from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiosqlite

from .uploads import remove_upload_files

logger = logging.getLogger('iqa.history')

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', str(DEFAULT_UPLOAD_DIR)))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_DB_FILE = Path(os.getenv('HISTORY_DB_FILE', str(UPLOAD_DIR / 'history.db')))
HISTORY_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

HISTORY_TTL_HOURS = int(os.getenv('HISTORY_TTL_HOURS', '24'))
HISTORY_MAX_RECORDS = int(os.getenv('HISTORY_MAX_RECORDS', '500'))

_schema_lock = asyncio.Lock()
_schema_ready = False


def _now() -> datetime:
    """返回当前 UTC 时间，保持与旧逻辑兼容。"""
    return datetime.now(timezone.utc)


def _cursor_key(record: Dict[str, Any]) -> str:
    """批次分页游标格式。"""
    return f"{record['timestamp']}|{record['batch_id']}"


async def _ensure_schema() -> None:
    """懒加载初始化 SQLite 表结构。"""
    global _schema_ready
    if _schema_ready:
        return

    async with _schema_lock:
        if _schema_ready:
            return
        async with aiosqlite.connect(HISTORY_DB_FILE) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    upload_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    filename TEXT,
                    score REAL,
                    caption TEXT,
                    objects TEXT,
                    thumbnail TEXT,
                    image TEXT,
                    timestamp TEXT NOT NULL,
                    result TEXT
                )
                """
            )
            columns_cursor = await db.execute("PRAGMA table_info(history)")
            columns = {row[1] for row in await columns_cursor.fetchall()}
            await columns_cursor.close()
            if 'batch_id' not in columns:
                await db.execute("ALTER TABLE history ADD COLUMN batch_id TEXT")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_batch_id ON history(batch_id)"
            )
            await db.commit()
        _schema_ready = True


async def _purge_expired(db: aiosqlite.Connection) -> None:
    """清理超过保留时长的记录（只移除历史条目，文件由定期任务处理）。"""
    expiry = (_now() - timedelta(hours=HISTORY_TTL_HOURS)).isoformat()
    await db.execute("DELETE FROM history WHERE timestamp < ?", (expiry,))


async def _enforce_limit(db: aiosqlite.Connection) -> None:
    """超过最大数量时，按时间最旧顺序删除多余记录。"""
    cursor = await db.execute("SELECT COUNT(1) FROM history")
    total = (await cursor.fetchone())[0]
    await cursor.close()
    if total <= HISTORY_MAX_RECORDS:
        return

    overflow = total - HISTORY_MAX_RECORDS
    cursor = await db.execute(
        """
        SELECT upload_id FROM history
        ORDER BY timestamp ASC, upload_id ASC
        LIMIT ?
        """,
        (overflow,),
    )
    stale_ids = [row[0] for row in await cursor.fetchall()]
    await cursor.close()

    await db.executemany("DELETE FROM history WHERE upload_id = ?", ((uid,) for uid in stale_ids))


def _hydrate_row(row: aiosqlite.Row) -> Dict[str, Any]:
    """还原成与旧版 JSON 结构一致的字典。"""
    objects_raw = row['objects']
    result_raw = row['result']
    return {
        'upload_id': row['upload_id'],
        'batch_id': row['batch_id'] or row['upload_id'],
        'filename': row['filename'],
        'score': row['score'],
        'caption': row['caption'],
        'objects': json.loads(objects_raw) if objects_raw else [],
        'thumbnail': row['thumbnail'],
        'image': row['image'],
        'timestamp': row['timestamp'],
        'result': json.loads(result_raw) if result_raw else None,
    }


async def store_result(record: Dict[str, Any]) -> None:
    """保存分析快照，保持幂等（相同 upload_id 覆盖）。"""
    await _ensure_schema()

    payload = {
        'upload_id': record['upload_id'],
        'batch_id': record.get('batch_id') or record['upload_id'],
        'filename': record.get('filename'),
        'score': record.get('score'),
        'caption': record.get('caption'),
        'objects': json.dumps(record.get('objects') or [], ensure_ascii=False),
        'thumbnail': record.get('thumbnail'),
        'image': record.get('image'),
        'timestamp': record.get('timestamp') or _now().isoformat(),
        'result': json.dumps(record.get('result') or {}, ensure_ascii=False),
    }

    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO history (
                upload_id, batch_id, filename, score, caption, objects,
                thumbnail, image, timestamp, result
            ) VALUES (
                :upload_id, :batch_id, :filename, :score, :caption, :objects,
                :thumbnail, :image, :timestamp, :result
            )
            ON CONFLICT(upload_id) DO UPDATE SET
                batch_id = excluded.batch_id,
                filename = excluded.filename,
                score = excluded.score,
                caption = excluded.caption,
                objects = excluded.objects,
                thumbnail = excluded.thumbnail,
                image = excluded.image,
                timestamp = excluded.timestamp,
                result = excluded.result
            """,
            payload,
        )
        await _purge_expired(db)
        await _enforce_limit(db)
        await db.commit()


async def list_history(
    *,
    limit: int = 20,
    order: str = 'desc',
    cursor: str | None = None,
    query: str | None = None,
) -> Tuple[List[Dict[str, Any]], str | None]:
    """按批次分页读取历史记录。"""
    await _ensure_schema()
    order = order.lower()
    order = 'asc' if order == 'asc' else 'desc'

    comparator = '>' if order == 'asc' else '<'
    ordering = 'ASC' if order == 'asc' else 'DESC'

    conditions: List[str] = []
    params: List[Any] = []

    if query:
        keyword = f"%{query.lower()}%"
        conditions.append(
            "(LOWER(filename) LIKE ? OR LOWER(caption) LIKE ? OR LOWER(objects) LIKE ?)"
        )
        params.extend([keyword, keyword, keyword])

    if cursor:
        try:
            cursor_timestamp, cursor_batch_id = cursor.split('|', 1)
        except ValueError:
            logger.warning('Invalid history cursor received: %s', cursor)
        else:
            conditions.append(f"(timestamp, COALESCE(batch_id, upload_id)) {comparator} (?, ?)")
            params.extend([cursor_timestamp, cursor_batch_id])

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ''
    fetch_size = max(0, limit) + 1  # 多取一条用于判断是否还有下一页

    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        await _purge_expired(db)
        await db.commit()

        cursor_obj = await db.execute(
            f"""
            SELECT
                COALESCE(batch_id, upload_id) AS batch_id,
                MAX(timestamp) AS timestamp,
                COUNT(*) AS item_count,
                MAX(CASE WHEN score IS NOT NULL THEN score ELSE -1 END) AS max_score,
                MIN(CASE WHEN score IS NOT NULL THEN score ELSE 101 END) AS min_score,
                AVG(score) AS avg_score,
                SUM(
                    CASE
                        WHEN json_extract(result, '$.meta.degraded') = 1 THEN 1
                        ELSE 0
                    END
                ) AS degraded_count,
                SUBSTR(GROUP_CONCAT(filename, ' / '), 1, 240) AS filenames,
                MAX(CASE WHEN thumbnail IS NOT NULL AND thumbnail != '' THEN thumbnail ELSE '' END) AS thumbnail,
                MAX(CASE WHEN image IS NOT NULL AND image != '' THEN image ELSE '' END) AS image,
                MAX(CASE WHEN caption IS NOT NULL AND caption != '' THEN caption ELSE '' END) AS caption
            FROM history
            {where_sql}
            GROUP BY COALESCE(batch_id, upload_id)
            ORDER BY timestamp {ordering}, batch_id {ordering}
            LIMIT ?
            """,
            (*params, fetch_size),
        )
        rows = await cursor_obj.fetchall()
        await cursor_obj.close()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    history_list = []
    for row in page_rows:
        item_count = row['item_count'] or 0
        avg_score = row['avg_score']
        min_score = None if row['min_score'] in (None, 101) else row['min_score']
        max_score = None if row['max_score'] in (None, -1) else row['max_score']
        history_list.append(
            {
                'batch_id': row['batch_id'],
                'timestamp': row['timestamp'],
                'item_count': item_count,
                'avg_score': round(avg_score, 2) if isinstance(avg_score, (int, float)) else None,
                'min_score': round(min_score, 2) if isinstance(min_score, (int, float)) else None,
                'max_score': round(max_score, 2) if isinstance(max_score, (int, float)) else None,
                'caption': row['caption'],
                'thumbnail': row['thumbnail'] or None,
                'image': row['image'] or None,
                'degraded': bool(row['degraded_count']),
                'filename': row['filenames'] or row['batch_id'],
            }
        )

    next_cursor = _cursor_key(history_list[-1]) if has_more and history_list else None
    return history_list, next_cursor


async def get_history_batch(batch_id: str) -> Dict[str, Any] | None:
    await _ensure_schema()
    normalized_batch_id = batch_id.strip()
    if not normalized_batch_id:
        return None

    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        await _purge_expired(db)
        await db.commit()
        cursor = await db.execute(
            """
            SELECT upload_id, batch_id, filename, score, caption, objects,
                   thumbnail, image, timestamp, result
            FROM history
            WHERE COALESCE(batch_id, upload_id) = ?
            ORDER BY timestamp DESC, upload_id DESC
            """,
            (normalized_batch_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

    if not rows:
        return None

    items = [_hydrate_row(row) for row in rows]
    scores = [item.get('score') for item in items if isinstance(item.get('score'), (int, float))]
    return {
        'batch_id': normalized_batch_id,
        'timestamp': items[0].get('timestamp'),
        'item_count': len(items),
        'avg_score': round(sum(scores) / len(scores), 2) if scores else None,
        'items': items,
    }


async def delete_history(batch_id: str) -> bool:
    """按批次删除历史记录并清理对应文件。"""
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT upload_id FROM history
            WHERE COALESCE(batch_id, upload_id) = ?
        """
        select_cursor = await db.execute(query, (batch_id,))
        rows = await select_cursor.fetchall()
        await select_cursor.close()
        upload_ids = [row['upload_id'] for row in rows]
        if not upload_ids:
            return False

        cursor = await db.execute(
            "DELETE FROM history WHERE COALESCE(batch_id, upload_id) = ?",
            (batch_id,),
        )
        affected = cursor.rowcount or 0
        await cursor.close()
        await db.commit()

    if affected:
        for upload_id in upload_ids:
            await remove_upload_files(upload_id)
        logger.info('History batch deleted | batch_id=%s | count=%s', batch_id, len(upload_ids))
        return True
    return False


async def clear_history() -> int:
    """清空历史记录，同时删除已保存文件。"""
    await _ensure_schema()
    async with aiosqlite.connect(HISTORY_DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT upload_id FROM history")
        upload_ids = [row['upload_id'] for row in await cursor.fetchall()]
        await cursor.close()

        await db.execute("DELETE FROM history")
        await db.commit()

    for upload_id in upload_ids:
        await remove_upload_files(upload_id)

    logger.info('History cleared | count=%s', len(upload_ids))
    return len(upload_ids)


async def persist_analysis_result(result: Dict[str, Any]) -> None:
    """保持旧接口不变，对分析结果进行标准化后写入。"""
    quality = result.get('quality') or {}
    quality_fusion = result.get('quality_fusion') or {}
    content = result.get('content') or {}
    snapshot = result.get('snapshot') or {}
    history_record = {
        'upload_id': result.get('upload_id'),
        'batch_id': (result.get('meta') or {}).get('batch_id') or result.get('upload_id'),
        'filename': result.get('filename'),
        'score': quality_fusion.get('final_score') if quality_fusion.get('final_score') is not None else quality.get('score'),
        'caption': content.get('caption'),
        'objects': [obj.get('label') for obj in content.get('objects', []) if obj.get('label')],
        'thumbnail': snapshot.get('thumbnail'),
        'image': snapshot.get('image'),
        'timestamp': snapshot.get('saved_at') or _now().isoformat(),
        'result': result,
    }
    await store_result(history_record)
