"""
龙头战法分析系统 - 主入口
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.stocks import router as stocks_router
from app.core.scheduler import setup_scheduler
from app.core.config import LOG_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="龙头战法分析系统",
    description="A股短线龙头识别与信号分析",
    version="0.2.0",
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
    logger.info("龙头战法分析系统启动中...")
    setup_scheduler()
    logger.info("系统启动完成")


@app.on_event("shutdown")
async def shutdown():
    from app.core.scheduler import scheduler
    scheduler.shutdown()
    logger.info("系统已关闭")


@app.get("/")
async def root():
    return {"message": "龙头战法分析系统运行中", "docs": "/docs"}
