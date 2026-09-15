from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

logger = logging.getLogger('iqa.uploads')

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', str(DEFAULT_UPLOAD_DIR)))
PUBLIC_PREFIX = '/uploads'
ALLOWED_TYPES: dict[str, str] = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
}
SAVE_FORMATS: dict[str, tuple[str, dict[str, Any]]] = {
    'image/jpeg': ('JPEG', {'quality': 92, 'optimize': True}),
    'image/png': ('PNG', {'optimize': True}),
    'image/webp': ('WEBP', {'quality': 90, 'method': 4}),
}
MAX_FILE_MB = int(os.getenv('MAX_FILE_MB', '20'))
MAX_PIXELS = int(os.getenv('MAX_PIXELS', '10000'))
MAX_UPLOAD_DIM = int(os.getenv('MAX_UPLOAD_DIM', '1200'))
THUMB_SIZE = int(os.getenv('THUMB_MAX', '320'))
METADATA_SUFFIX = '.json'
RESAMPLE_MODE = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_metadata_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_path(path: Path) -> str:
    return f"{PUBLIC_PREFIX}/{path.name}"


@dataclass(slots=True)
class StoredUpload:
    upload_id: str
    filename: str
    mime: str
    size_kb: float
    width: int
    height: int
    timestamp: datetime
    path: Path
    thumbnail_path: Path
    original_path: Path | None = None
    original_size_kb: float | None = None
    original_width: int | None = None
    original_height: int | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            'upload_id': self.upload_id,
            'filename': self.filename,
            'mime': self.mime,
            'size_kb': round(self.size_kb, 2),
            'width': self.width,
            'height': self.height,
            'thumbnail': _public_path(self.thumbnail_path),
            'timestamp': self.timestamp.isoformat(),
        }

    def to_metadata_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['path'] = self.path.name
        data['thumbnail_path'] = self.thumbnail_path.name
        data['original_path'] = self.original_path.name if self.original_path else None
        return data


async def save_upload(file: UploadFile) -> StoredUpload:
    if file.content_type not in ALLOWED_TYPES:
        logger.warning('Unsupported file type | type=%s', file.content_type)
        raise HTTPException(status_code=415, detail='仅支持 JPG / PNG / WEBP 图片')

    data = await file.read()
    original_data = data
    original_size_bytes = len(original_data)
    size_bytes = len(data)
    if size_bytes == 0:
        raise HTTPException(status_code=422, detail='文件内容为空')
    if size_bytes > MAX_FILE_MB * 1024 * 1024:
        logger.warning('File too large | size=%s', size_bytes)
        raise HTTPException(status_code=413, detail=f'文件不得超过 {MAX_FILE_MB} MB')

    try:
        with Image.open(BytesIO(data)) as validator:
            validator.verify()
        with Image.open(BytesIO(data)) as details:
            width, height = details.size
        original_width, original_height = width, height
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception('Image validation failed')
        raise HTTPException(status_code=422, detail='图片校验失败') from exc

    if max(width, height) > MAX_PIXELS:
        raise HTTPException(status_code=422, detail=f'图片边长不得超过 {MAX_PIXELS} 像素')

    data, width, height, resized = await _resize_image_if_needed(
        data, file.content_type, width, height
    )
    size_bytes = len(data)

    upload_id = _now().strftime('ul_%Y%m%d_%H%M%S_') + secrets.token_hex(4)
    suffix = ALLOWED_TYPES[file.content_type]
    filename = file.filename or f'{upload_id}{suffix}'

    image_path = UPLOAD_DIR / f'{upload_id}{suffix}'
    thumb_path = UPLOAD_DIR / f'{upload_id}_thumb.jpg'
    original_path = UPLOAD_DIR / f'{upload_id}_orig{suffix}'
    metadata_path = UPLOAD_DIR / f'{upload_id}{METADATA_SUFFIX}'

    async with aiofiles.open(image_path, 'wb') as handle:
        await handle.write(data)
    async with aiofiles.open(original_path, 'wb') as handle:
        await handle.write(original_data)

    await _write_thumbnail(data, thumb_path)

    stored = StoredUpload(
        upload_id=upload_id,
        filename=filename,
        mime=file.content_type,
        size_kb=size_bytes / 1024,
        width=width,
        height=height,
        timestamp=_now(),
        path=image_path,
        thumbnail_path=thumb_path,
        original_path=original_path,
        original_size_kb=original_size_bytes / 1024,
        original_width=original_width,
        original_height=original_height,
    )

    async with _metadata_lock:
        payload = json.dumps(stored.to_metadata_dict(), ensure_ascii=False, indent=2)
        await asyncio.to_thread(metadata_path.write_text, payload, 'utf-8')

    if resized:
        logger.info(
            'Resized upload | id=%s | original=%sx%s -> %sx%s',
            upload_id,
            original_width,
            original_height,
            width,
            height,
        )
    logger.info('File uploaded | id=%s | path=%s', upload_id, image_path)
    return stored


async def _write_thumbnail(raw: bytes, path: Path) -> None:
    def _create() -> None:
        buffer = BytesIO(raw)
        with Image.open(buffer) as img:
            thumb = img.copy().convert('RGB')
            thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
            out = BytesIO()
            thumb.save(out, format='JPEG', quality=82)
            path.write_bytes(out.getvalue())

    await asyncio.to_thread(_create)


async def load_metadata(upload_id: str) -> StoredUpload | None:
    metadata_path = UPLOAD_DIR / f'{upload_id}{METADATA_SUFFIX}'
    if not metadata_path.exists():
        return None

    def _load() -> StoredUpload | None:
        try:
            payload = json.loads(metadata_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            logger.warning('Invalid metadata json | id=%s', upload_id)
            return None

        path_name = payload.get('path')
        thumb_name = payload.get('thumbnail_path')
        original_path_name = payload.get('original_path')
        timestamp = datetime.fromisoformat(payload['timestamp'])
        return StoredUpload(
            upload_id=payload['upload_id'],
            filename=payload.get('filename', path_name),
            mime=payload.get('mime', 'image/jpeg'),
            size_kb=float(payload.get('size_kb', 0.0)),
            width=int(payload.get('width', 0)),
            height=int(payload.get('height', 0)),
            timestamp=timestamp,
            path=UPLOAD_DIR / path_name,
            thumbnail_path=UPLOAD_DIR / thumb_name,
            original_path=(UPLOAD_DIR / original_path_name) if original_path_name else None,
            original_size_kb=float(payload.get('original_size_kb', 0.0)) if payload.get('original_size_kb') is not None else None,
            original_width=int(payload.get('original_width', 0)) if payload.get('original_width') is not None else None,
            original_height=int(payload.get('original_height', 0)) if payload.get('original_height') is not None else None,
        )

    return await asyncio.to_thread(_load)


async def remove_upload_files(upload_id: str) -> None:
    patterns = (
        f'{upload_id}.jpg',
        f'{upload_id}.png',
        f'{upload_id}.webp',
        f'{upload_id}_orig.jpg',
        f'{upload_id}_orig.png',
        f'{upload_id}_orig.webp',
        f'{upload_id}_thumb.jpg',
        f'{upload_id}{METADATA_SUFFIX}',
    )
    for name in patterns:
        path = UPLOAD_DIR / name
        if not path.exists():
            continue
        try:
            await asyncio.to_thread(path.unlink)
        except OSError:
            logger.warning('Failed to delete file | path=%s', path)


def _format_options_for_mime(mime: str) -> tuple[str, dict[str, Any]]:
    fmt, options = SAVE_FORMATS.get(mime, ('JPEG', {'quality': 92, 'optimize': True}))
    return fmt, dict(options)


async def _resize_image_if_needed(
    raw: bytes, mime: str, width: int, height: int
) -> tuple[bytes, int, int, bool]:
    if MAX_UPLOAD_DIM <= 0 or max(width, height) <= MAX_UPLOAD_DIM:
        return raw, width, height, False

    def _resize() -> tuple[bytes, int, int, bool]:
        with Image.open(BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            src_w, src_h = img.size
            fmt, save_kwargs = _format_options_for_mime(mime)
            longest = max(src_w, src_h)
            if longest <= MAX_UPLOAD_DIM:
                return raw, width, height, False

            scale = MAX_UPLOAD_DIM / float(longest)
            new_size = (
                max(1, int(round(src_w * scale))),
                max(1, int(round(src_h * scale))),
            )
            resized = img.resize(new_size, RESAMPLE_MODE)
            if fmt == 'JPEG' and resized.mode not in ('RGB', 'L'):
                resized = resized.convert('RGB')
            out = BytesIO()
            resized.save(out, format=fmt, **save_kwargs)
            return out.getvalue(), resized.width, resized.height, True

    new_bytes, new_w, new_h, resized = await asyncio.to_thread(_resize)
    return new_bytes, new_w, new_h, resized
