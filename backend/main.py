# -*- coding: utf-8 -*-
"""
FastAPI 入口
启动：python backend/main.py
访问：http://localhost:5000/api/health
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.api import router
from backend.database import init_db


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='文献管理助手 API', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)


@app.get('/')
def root():
    return {'message': '文献管理助手 API，接口见 /docs'}


if __name__ == '__main__':
    uvicorn.run('backend.main:app', host='127.0.0.1', port=5000, reload=True)