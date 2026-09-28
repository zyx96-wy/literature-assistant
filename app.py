import os
import sys
from config.settings import DOCS_DIR, CHROMA_DIR
from core.document_loader import load_documents
from core.text_splitter import split_documents
from core.vector_store import build_vectorstore, load_vectorstore
from core.rag_chain import build_rag_chain


def chat_loop(rag_chain):
    """启动交互式问答"""
    print("\n" + "=" * 50)
    print("🤖 RAG问答系统已就绪，输入问题开始提问（输入 q 退出）")
    print("=" * 50)
    while True:
        question = input("\n❓ 你的问题：").strip()
        if question.lower() in ("q", "quit", "exit"):
            print("👋 再见！")
            break
        if not question:
            continue
        try:
            answer = rag_chain.invoke(question)
            print(f"\n🤖 回答：{answer}")
        except Exception as e:
            print(f"⚠️ 出错了：{e}")


if __name__ == "__main__":
    if "--rebuild" in sys.argv:
        print("🔄 正在重建向量库...")
        docs = load_documents(DOCS_DIR)
        chunks = split_documents(docs)
        vectorstore = build_vectorstore(chunks)
    else:
        if os.path.exists(CHROMA_DIR):
            print("📂 加载已有向量库...")
            vectorstore = load_vectorstore()
        else:
            print("🔄 首次运行，正在构建向量库...")
            docs = load_documents(DOCS_DIR)
            chunks = split_documents(docs)
            vectorstore = build_vectorstore(chunks)

    rag_chain = build_rag_chain(vectorstore)
    chat_loop(rag_chain)