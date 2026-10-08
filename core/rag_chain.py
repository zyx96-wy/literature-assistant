from config.settings import RETRIEVAL_K


def rewrite_query(question: str) -> list:
    """用 LLM 把问题改写成多条查询"""
    from langchain_community.chat_models import ChatTongyi
    from langchain_core.prompts import ChatPromptTemplate
    from config.settings import LLM_MODEL, DASHSCOPE_API_KEY
    import os

    os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY

    llm = ChatTongyi(model_name=LLM_MODEL, temperature=0.1)
    prompt = ChatPromptTemplate.from_template('''你是查询改写助手。
把用户问题改写成最多 3 条适合知识库检索的查询。
每行一条，不要编号，不要解释。

用户问题：{question}

输出：''')

    chain = prompt | llm
    result = chain.invoke({'question': question})
    lines = [l.strip() for l in result.content.strip().split('\n') if l.strip()]
    return lines[:3] if lines else [question]


def _translate_to_english(queries: list) -> list:
    """
    把中文 query 翻成英文检索词（用于跨语言召回）。
    已是英文的 query 原样输出。
    """
    from langchain_community.chat_models import ChatTongyi
    from langchain_core.prompts import ChatPromptTemplate
    from config.settings import LLM_MODEL, DASHSCOPE_API_KEY
    import os

    os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY

    llm = ChatTongyi(model_name=LLM_MODEL, temperature=0.0)
    prompt = ChatPromptTemplate.from_template('''把下面的问题翻译成简洁的英文检索词。
每行一条，不要编号，不要解释。如果已经是英文，原样输出。

{queries}

输出：''')

    qs_text = '\n'.join(queries)
    try:
        result = (prompt | llm).invoke({'queries': qs_text}).content.strip()
        lines = [l.strip() for l in result.split('\n') if l.strip()]
        return lines[:3] if lines else []
    except Exception as e:
        print(f'⚠️ [RAG] query 翻译失败：{e}')
        return []


def is_references(content: str) -> bool:
    """判断是否为参考文献段"""
    if not content:
        return False
    head = content[:200].strip()
    markers = ['References', 'REFERENCES', 'Bibliography', 'BIBLIOGRAPHY',
               'Works Cited', '参考文献', '引用文献', '文献列表']
    return any(m in head for m in markers)


def _has_chinese(s: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in s)


def multi_retrieval(question: str, vectorstore, doc_ids: list = None) -> list:
    """
    多路检索 + 合并 + References 过滤

    新增：如果 query 含中文，翻译成英文，中英各检一次再合并 —— 解决跨语言召回。

    :param doc_ids: 限定的 doc_id 列表。给定后只在这些文献内检索（元数据过滤），
                    用于兑现「亮牌范围 == 实际检索范围」。None = 全库。
    """
    queries = rewrite_query(question)

    # 跨语言优化：中文 query 翻译成英文，中英各检一次
    if any(_has_chinese(q) for q in queries):
        translated = _translate_to_english(queries)
        if translated:
            queries = queries + translated
            print(f'[RAG] 跨语言检索：中文 {len(queries) - len(translated)} 条 + 英文 {len(translated)} 条')

    all_docs = []

    # 元数据过滤：Chroma 支持 where 过滤
    flt = {'doc_id': {'$in': list(doc_ids)}} if doc_ids else None

    for q in queries:
        try:
            docs = vectorstore.similarity_search(q, k=RETRIEVAL_K, filter=flt)
        except Exception:
            docs = vectorstore.similarity_search(q, k=RETRIEVAL_K)

            if doc_ids:
                docs = [d for d in docs if d.metadata.get('doc_id') in doc_ids]
        all_docs.extend(docs)

    # 去重 + 过滤 References
    seen = set()
    unique = []
    for doc in all_docs:
        if is_references(doc.page_content):
            continue
        key = doc.page_content[:50]
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)

    return unique