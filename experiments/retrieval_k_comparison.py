# -*- coding: utf-8 -*-
"""
检索参数对比实验：k 实验
=========================

不调 LLM，只跑检索，看不同 k 下的召回效果。

用法：
    python experiments/retrieval_k_comparison.py

它会：
    1. 从 SQLite 读所有 doc
    2. 对每个 topic 和每个 k，跑一遍「每篇独立检索」
    3. 记录：召回片段数、覆盖篇数、漏篇
    4. 打印对比表
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.vector_store import load_vectorstore
from core.rag_chain import rewrite_query, is_references
from backend.database import get_all_docs, get_doc


# ===== 实验参数 =====
TOPICS = [
    'AI 与写作',
    '文本隐写',
    'AI 素养',
    # 你可以加更多
]
K_VALUES = [3, 6, 8, 12]


def retrieve_per_doc(vs, queries, doc_ids, k, max_per_doc=5):
    """每篇独立检索（和 create_review 逻辑一致）"""
    per_doc_hits = {}

    for doc_id in doc_ids:
        doc_hits = []
        for q in queries:
            try:
                docs = vs.similarity_search(q, k=k, filter={'doc_id': doc_id})
            except Exception:
                docs = vs.similarity_search(q, k=k)
                docs = [d for d in docs if d.metadata.get('doc_id') == doc_id]
            doc_hits.extend(docs)

        # 该篇去重 + 过滤参考文献
        seen_keys = set()
        unique_for_doc = []
        for d in doc_hits:
            if is_references(d.page_content):
                continue
            key = d.page_content[:50]
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_for_doc.append(d)

        unique_for_doc = unique_for_doc[:max_per_doc]

        if unique_for_doc:
            per_doc_hits[doc_id] = unique_for_doc

    return per_doc_hits


def main():
    # 1. 加载数据
    vs = load_vectorstore()
    docs = get_all_docs()
    doc_ids = [d['id'] for d in docs]
    print(f'📚 库里有 {len(doc_ids)} 篇文献：')
    for d in docs:
        print(f'   {d["id"]}  {d["title"][:50]}')
    print()

    # 2. 对每个 topic 做查询改写（只做一次，所有 k 复用）
    topic_queries = {}
    for topic in TOPICS:
        print(f'🔄 改写 topic：{topic}')
        queries = rewrite_query(topic)
        topic_queries[topic] = queries
        print(f'   → {queries}')
    print()

    # 3. 对每个 k，跑一遍
    results = {}  # (topic, k) -> {召回片段数, 覆盖篇数, 漏篇}

    for k in K_VALUES:
        print(f'=' * 60)
        print(f'📊 k = {k}')
        print(f'=' * 60)

        for topic in TOPICS:
            queries = topic_queries[topic]
            per_doc_hits = retrieve_per_doc(vs, queries, doc_ids, k)

            n_chunks = sum(len(v) for v in per_doc_hits.values())
            n_docs = len(per_doc_hits)
            missing = [did for did in doc_ids if did not in per_doc_hits]

            results[(topic, k)] = {
                'n_chunks': n_chunks,
                'n_docs': n_docs,
                'missing': missing,
            }

            missing_str = f'  漏篇：{missing}' if missing else ''
            print(f'  {topic}：{n_chunks} 个片段，{n_docs}/{len(doc_ids)} 篇覆盖{missing_str}')

    # 4. 汇总表
    print()
    print(f'=' * 60)
    print('📊 汇总（平均）')
    print(f'=' * 60)

    header = f'{"k":>4}  {"平均片段数":>12}  {"平均覆盖篇数":>14}  {"漏篇 topic 数":>14}'
    print(header)
    print('-' * len(header))

    for k in K_VALUES:
        rows = [results[(t, k)] for t in TOPICS]
        avg_chunks = sum(r['n_chunks'] for r in rows) / len(rows)
        avg_docs = sum(r['n_docs'] for r in rows) / len(rows)
        n_missing_topics = sum(1 for r in rows if r['missing'])

        print(f'{k:>4}  {avg_chunks:>12.1f}  {avg_docs:>14.1f}  {n_missing_topics:>14}')

    print()
    print('💡 建议：')
    print('  - 覆盖篇数越多越好（不漏篇）')
    print('  - 片段数适中（太多会拉长 LLM 输入）')
    print('  - 选一个「覆盖全 + 片段不太多」的 k')


if __name__ == '__main__':
    main()