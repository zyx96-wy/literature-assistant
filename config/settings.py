import os
from dotenv import load_dotenv

load_dotenv()

# 项目根目录（根据文件位置动态计算）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# API配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# 文档与向量库路径（基于 BASE_DIR 拼接，别人克隆也能用）
DOCS_DIR = os.path.join(BASE_DIR, "data", "raw")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

# 其他配置不变
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
RETRIEVAL_K = 4
EMBEDDING_MODEL = "text-embedding-v2"
LLM_MODEL = "qwen-turbo"
LLM_TEMPERATURE = 0