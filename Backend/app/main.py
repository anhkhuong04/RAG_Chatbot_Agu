import os
import logging
from logging.config import dictConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def setup_logging() -> None:
    """Configure application logging so app.* loggers are visible under uvicorn."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": log_format,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": log_level,
            },
            "loggers": {
                "app": {
                    "handlers": ["console"],
                    "level": log_level,
                    "propagate": False,
                }
            },
        }
    )


setup_logging()
logger = logging.getLogger("app.main")

# Import API routers
from app.api.v1 import api_router

# Create FastAPI app
app = FastAPI(
    title="University RAG Chatbot API",
    description="API for University Knowledge Base Management and Chat",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_log() -> None:
    logger.info("Backend started successfully")


@app.get("/")
async def root():
    return {
        "status": "running",
        "service": "University RAG Chatbot API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "api": "up"
        }
    }
