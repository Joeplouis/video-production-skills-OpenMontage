"""
VPMS FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vpms import __version__, __product_name__
from vpms.api.routes import router, health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=__product_name__,
        version=__version__,
        description="Control plane for video production orchestration",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    app.include_router(health_router)  # /health at root
    app.include_router(router)  # /api/v1/*

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("vpms.main:app", host="0.0.0.0", port=8090, reload=True)
