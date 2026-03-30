"""
龙头战法分析系统 - 主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.stocks import router as stocks_router
from app.core.scheduler import setup_scheduler

app = FastAPI(
    title="龙头战法分析系统",
    description="A股短线龙头识别与信号分析",
    version="0.1.0"
)

# CORS（前端Vue开发需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(stocks_router)


@app.on_event("startup")
async def startup():
    setup_scheduler()


@app.on_event("shutdown")
async def shutdown():
    from app.core.scheduler import scheduler
    scheduler.shutdown()


@app.get("/")
async def root():
    return {"message": "龙头战法分析系统运行中", "docs": "/docs"}
