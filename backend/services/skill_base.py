from __future__ import annotations

import asyncio
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Dict

from PIL import Image

from backend.services.uploads import StoredUpload


@dataclass(slots=True)
class SkillRuntimeOptions:
    detail: str = 'low'
    prompt: str | None = None
    model: str | None = None
    provider_profile_id: str | None = None


@dataclass(slots=True)
class SkillContext:
    upload: StoredUpload
    runtime: SkillRuntimeOptions
    _raw_bytes: bytes | None = None
    _base64_image: str | None = None
    _rgb_image: Image.Image | None = None
    _shared_data: Dict[str, Any] = field(default_factory=dict)
    _bytes_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _base64_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _image_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _shared_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def read_bytes(self) -> bytes:
        if self._raw_bytes is None:
            async with self._bytes_lock:
                if self._raw_bytes is None:
                    self._raw_bytes = await asyncio.to_thread(self.upload.path.read_bytes)
        return self._raw_bytes

    async def read_base64(self) -> str:
        if self._base64_image is None:
            async with self._base64_lock:
                if self._base64_image is None:
                    raw = await self.read_bytes()
                    self._base64_image = base64.b64encode(raw).decode('utf-8')
        return self._base64_image

    async def load_rgb_image(self) -> Image.Image:
        if self._rgb_image is None:
            async with self._image_lock:
                if self._rgb_image is None:
                    raw = await self.read_bytes()

                    def _load() -> Image.Image:
                        with Image.open(BytesIO(raw)) as img:
                            return img.convert('RGB')

                    self._rgb_image = await asyncio.to_thread(_load)
        return self._rgb_image.copy()

    async def merge_shared(self, payload: Dict[str, Any]) -> None:
        if not payload:
            return
        async with self._shared_lock:
            self._shared_data.update(payload)

    async def get_shared(self, key: str, default: Any = None) -> Any:
        async with self._shared_lock:
            return self._shared_data.get(key, default)


@dataclass(slots=True)
class SkillOutcome:
    skill_id: str
    data: Dict[str, Any]
    models: Dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class AnalysisSkill(ABC):
    skill_id: str = ''
    aliases: tuple[str, ...] = ()
    description: str = ''
    dependencies: tuple[str, ...] = ()
    expose_in_ui: bool = True

    @abstractmethod
    async def run(self, context: SkillContext) -> SkillOutcome:
        raise NotImplementedError
