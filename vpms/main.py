"""
VPMS FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vpms import __version__, __product_name__
from vpms.api.routes import router, health_router
from vpms.api.routes_golden_path import router as golden_path_router


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
    app.include_router(golden_path_router)  # /api/v1/* (Phase 2 Golden Path)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("vpms.main:app", host="0.0.0.0", port=8090, reload=True)
