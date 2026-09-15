from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv

load_dotenv()

from backend.routes.analyze import router as analyze_router
from backend.routes.delete import router as delete_router
from backend.routes.filtering import router as filtering_router
from backend.routes.history import router as history_router
from backend.routes.providers import router as providers_router
from backend.routes.upload import router as upload_router
from backend.services.health import get_health_status
from backend.services.skill_registry import list_registered_skills

APP_NAME = 'IQA Backend'
APP_VERSION = '1.2.0'
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / 'logs'
UPLOAD_DIR = BASE_DIR / 'uploads'
LOG_FILE = LOG_DIR / 'app.log'


def _get_cors_origins() -> list[str]:
    raw = os.getenv('CORS_ALLOW_ORIGINS', '').strip()
    if raw:
        origins = [item.strip() for item in raw.split(',') if item.strip()]
        if origins:
            return origins
    return [
        'http://127.0.0.1:5173',
        'http://localhost:5173',
        'http://127.0.0.1:4173',
        'http://localhost:4173',
    ]


def _prepare_directories() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
        ],
    )


_prepare_directories()
_configure_logging()

logger = logging.getLogger('iqa.app')

app = FastAPI(title=APP_NAME, version=APP_VERSION)

cors_origins = _get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=['*'],
    allow_headers=['*'],
    allow_credentials=False,
)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

app.include_router(upload_router)
app.include_router(analyze_router)
app.include_router(history_router)
app.include_router(delete_router)
app.include_router(filtering_router)
app.include_router(providers_router)


@app.get('/health')
async def health_check() -> dict[str, Any]:
    try:
        status = await get_health_status()
        return {'status': 'ok', **status}
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception('Health check failed')
        raise HTTPException(status_code=503, detail='Service unavailable') from exc


@app.get('/logs/latest')
async def latest_logs(limit: int = 10) -> dict[str, Any]:
    if not LOG_FILE.exists():
        return {'logs': []}

    entries: list[dict[str, Any]] = []
    try:
        with LOG_FILE.open('r', encoding='utf-8') as handle:
            lines = handle.readlines()[-limit:]
    except OSError:
        return {'logs': []}

    for line in lines:
        entries.append({'message': line.strip()})

    return {'logs': entries}


@app.get('/skills')
async def list_skills() -> dict[str, Any]:
    return {'skills': list_registered_skills()}


@app.get('/')
async def root() -> dict[str, str]:
    return {'message': 'Image Quality Analyzer backend', 'version': APP_VERSION}
