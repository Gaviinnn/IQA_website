from __future__ import annotations

from datetime import datetime, timezone

from backend.models.doubao_api import ping as doubao_ping
from backend.services.provider_profiles import get_active_provider_profile, get_model_display_name
from backend.services.skill_registry import list_registered_skills
from ..iqa.models.maniqa_service import ping as maniqa_ping


async def get_health_status() -> dict[str, str]:
  maniqa_ok, doubao_ok = await maniqa_ping(), await doubao_ping()
  active_profile = await get_active_provider_profile()
  return {
    "backend": "running",
    "maniqa_server": "connected" if maniqa_ok else "degraded",
    "doubao_api": "connected" if doubao_ok else "degraded",
    "skills": [item["id"] for item in list_registered_skills()],
    "active_provider": get_model_display_name(active_profile) if active_profile else "not configured",
    "timestamp": datetime.now(timezone.utc).isoformat(),
  }
