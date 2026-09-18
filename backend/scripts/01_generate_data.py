"""脚本 01：生成示例数据（多租户、中英混合、含长文档）。

用法：python scripts/01_generate_data.py
产出：data/sample_docs/{tech,finance}/xxx.md

设计目的（对应学习手册 02 篇）：
- 多租户（tech/finance）→ 演示 metadata 过滤 + 数据隔离
- 长文档 → 触发真实切分（多 chunk）
- 含明确数字 → 供 Agent 演示"检索 + 计算"多工具协作
- 内容自洽 → 评测集可回答、可断言来源
"""

import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "sample_docs"

# 每个 (tenant, filename, content) 一组
DOCS: list[tuple[str, str, str]] = []


def add(tenant: str, name: str, content: str):
    DOCS.append((tenant, name, content))


# ============ tech 租户 ============

add("tech", "apple_iphone_17.md", """# Apple iPhone 17 产品介绍

## 概述

苹果公司于 2026 年 9 月发布了新一代旗舰手机 iPhone 17。它搭载 A19 仿生芯片，
相比上一代 A18 性能提升约 30%，能效比提升 25%。这款手机主打专业影像与长续航。

## 核心配置

iPhone 17 提供三个存储版本：128GB 售价 5999 元，256GB 售价 6999 元，
512GB 售价 8999 元。屏幕采用 6.3 英寸 Super Retina XDR Pro，
支持 120Hz ProMotion 自适应刷新率，峰值亮度达到 3000 尼特。

影像系统是 iPhone 17 的最大亮点。主摄升级为 4800 万像素第二代融合式摄像头，
支持 2 倍光学变焦和 10 倍数字变焦。新增的「电影级人像」模式可以在视频中
实时调整景深，这一功能在业界属于首创。

## 电池与充电

iPhone 17 电池容量提升至 4800mAh，官方宣称视频播放时间最长可达 32 小时。
支持 45W 有线快充和 25W MagSafe 磁吸无线充电。30 分钟即可充至 60%。

## 总结

iPhone 17 的定位是"影像旗舰"，适合摄影师与内容创作者。它的主要竞争对手是
华为 Mate 90 和三星 Galaxy S27 Ultra。
""")

add("tech", "tesla_model3_2026.md", """# Tesla Model 3 焕新版 2026 款技术解析

## 概述

特斯拉于 2026 年春季交付了 Model 3 焕新版。这次改款重点优化了底盘悬挂、
座舱静音和驾驶辅助硬件。

## 性能参数

后轮驱动版采用 60kWh 磷酸铁锂电池，CLTC 续航 623 公里，百公里加速 5.8 秒。
长续航全轮驱动版搭载 78kWh 三元锂电池，CLTC 续航 713 公里，
百公里加速 4.2 秒，峰值功率 366 马力。

## 充电

长续航版支持 V3 超级充电桩，峰值充电功率 250kW，15 分钟即可补充 300 公里续航。
家用 7kW 交流桩充满约需 10 小时。

## 价格

后驱版起售价 26.99 万元，长续航版起售价 31.99 万元。
选购增强版自动辅助驾驶功能需额外支付 3.2 万元。
""")

add("tech", "chroma_db_usage_guide.md", """# ChromaDB 使用指南

## 什么是 ChromaDB

ChromaDB 是一个开源的向量数据库，专门用于存储和检索 embedding 向量。
它的特点是轻量、易用、支持持久化。底层使用 SQLite 存储数据，并采用 WAL
（Write-Ahead Log）机制保证写入不丢失。

## 安装与快速开始

首先安装：pip install chromadb。

创建一个持久化客户端并写入数据：

    import chromadb
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection("my_docs")
    collection.add(
        ids=["id1", "id2"],
        documents=["苹果发布了新手机", "特斯拉发布新款电动车"],
    )

## 检索与过滤

ChromaDB 支持相似度检索和元数据过滤：

    collection.query(query_texts=["新款手机"], n_results=2)

同时可以使用 where 参数按元数据过滤，例如 where={"category": "tech"}。

## 性能与规模

ChromaDB 的 HNSW 索引在查询时会整体加载到内存，因此适合单机百万级向量。
当规模进一步扩大时，需要考虑迁移到 Milvus 或 Qdrant 等分布式向量数据库。
""")

add("tech", "llm_api_docs.md", """# LLM API 调用指南

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
""")

# ============ finance 租户 ============

add("finance", "market_report_2026_q3.md", """# 2026 年第三季度市场报告

## 宏观经济

2026 年第三季度，全球经济增长放缓至 2.8%。美联储在 9 月维持利率不变，
但暗示年底可能有一次 25 个基点的降息。人民币兑美元汇率在 7.05 附近波动。

## A 股表现

三季度 A 股整体震荡上行。上证指数累计上涨 6.2%，深证成指上涨 9.5%。
北向资金三季度净流入 1800 亿元，其中 40% 流向新能源板块。

## 行业热点

新能源和人工智能是两大主线。新能源汽车三季度销量同比增长 35%，
光伏组件出口同比增长 22%。人工智能板块虽然估值偏高，但业绩增速
仍保持在 50% 以上。

## 风险提示

四季度需要关注三个风险：地缘冲突升级、美联储降息不及预期、
以及部分高估值成长股的回调压力。
""")

add("finance", "fund_introduction.md", """# 稳健成长混合基金产品介绍

## 产品概况

稳健成长混合基金成立于 2020 年，是一只偏股混合型基金。
基金代码 001234，托管行为工商银行，管理费每年 1.2%，托管费每年 0.2%。

## 投资策略

基金采用"核心 + 卫星"策略：60% 仓位配置沪深 300 成分股作为核心底仓，
40% 仓位配置新能源、医药等高成长行业作为卫星仓位。历史年化收益率 12.8%，
最大回撤控制在 18% 以内。

## 近期表现

截至 2026 年三季度末，基金规模 85 亿元，过去一年净值增长率 15.3%。
近三年累计收益 42.1%。基金最近一次分红是 2026 年 8 月，每 10 份分红 0.6 元。

## 购买方式

投资者可以通过天天基金、蚂蚁财富等平台申购，起购金额 100 元，
支持定投。赎回费根据持有时间递减，持有满一年免赎回费。
""")

add("finance", "risk_management.md", """# 个人投资风险管理指南

## 为什么要做风险管理

任何投资都有风险。历史数据显示，股票市场每年的波动率通常在 15% 到 25% 之间。
没有风险管理体系，一次错误的决策可能吞噬多年的收益。

## 仓位管理

单只股票仓位建议不超过总资产的 10%，单行业不超过 25%。
持仓数量建议控制在 8 到 15 只，既分散风险又不至于无法跟踪。

## 止损纪律

买入前就要设定止损位，常见的止损规则是亏损 8% 无条件卖出。
连续三次止损后应停止交易两周，复盘总结后再继续，避免情绪化操作。

## 定期再平衡

每季度对资产组合做一次再平衡：将涨幅过大的部分卖出，
把仓位加回到目标比例。这可以帮助投资者"高抛低吸"，保持风险水平稳定。
""")


def main():
    random.seed(42)
    written = 0
    for tenant, name, content in DOCS:
        out_dir = DATA_DIR / tenant
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written += 1
        n_chunks = max(1, len(content) // 256)
        print(f"生成 {tenant}/{name}（{len(content)}字，约{n_chunks}个chunk）")
    print(f"\n共生成 {written} 篇文档，位于 {DATA_DIR}")


if __name__ == "__main__":
    main()
