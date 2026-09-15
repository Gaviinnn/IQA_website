from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.services.history_service import clear_history, get_history_batch, list_history

router = APIRouter()


@router.get('/history')
async def history_route(
    cursor: str | None = Query(default=None, description='分页游标'),
    limit: int = Query(default=20, ge=1, le=50, description='返回记录数量，最大 50'),
    order: str = Query(default='desc', description='排序方式 asc/desc'),
    q: str | None = Query(default=None, description='模糊搜索关键字'),
) -> dict[str, Any]:
    order_normalized = order.lower()
    if order_normalized not in {'asc', 'desc'}:
        raise HTTPException(status_code=400, detail='order 仅支持 asc / desc')

    records, next_cursor = await list_history(
        limit=limit,
        order=order_normalized,
        cursor=cursor,
        query=q,
    )

    payload = [
        {
            'batch_id': item.get('batch_id'),
            'filename': item.get('filename'),
            'avg_score': item.get('avg_score'),
            'min_score': item.get('min_score'),
            'max_score': item.get('max_score'),
            'item_count': item.get('item_count'),
            'caption': item.get('caption'),
            'thumbnail': item.get('thumbnail'),
            'image': item.get('image'),
            'degraded': item.get('degraded'),
            'timestamp': item.get('timestamp'),
        }
        for item in records
    ]

    return {'history': payload, 'next_cursor': next_cursor}


@router.get('/history/{batch_id}')
async def history_batch_detail_route(batch_id: str) -> dict[str, Any]:
    batch = await get_history_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail='历史批次不存在或已清理')
    return {'batch': batch}


@router.delete('/history')
async def clear_history_route() -> dict[str, int]:
    removed = await clear_history()
    return {'cleared': removed}
