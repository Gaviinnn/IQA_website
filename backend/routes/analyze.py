from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.services.analyze_service import analyze_uploads

router = APIRouter()
logger = logging.getLogger('iqa.analyze.route')

VALID_DETAILS = {'low', 'high', 'auto'}


class AnalyzeRequest(BaseModel):
    upload_id: str | None = Field(None, description='单个上传文件 ID')
    upload_ids: List[str] | None = Field(None, description='上传文件 ID 列表')
    skills: List[str] | None = Field(None, description='要执行的技能列表')
    detail: str = Field('low', description='图像分辨率 detail 参数')
    model: str | None = Field(None, description='覆盖活跃 Provider Profile 的模型名，可选')
    prompt: str | None = Field(None, description='自定义识别提示词，可选')
    provider_profile_id: str | None = Field(None, description='指定本次分析使用的 Provider Profile')

    @field_validator('upload_ids')
    @classmethod
    def ensure_ids(cls, value: List[str] | None) -> List[str] | None:
        if value is None:
            return None
        filtered = [item.strip() for item in value if item and item.strip()]
        return filtered or None

    @field_validator('skills')
    @classmethod
    def normalize_skills(cls, value: List[str] | None) -> List[str] | None:
        if value is None:
            return None
        filtered = [item.strip().lower() for item in value if item and item.strip()]
        return filtered or None

    @field_validator('detail')
    @classmethod
    def validate_detail(cls, value: str) -> str:
        detail = value.lower()
        if detail not in VALID_DETAILS:
            raise ValueError('detail 仅支持 low / high / auto')
        return detail

    @model_validator(mode='after')
    def validate_payload(self) -> 'AnalyzeRequest':
        normalized_ids: List[str] = []
        if self.upload_id and self.upload_id.strip():
            normalized_ids.append(self.upload_id.strip())
        if self.upload_ids:
            normalized_ids.extend(self.upload_ids)

        deduped = list(dict.fromkeys(normalized_ids))
        if not deduped:
            raise ValueError('upload_id 或 upload_ids 至少提供一个')

        self.upload_ids = deduped
        self.upload_id = deduped[0]
        return self


@router.post('/analyze')
async def analyze_route(payload: AnalyzeRequest) -> dict[str, Any]:
    try:
        results = await analyze_uploads(
            payload.upload_ids or [],
            detail=payload.detail,
            prompt=payload.prompt,
            model=payload.model,
            skills=payload.skills,
            provider_profile_id=payload.provider_profile_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception('Analyze route failed')
        raise HTTPException(status_code=500, detail='分析失败，请稍后再试') from exc

    return {'results': results}
