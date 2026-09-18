"""消息队列层（对应 v2 手册 03 篇）。

为什么抽象出接口 + 双后端：
  生产用 Kafka，但 Kafka broker 是 JVM 重组件——在还没有 broker 的机器上
  做开发联调很痛苦。抽象出 Producer/Consumer 接口后：
    - kafka_backend  ：真实 Kafka（生产）
    - dev_backend    ：内存队列（本地开发/单测，无 Kafka 也能跑通全流程）
  切换后端只需改一个环境变量 QUEUE_BACKEND=kafka|dev。

消息语义：
  我们采用「at-least-once」：消费者处理成功才 commit 偏移；
  处理失败重试；多次失败进死信队列。代价是可能重复消费，
  由消费端的「幂等（版本号判断）」来兜底（见 ingestion/consumer.py）。
"""
