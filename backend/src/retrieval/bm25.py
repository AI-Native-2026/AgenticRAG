"""BM25 关键词检索（对应学习手册 04 篇）。

为什么需要 BM25：
- 向量检索擅长语义相关，但对"精确词/专有名词/编号"容易漏召回
- BM25 是经典的词频统计检索（TF-IDF 的强化版），对精确匹配极其可靠

中文关键点：
- BM25 按空格分词；中文必须先用 jieba 分词，否则"苹果公司"会被当成一个
  未知单词，检索失效 —— 这是本模块最重要的教学点。
"""

from typing import Dict, List, Optional

import jieba
from rank_bm25 import BM25Okapi


def jieba_tokenize(text: str) -> List[str]:
    """中文分词：jieba 精确模式 + 过滤空白。"""
    # 去掉停用/噪声词可以进一步提升效果，教学保留最简形态
    return [w.strip() for w in jieba.lcut(text) if w.strip()]


class BM25Retriever:
    """基于 rank-bm25 的关键词检索器。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        self.node_map: Dict[str, Dict] = {}
        self.bm25: Optional[BM25Okapi] = None

    def build(self, nodes: List[Dict]) -> None:
        """用节点列表构建 BM25 索引（每次启动重建即可，量级小）。"""
        self.documents = [n["text"] for n in nodes]
        self.doc_ids = [n["node_id"] for n in nodes]
        self.node_map = {n["node_id"]: n for n in nodes}
        tokenized = [jieba_tokenize(d) for d in self.documents]
        self.bm25 = BM25Okapi(tokenized, k1=self.k1, b=self.b)

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """检索，返回按得分降序的 [{node_id, score, text, metadata}]。"""
        if self.bm25 is None:
            return []
        query_tokens = jieba_tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        ranked = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        out = []
        for i in ranked:
            nid = self.doc_ids[i]
            node = self.node_map.get(nid, {})
            out.append({"node_id": nid, "score": float(scores[i]),
                        "text": node.get("text", ""),
                        "metadata": node.get("metadata", {})})
        return out


if __name__ == "__main__":
    # 注意：demo 语料要足够大。rank-bm25 用 ATIRE idf 变体
    # (log((N-n+0.5)/(n+0.5)))，词出现在恰好一半文档时 idf=0，
    # 只有 2 篇文档时任何词都会退化到 idf=0（教学踩坑点）。
    nodes = [
        {"node_id": "n1", "text": "苹果公司发布了新款 iPhone 手机，主打拍照功能。"},
        {"node_id": "n2", "text": "特斯拉发布了新款电动车，续航里程大幅提升。"},
        {"node_id": "n3", "text": "华为发布了 Mate 90 旗舰手机，支持卫星通信。"},
        {"node_id": "n4", "text": "三星 Galaxy S27 采用折叠屏设计，主打商务办公。"},
        {"node_id": "n5", "text": "小鹏 G7 电动车搭载城市智驾系统，主打性价比。"},
        {"node_id": "n6", "text": "宁德时代发布新一代电池，能量密度提升至 500Wh/kg。"},
    ]
    br = BM25Retriever()
    br.build(nodes)
    print("查询『苹果手机』→", br.search("苹果手机", top_k=2))
    print("查询『电动车』→", br.search("电动车", top_k=3))
    print("查询『电池』→", br.search("电池", top_k=3))
