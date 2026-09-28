from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader


def load_documents(docs_dir: str) -> list:
    """加载指定目录下的PDF文档"""
    loader = DirectoryLoader(
        docs_dir,
        glob="**/*.pdf",
        loader_cls=PyPDFLoader,
    )
    docs = loader.load()
    print(f"✅ 共加载 {len(docs)} 个文档")
    return docs