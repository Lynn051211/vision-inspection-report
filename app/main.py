"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.core.config import settings
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"端口: {settings.PORT}")

    # 预热检测器
    try:
        from app.engine.detector import init_detector
        init_detector()
        logger.info("YOLO 检测器预热完成")
    except Exception as e:
        logger.warning(f"检测器预热失败（首次运行会自动下载模型）: {e}")

    yield
    logger.info("服务关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
