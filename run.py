# -*- coding: utf-8 -*-
"""
文献管理助手 · 统一启动入口
============================

用法：
    python run.py

它会做：
    1. 检查 .env 里的 DASHSCOPE_API_KEY
    2. 检查依赖是否装齐
    3. 启动 FastAPI（backend/main.py）
"""
import os
import sys
import subprocess


ROOT = os.path.dirname(os.path.abspath(__file__))


def check_env():
    """检查 .env"""
    env_path = os.path.join(ROOT, '.env')
    if not os.path.exists(env_path):
        print('❌ 找不到 .env 文件')
        print(f'   请在 {ROOT} 下创建 .env，内容：')
        print('   DASHSCOPE_API_KEY=sk-你的key')
        sys.exit(1)

    # 读 .env
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'DASHSCOPE_API_KEY' not in content:
        print('❌ .env 里没有 DASHSCOPE_API_KEY')
        sys.exit(1)

    # 检查 key 是否为空
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('DASHSCOPE_API_KEY'):
            value = line.split('=', 1)[1].strip() if '=' in line else ''
            if not value or value == '':
                print('❌ DASHSCOPE_API_KEY 为空')
                sys.exit(1)
            if not value.startswith('sk-'):
                print(f'⚠️  DASHSCOPE_API_KEY 不以 sk- 开头，可能不对：{value[:10]}...')
            break

    print('✅ .env 检查通过')


def check_deps():
    """检查关键依赖"""
    missing = []
    try:
        import fastapi
    except ImportError:
        missing.append('fastapi')
    try:
        import uvicorn
    except ImportError:
        missing.append('uvicorn')
    try:
        import langchain
    except ImportError:
        missing.append('langchain')
    try:
        import langchain_community
    except ImportError:
        missing.append('langchain-community')
    try:
        import langchain_chroma
    except ImportError:
        missing.append('langchain-chroma')
    try:
        import chromadb
    except ImportError:
        missing.append('chromadb')
    try:
        import fitz
    except ImportError:
        missing.append('pymupdf')
    try:
        import dashscope
    except ImportError:
        missing.append('dashscope')

    if missing:
        print('❌ 缺少依赖：')
        for m in missing:
            print(f'   - {m}')
        print('\n安装：pip install -r requirements.txt')
        sys.exit(1)

    print('✅ 依赖检查通过')


def main():
    print('=' * 50)
    print('📚 文献管理助手 · 启动中...')
    print('=' * 50)

    # 1. 环境检查
    check_env()

    # 2. 依赖检查
    check_deps()

    # 3. 启动 FastAPI
    print('\n🚀 启动后端服务...')
    print('   访问 http://127.0.0.1:5000/api/health 测试')
    print('   API 文档：http://127.0.0.1:5000/docs')
    print('   前端页面：打开 demo/index.html')
    print('   停止：Ctrl+C\n')


    import uvicorn
    uvicorn.run(
        'backend.main:app',
        host='127.0.0.1',
        port=5000,
        reload=True,           # run.py 不重载，重启就重新跑
    )


if __name__ == '__main__':
    main()