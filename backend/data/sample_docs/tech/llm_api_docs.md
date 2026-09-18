# LLM API 调用指南

## 认证方式

所有 API 请求都需要在请求头中携带 Authorization: Bearer <API_KEY>。
API Key 请妥善保管，不要提交到代码仓库。

## 文本补全

文本补全接口用于生成文本。请求参数包括 model、messages、temperature 和 max_tokens。
temperature 控制随机性，取值 0 到 2，数值越大输出越多样。

## 函数调用

函数调用（Function Calling）让模型可以自主决定调用外部工具。
模型会返回 tool_calls 字段，其中包含函数名和参数 JSON。调用完工具后，
把工具结果作为新的消息回传给模型，模型会继续推理。

## 限流与重试

免费和低阶账号存在 QPS 限制。当返回 429 状态码时，需要指数退避重试：
第一次等 1 秒，第二次等 2 秒，第三次等 4 秒，以此类推。
这是生产系统必须处理的健壮性问题。
