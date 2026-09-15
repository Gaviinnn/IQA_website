from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.history_service import delete_history

router = APIRouter()


class DeleteRequest(BaseModel):
    batch_id: str = Field(..., description='要删除的 batch_id')


@router.delete('/delete')
async def delete_route(payload: DeleteRequest) -> dict[str, bool]:
    deleted = await delete_history(payload.batch_id.strip())
    if not deleted:
        raise HTTPException(status_code=404, detail='记录不存在或已清理')
    return {'deleted': True}
