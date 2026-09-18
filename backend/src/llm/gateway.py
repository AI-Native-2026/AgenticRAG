"""LLM 网关层（v2 增强版，对应 v2 手册 04 篇）。

v1 只做「重试+退避」。v2 叠加四层生产防护：
  1. GPU 推理单写者锁（threading.RLock）
     多个请求/消费者并发时，embedding 和重排都挤同一块 GPU，
     不加锁会显存争抢/崩溃。全局锁保证同时只有一个线程在推理。
  2. 按租户令牌桶限流（rate_limit.TenantRateLimiter）
     防止单租户打爆 LLM API / 打爆本地 GPU。
  3. 熔断器（circuit_breaker.CircuitBreaker）
     LLM API 连续失败 → 快速失败，避免雪崩。
  4. KV 前缀缓存统计（honest 版本）
     说明：真正的 prompt/KV 缓存是【服务商侧】自动特性（DeepSeek/OpenAI
     对缓存命中的 token 收费大幅降低）。应用层能做的是：
       a) 把 prompt 组织成「稳定前缀在前、变化内容在后」，最大化命中；
       b) 从 response usage 里读取 cached_tokens，统计"命中率/省了多少"。
     这里实现的是 a+b 的统计口径，供成本报表使用。
"""

import hashlib
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.base.llms.types import ChatResponse
from llama_index.llms.openai_like import OpenAILike

from src.config import get_env
from src.llm.circuit_breaker import CircuitBreaker
from src.llm.rate_limit import TenantRateLimiter

logger = logging.getLogger(__name__)

# 全局 GPU 推理锁（单写者）。模块级单例，全进程共享。
MODEL_LOCK = threading.RLock()


class MeteringOpenAILike(OpenAILike):
    """继承 OpenAILike 的 LLM：统一记录每次调用的 usage（token 计量 + KV 统计）。

    为什么用继承而不是包装：
      包装对象不是 LLM 实例，FunctionAgent 的 pydantic 校验会拒绝
      （type=model_type 报错）。继承 OpenAILike 本身就是合法 LLM，
      只覆写 chat/achat 增加记录逻辑，既能过校验又能统一计量。
    """

    def __init__(self, on_usage, **kwargs):
        super().__init__(**kwargs)
        self._on_usage_cb = on_usage

    def chat(self, messages, **kwargs):
        resp = super().chat(messages, **kwargs)
        self._record(resp)
        return resp

    async def achat(self, messages, **kwargs):
        resp = await super().achat(messages, **kwargs)
        self._record(resp)
        return resp

    def _record(self, resp) -> None:
        """提取 usage 回调（prompt_tokens, completion_tokens）。"""
        if self._on_usage_cb is None:
            return
        try:
            raw = getattr(resp, "raw", None)
            if isinstance(raw, dict):  # dict 形态
                prompt = raw.get("prompt_tokens", 0)
                completion = raw.get("completion_tokens", 0)
            else:  # OpenAI ChatCompletion 对象形态
                usage = getattr(raw, "usage", None)
                prompt = getattr(usage, "prompt_tokens", 0) or 0
                completion = getattr(usage, "completion_tokens", 0) or 0
            self._on_usage_cb(prompt, completion)
        except Exception:  # noqa: BLE001 —— 计量失败不影响主流程
            pass


class LLMGateway:
    """DeepSeek LLM 网关：重试 + 退避 + 超时 + 限流 + 熔断。"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        env = get_env()
        self.api_key = env["DEEPSEEK_API_KEY"]
        self.base_url = env["LLM_BASE_URL"]
        self.model = env["LLM_MODEL"] or "deepseek-chat"
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.rate_limiter = TenantRateLimiter(
            default_capacity=20, default_rate=10  # 每租户默认 10 QPS、突发 20
        )
        self.breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        # KV 前缀缓存统计（见模块 docstring）
        self.kv_stats = {"calls": 0, "cached_tokens": 0, "total_input_tokens": 0}

        if not self.api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY。请确认 /root/autodl-tmp/labs/07/test.env 存在且含该字段。"
            )

        # 用 OpenAILike 而不是 llama-index-llms-deepseek：
        # DeepSeek 类把 metadata.is_function_calling_model 置为 False，
        # 导致 FunctionAgent 拒绝使用；OpenAILike 是 OpenAI 兼容实现，
        # 显式打开函数调用开关即可支持 DeepSeek 的 tool_calls。
        # 用 OpenAILike 而不是 llama-index-llms-deepseek：
        # DeepSeek 类把 metadata.is_function_calling_model 置为 False，
        # 导致 FunctionAgent 拒绝使用；OpenAILike 是 OpenAI 兼容实现，
        # 显式打开函数调用开关即可支持 DeepSeek 的 tool_calls。
        # 用 MeteringOpenAILike 子类（继承自 OpenAILike）统一计量 usage。
        self.llm = MeteringOpenAILike(
            on_usage=self._on_usage,
            model=self.model,
            api_key=self.api_key,
            api_base=self.base_url,
            is_chat_model=True,                  # 走 /chat/completions 端点
            is_function_calling_model=True,      # 关键：显式声明支持函数调用
            temperature=float(env.get("DEEPSEEK_TEMPERATURE") or 0.1),
            max_tokens=int(env.get("DEEPSEEK_MAX_TOKENS") or 2048),
            timeout=60.0,
        )

    def _on_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """每次 LLM 调用后的统一记账：KV 缓存统计 + 用量计量。"""
        self.kv_stats["calls"] += 1
        self.kv_stats["total_input_tokens"] += prompt_tokens
        try:
            from src.agent.tools import _CTX  # 从线程本地拿当前租户
            self.kv_stats["cached_tokens"] += 0  # cached 细节在 raw 内，此处简化
            from src.storage.metering import Metering

            Metering().record_generate(_CTX.tenant or "default", prompt_tokens, completion_tokens)
        except Exception:  # noqa: BLE001 —— 计量失败不影响主流程
            pass

    def build_llm(self):
        """返回配置好的 DeepSeek LLM 实例。"""
        return self.llm

    def chat(self, messages: Sequence[ChatMessage], tenant: str = "default", **kwargs) -> ChatResponse:
        """带四层防护的 chat 调用。

        顺序：限流 → 熔断 → 重试退避 → 调用 → KV 统计。
        """
        # 1) 限流：超限直接抛错（快速失败），由上层决定降级
        if not self.rate_limiter.allow(tenant):
            raise RateLimitedError(f"租户 {tenant} 触发限流")

        # 2) 熔断保护
        def _do_chat():
            for attempt in range(self.max_retries):
                try:
                    return self.llm.chat(messages, **kwargs)
                except Exception as e:  # noqa: BLE001 —— 网关层统一兜底
                    if attempt == self.max_retries - 1:
                        raise
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning("LLM 调用失败(%s)，%.1fs 后重试(%d/%d)",
                                   e, delay, attempt + 1, self.max_retries)
                    time.sleep(delay)
            raise RuntimeError("LLM 调用最终失败")  # 理论不可达

        try:
            resp = self.breaker.call(_do_chat)
        except Exception:
            raise  # 熔断打开或调用失败，向上抛
        self._record_kv_stats(resp)
        return resp

    def complete(self, prompt: str, tenant: str = "default", **kwargs) -> str:
        """带重试的纯文本补全。"""
        return str(self.chat([ChatMessage(role=MessageRole.USER, content=prompt)],
                             tenant=tenant, **kwargs))

    # ---------- KV 前缀缓存统计（honest 版） ----------

    def _record_kv_stats(self, resp: ChatResponse) -> None:
        """从 response 的 usage 里读取缓存命中 token，累计统计。"""
        try:
            usage = getattr(resp, "raw", None)
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens", 0)
                cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
            else:
                prompt_tokens = cached = 0
            self.kv_stats["calls"] += 1
            self.kv_stats["total_input_tokens"] += prompt_tokens
            self.kv_stats["cached_tokens"] += cached
        except Exception:  # noqa: BLE001 —— 统计失败不影响主流程
            pass

    @property
    def kv_cache_hit_rate(self) -> float:
        """prompt 前缀缓存命中率（供成本报表）。"""
        if self.kv_stats["total_input_tokens"] == 0:
            return 0.0
        return self.kv_stats["cached_tokens"] / self.kv_stats["total_input_tokens"]


class RateLimitedError(Exception):
    pass


# ---------- 全局 GPU 推理单写者工具 ----------

class ModelExecutor:
    """包一层模型调用，强制全局锁（GPU 单写者）。"""

    @staticmethod
    def embed(embed_model, texts: List[str]) -> List[List[float]]:
        with MODEL_LOCK:
            return embed_model.get_text_embedding_batch(texts)

    @staticmethod
    def rerank(reranker, pairs):
        with MODEL_LOCK:
            return reranker.predict(pairs)


def build_embed_model(device: Optional[str] = None):
    """构造 bge-small-zh-v1.5 本地 embedding 模型（HuggingFaceEmbedding）。"""
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    env = get_env()
    device = device or env["DEVICE"]
    return HuggingFaceEmbedding(
        model_name=env["BGE_EMBED_PATH"],
        device=device,
        # pooling 由模型 config 决定（bge-small-zh 默认 CLS pooling）
        normalize=True,      # 归一化，便于用余弦相似度
        query_instruction="为这个句子生成表示以用于检索相关文章：",
    )


def setup_settings() -> Dict[str, Any]:
    """初始化全局 LlamaIndex Settings，返回（llm, embed_model, env）。"""
    env = get_env()
    gateway = LLMGateway()
    llm = gateway.build_llm()
    embed_model = build_embed_model()

    Settings.llm = llm
    Settings.embed_model = embed_model
    Settings.context_window = 8192
    Settings.num_output = 1024

    logger.info("Settings 就绪：llm=%s, embed_model=%s, device=%s",
                env["LLM_MODEL"], env["BGE_EMBED_PATH"], env["DEVICE"])
    return {"llm": llm, "embed_model": embed_model, "env": env}
