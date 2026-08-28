"""agent-room 后端启动入口。

启动 FastAPI 服务（127.0.0.1:8899），同端口托管前端静态资源。
被 Tauri 作为 sidecar 拉起，也可单独 `python main.py` 运行供浏览器调试。
"""

import os
import sys

import uvicorn

from app.core.config import BASE_DIR, settings

if __name__ == "__main__":
    sys.path.insert(0, str(BASE_DIR))
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
