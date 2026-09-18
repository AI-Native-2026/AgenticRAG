# Agentic RAG v2 —— 生产增强版

在 [v1](../agentic_rag/README.md)（单机可跑教学版）基础上，按**生产级设计**
补齐 12 项增强：API 服务化、可观测性、Kafka 队列化、LLM 网关加固、
安全多租户、工具治理、数据治理、评测回归、admin 平台化。
**v1 原样保留，两版可并行运行。**

## 环境

| 项 | 值 |
|---|---|
| VM | AutoDL Ubuntu 22.04（RTX 4090，数据盘 `/root/autodl-tmp`） |
| 项目 | `/root/autodl-tmp/agentic_rag_v2` |
| Python 环境 | `/root/autodl-tmp/conda_envs/agentic_rag`（与 v1 共用） |
| 队列 | Kafka 4.1.2（KRaft 单节点，`/root/autodl-tmp/kafka`） |
| 依赖 | v1 依赖 + `requirements-v2.txt`（fastapi/uvicorn/kafka-python/PyJWT/pytest） |

## 快速开始

```bash
# 1. 激活环境 + 前置服务（Mongo/Redis/Kafka 需已启动）
source /root/miniconda3/etc/profile.d/conda.sh
conda activate /root/autodl-tmp/conda_envs/agentic_rag
export HF_HOME=/root/autodl-tmp/.cache/huggingface
cd /root/autodl-tmp/agentic_rag_v2

# 2. 一键启动 API + 队列消费者
bash scripts/start_services.sh start

# 3. 端到端冒烟测试（8/8 通过）
python scripts/smoke_api.py

# 4. 建租户 / 看报表 / 跑回归
python scripts/admin/create_tenant.py --tenant tech --tokens 100000 --storage 10000
python scripts/admin/report.py
python scripts/05_eval.py --all --out data/baseline.json
python scripts/admin/check_regression.py --current data/baseline.json

# 5. 单测
python -m pytest tests/ -v
```

## v1 → v2 对照

| 能力 | v1 | v2 |
|---|---|---|
| 对外接口 | 命令行 | FastAPI + JWT + SSE |
| 文档入库 | 同步 | Kafka 队列（幂等/死信/优雅停机） |
| 观测 | 打印日志 | 事件模型 + JSONL + 指标 + 告警 |
| LLM 网关 | 重试 | 重试 + 限流 + 熔断 + GPU 锁 + KV 统计 |
| 工具 | 裸工具 | 注册中心 + 角色权限 + 审计 |
| 安全 | 防御性 prompt | + JWT + 配额 + 幂等键 |
| 数据 | — | 审计 / 血缘 / 计量 / 配额 |
| 评测 | 5 题 | 基线 + 回归门禁 |
| 运维 | 手动 | admin CLI + 健康检查 |

## 学习手册（细致版，讲透为什么）

| 篇 | 内容 |
|---|---|
| [00 架构总览](docs/00_v2架构总览.md) | v1→v2 演进、边界与取舍 |
| [01 API 服务化](docs/01_API服务化.md) | FastAPI/JWT/SSE/健康检查/幂等键 |
| [02 可观测性](docs/02_可观测性.md) | 事件模型/JSONL/指标聚合/告警 |
| [03 消息队列](docs/03_消息队列.md) | Kafka KRaft/生产者/幂等/死信/优雅停机 |
| [04 LLM 网关增强](docs/04_LLM网关增强.md) | 令牌桶/熔断/GPU 锁/KV 前缀统计 |
| [05 安全与多租户](docs/05_安全与多租户.md) | JWT/越权防御/注入/配额 |
| [06 工具治理与审计](docs/06_工具治理与审计.md) | 注册中心/角色/审计 |
| [07 数据治理](docs/07_数据治理.md) | 血缘/计量/删除 |
| [08 评测回归与基线](docs/08_评测回归与基线.md) | 基线/门禁/LLM 裁判 |
| [09 admin 平台化](docs/09_admin平台化.md) | admin CLI + 管理 API |

## 工程结构（相对 v1 的增量）

```
agentic_rag_v2/
├── src/
│   ├── api/            # FastAPI + JWT + SSE + 健康检查
│   ├── observability/  # 事件/日志/sink/metrics/告警
│   ├── queue/          # Producer/Consumer 抽象 + Kafka + dev 后端
│   ├── llm/            # 限流 + 熔断 + GPU 锁 + KV 统计
│   ├── agent/          # 工具注册中心 + 审计
│   ├── storage/        # +audit/lineage/metering/quota
│   └── ingestion/      # producer/consumer 拆分
├── scripts/
│   ├── admin/          # create_tenant/list_tenants/report/check_regression
│   ├── run_api.py / run_consumer.py / start_services.sh
│   └── smoke_api.py    # 一键端到端冒烟
├── tests/              # pytest（限流/熔断/队列/JWT/权限）
└── data/               # baseline.json + alerts_rules.json
```
