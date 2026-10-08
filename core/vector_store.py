import os
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from config.settings import CHROMA_DIR, EMBEDDING_MODEL


def build_vectorstore(chunks: list) -> Chroma:
    """创建向量数据库并持久化到本地"""
    embeddings = DashScopeEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR
    )
    print("✅ 向量数据库构建完成")
    return vectorstore

def load_vectorstore() -> Chroma:
    """加载已有的向量数据库"""
    embeddings = DashScopeEmbeddings(model=EMBEDDING_MODEL)
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)