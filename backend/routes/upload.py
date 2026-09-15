from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services.uploads import save_upload

router = APIRouter()
logger = logging.getLogger('iqa.upload.route')
UPLOAD_BATCH_CONCURRENCY = max(1, int(os.getenv('UPLOAD_BATCH_CONCURRENCY', '3')))


@router.post('/upload')
async def upload_images(files: List[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail='未检测到文件')

    sem = asyncio.Semaphore(min(UPLOAD_BATCH_CONCURRENCY, len(files)))

    async def _save(file: UploadFile) -> dict:
        async with sem:
            stored = await save_upload(file)
            return stored.to_public_dict()

    saved_items = await asyncio.gather(*[_save(file) for file in files])

    logger.info('Uploaded batch | count=%s', len(saved_items))
    return {'uploads': saved_items}
