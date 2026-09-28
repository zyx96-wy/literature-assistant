# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.vector_store import load_vectorstore, build_vectorstore
from core.rag_chain import build_rag_chain
from config.settings import CHROMA_DIR, DOCS_DIR
from backend.deep_parse import deep_parse

router = APIRouter(prefix='/api')

_rag_chain = None

from backend.database import (
    init_db, get_all_docs, get_doc,
    insert_doc_with_paragraphs   # ← 加这个
)


def get_rag_chain():
    global _rag_chain
    if _rag_chain is None:
        if not os.path.exists(CHROMA_DIR):
            raise HTTPException(status_code=500, detail=f'向量库不存在：{CHROMA_DIR}')
        vs = load_vectorstore()
        result = build_rag_chain(vs)
        _rag_chain = result[0] if isinstance(result, tuple) else result
    return _rag_chain


class AskRequest(BaseModel):
    question: str
    # 限定的文献范围（doc_id 列表）。空 = 全库。
    # 非空时必须只在该范围内检索，绝不静默扩库。
    scope: list[str] = []

    class Config:
        schema_extra = {
            'example': {'question': '这篇用了什么检索器？', 'scope': ['lit_ab12cd34']}
        }


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/docs')
def list_docs():
    """从 SQLite 读文档列表"""
    docs = get_all_docs()
    return {'docs': docs}


@router.get('/docs/{doc_id}')
def get_doc_detail(doc_id: str):
    """获取单篇文档详情"""
    doc = get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f'文档不存在：{doc_id}')
    return doc


from backend.pdf_parser import parse_pdf, split_for_rag, split_for_reading


@router.post('/upload')
async def upload(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail='只支持 PDF 文件')

    doc_id = 'lit_' + str(uuid.uuid4())[:8]
    filepath = os.path.join(DOCS_DIR, f'{doc_id}.pdf')
    os.makedirs(DOCS_DIR, exist_ok=True)
    content = await file.read()
    with open(filepath, 'wb') as f:
        f.write(content)

    try:
        # 1. 解析 PDF
        text = parse_pdf(filepath)

        # 2. 两套分段
        rag_chunks = split_for_rag(text)
        read_paragraphs = split_for_reading(text)

        # 3. RAG 块入向量库
        from langchain_core.documents import Document
        docs = [
            Document(page_content=c, metadata={'doc_id': doc_id, 'source': file.filename})
            for c in rag_chunks
        ]
        vs = load_vectorstore()
        vs.add_documents(docs)

        # 4. LLM 抽字段（传入段落表，用于真实段落号定位与 quote 逐字校验）
        fields = deep_parse(text, paragraphs=read_paragraphs)

        # 5. 存数据库
        insert_doc_with_paragraphs(
            doc_id=doc_id,
            title=file.filename[:-4],
            meta='上传于 2026',
            text=text,
            paragraphs=read_paragraphs,
            fields=fields
        )

        return {
            'status': 'success',
            'doc_id': doc_id,
            'title': file.filename[:-4],
            'chunks': len(rag_chunks),
            'paragraphs': len(read_paragraphs),
            'fields_count': len([k for k, v in fields.items() if v])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'上传处理失败：{str(e)}')


@router.post('/ask')
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail='question 不能为空')

    try:
        from core.rag_chain import multi_retrieval
        from langchain_community.chat_models import ChatTongyi
        from langchain_core.prompts import ChatPromptTemplate
        from config.settings import LLM_MODEL

        question = req.question.strip()
        # 去重 + 去掉空值，保持顺序
        scope = list(dict.fromkeys([s for s in (req.scope or []) if str(s).strip()]))

        # 1. 多路检索（带范围过滤）
        vs = load_vectorstore()
        docs = multi_retrieval(question, vs, doc_ids=scope or None)

        # 范围限定下召回为空 —— 如实返回，绝不扩库兜底
        if scope and not docs:
            return {
                'answer': '在你选定的文献范围内未找到相关内容。已严格按所选范围检索，未扩大到全库。',
                'question': question,
                'sources': [],
                'scope': scope,
                'scope_empty': True
            }

        # 2. 拼接上下文 + 记录 sources
        context_parts = []
        sources = []
        for i, doc in enumerate(docs, 1):
            source_name = doc.metadata.get('source', '未知')
            doc_id = doc.metadata.get('doc_id', '')
            context_parts.append(f'[{i}] 来源：{source_name}\n{doc.page_content}')
            sources.append({
                'index': i,
                'source': source_name,
                'doc_id': doc_id,
                'content': doc.page_content[:200]
            })

        context = '\n\n'.join(context_parts)

        # 3. LLM 回答
        scope_note = (
            f'本次检索已限定在用户选定的 {len(scope)} 篇文献内（doc_id: {", ".join(scope)}）。'
            '只依据下面给出的片段作答，不得补充范围外的知识。'
            if scope else '本次检索范围为全部已上传文献。'
        )

        llm = ChatTongyi(model_name=LLM_MODEL, temperature=0.2)
        prompt = ChatPromptTemplate.from_template('''你是严谨的文献问答助手。
请根据参考文档回答问题。
如果参考文档没有相关信息，回答「当前知识库中未找到相关信息」。

【检索范围】
{scope_note}

【参考文档】
{context}

【要求】
1. 只使用参考文档中出现的信息
2. 回答时在句末标注来源编号，如 [1]、[2]

【用户问题】
{question}

回答：''')

        answer = (prompt | llm).invoke(
            {'context': context, 'question': question, 'scope_note': scope_note}
        ).content

        return {
            'answer': answer,
            'question': question,
            'sources': sources,
            'scope': scope,
            'scope_empty': False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'问答出错：{str(e)}')