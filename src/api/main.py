import anyio
import uvicorn
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from api.router.chat import router
from infra.lifespan.init_client import init_connect
from infra.log.logging import logger
from infra.middware.track import add_context_id

app = FastAPI(
    title="Smart Data Analysis API",
    description="智能AI数据分析",
    version="1.0",
    root_path="/smart/data/analysis",
    lifespan=init_connect  # 启动时初始化连接
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_credentials=True,
)

app.add_middleware(
    BaseHTTPMiddleware,
    dispatch=add_context_id
)

app.include_router(router)

if __name__ == '__main__':
    try:
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8080
        )
        server = uvicorn.Server(config)
        anyio.run(server.serve, None)
    except KeyboardInterrupt:
        logger.error("服务器被用户中断，正在关闭...")
    except Exception as e:
        logger.error(f"服务器发生未预期的异常: {e}")
