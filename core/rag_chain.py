from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from config.settings import LLM_MODEL, LLM_TEMPERATURE, RETRIEVAL_K

def build_rag_chain(vectorstore) -> any:
    """构建完整的RAG检索增强生成链"""
    retriever = vectorstore.as_retriever(search_kwargs={"k": RETRIEVAL_K})
    llm = ChatTongyi(model_name=LLM_MODEL, temperature=LLM_TEMPERATURE)

    prompt = ChatPromptTemplate.from_template("""你是一个专业的知识助手。请严格基于以下【参考资料】回答用户问题。
如果资料中没有相关信息，请直接回答"根据现有资料无法回答"，不要编造。

【参考资料】
{context}

【用户问题】
{question}

【要求】
1. 回答需简洁准确
2. 必要时标注来源编号，如[1]
3. 资料不足时明确说明""")

    def format_docs(docs):
        formatted = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知文件")
            formatted.append(f"[{i}] {source}: {doc.page_content}")
        return "\n\n".join(formatted)

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}

        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain


# core/rag_chain.py

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


def is_references(content: str) -> bool:
    """判断是否为参考文献段"""
    if not content:
        return False
    head = content[:200].strip()
    markers = ['References', 'REFERENCES', 'Bibliography', 'BIBLIOGRAPHY',
               'Works Cited', '参考文献', '引用文献', '文献列表']
    return any(m in head for m in markers)


def multi_retrieval(question: str, vectorstore, doc_ids: list = None) -> list:
    """
    多路检索 + 合并 + References 过滤

    :param doc_ids: 限定的 doc_id 列表。给定后只在这些文献内检索（元数据过滤），
                    用于兑现「亮牌范围 == 实际检索范围」。None = 全库。
    """
    queries = rewrite_query(question)
    all_docs = []

    # 元数据过滤：Chroma 支持 where 过滤
    flt = {'doc_id': {'$in': list(doc_ids)}} if doc_ids else None

    for q in queries:
        try:
            docs = vectorstore.similarity_search(q, k=4, filter=flt)
        except Exception:
            # 过滤失败绝不能静默扩库：退化为「全库召回 + 按 metadata 再筛一次」
            docs = vectorstore.similarity_search(q, k=4)
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
