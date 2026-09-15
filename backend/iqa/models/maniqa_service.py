from __future__ import annotations
import base64
import contextlib
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TIMM_DISABLE_DOWNLOADS"] = "1"

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable, Tuple

import torch
from PIL import Image
from torchvision import transforms

import pyiqa.archs.maniqa_arch as maniqa_arch_module
from pyiqa.archs.maniqa_arch import MANIQA
from backend.models.doubao_api import call_text_model


logger = logging.getLogger("iqa.maniqa")

MODEL_PATH = Path(__file__).parent / "MANIQA_PIPAL-ae6d356b.pth"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


@contextlib.contextmanager
def _disable_maniqa_vit_pretrain():
  original_create_model = maniqa_arch_module.timm.create_model

  def create_model_without_remote_weights(model_name, *args, **kwargs):
    if model_name == "vit_base_patch8_224":
      kwargs["pretrained"] = False
    return original_create_model(model_name, *args, **kwargs)

  maniqa_arch_module.timm.create_model = create_model_without_remote_weights
  try:
    yield
  finally:
    maniqa_arch_module.timm.create_model = original_create_model


def _safe_torch_load(path: Path, device: torch.device):
  try:
    return torch.load(path, map_location=device, weights_only=True)
  except TypeError:
    return torch.load(path, map_location=device)


@dataclass(slots=True)
class ManiqaResult:
  score: float
  level: str
  explanation: str


class MANIQAService:
  _instance: "MANIQAService | None" = None

  def __init__(self) -> None:
    self.logger = logger
    self.device = DEVICE
    self.model = self._load_model()
    self.transform = transforms.Compose(
      [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
      ]
    )
    # ����������ʱ��Ϊ��һʱ��ͬ�����ʹ�ͬһģ�Ͷ��
    self._eval_lock = asyncio.Lock()

  @classmethod
  def instance(cls) -> "MANIQAService":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  async def evaluate(self, image_path: Path, provider_profile_id: str | None = None) -> ManiqaResult:
    started = time.perf_counter()
    image_base64 = await asyncio.to_thread(self._read_base64, image_path)
    async with self._eval_lock:
      normalized_score = await asyncio.to_thread(self._score_image_sync, image_path)
    level = self._score_to_level(normalized_score)
    rationale = await self._generate_explanation(normalized_score, image_base64, provider_profile_id, level)
    self.logger.info(
      "MANIQA completed | path=%s | score=%.2f | elapsed_ms=%s",
      image_path,
      normalized_score,
      int((time.perf_counter() - started) * 1000),
    )
    return ManiqaResult(score=normalized_score, level=level, explanation=rationale)

  def _load_model(self) -> MANIQA:
      import os

      # ===== 禁止任何联网行为 =====
      os.environ["HF_HUB_OFFLINE"] = "1"
      os.environ["TRANSFORMERS_OFFLINE"] = "1"
      os.environ["TIMM_DISABLE_DOWNLOADS"] = "1"

      # ===== 检查权重文件 =====
      if not MODEL_PATH.exists():
          raise FileNotFoundError(f"MANIQA 权重文件未找到：{MODEL_PATH}")

      self.logger.info("Loading MANIQA model from local weights: %s", MODEL_PATH)

      # ===== 初始化模型结构（仅构建结构，不加载远程权重） =====
      with _disable_maniqa_vit_pretrain():
          model = MANIQA(train_dataset="pipal", pretrained=False)
      if model is None:
          raise RuntimeError("MANIQA 模型结构初始化失败，请检查 timm 或 pyiqa 安装。")

      # ===== 加载本地权重 =====
      checkpoint = _safe_torch_load(MODEL_PATH, self.device)
      state_dict = checkpoint.get("state_dict", checkpoint)

      # 去掉多余的前缀（如 "model.", "module."）
      cleaned_state = {}
      for key, value in state_dict.items():
          new_key = key
          for prefix in ("model.", "module."):
              if new_key.startswith(prefix):
                  new_key = new_key[len(prefix):]
          cleaned_state[new_key] = value

      # ===== 加载权重到模型 =====
      load_result = model.load_state_dict(cleaned_state, strict=False)

      missing = getattr(load_result, "missing_keys", [])
      unexpected = getattr(load_result, "unexpected_keys", [])
      if missing:
          self.logger.warning("MANIQA missing keys: %s", ", ".join(missing))
      if unexpected:
          self.logger.warning("MANIQA unexpected keys: %s", ", ".join(unexpected))

      # ===== 设置设备与推理模式 =====
      model.to(self.device)
      model.eval()

      self.logger.info("MANIQA model loaded successfully on %s", self.device)
      return model

  @staticmethod
  def _read_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("ascii")

  def _score_image_sync(self, image_path: Path) -> float:
    self.logger.info("Running MANIQA inference | path=%s", image_path)

    image = Image.open(image_path).convert("RGB")
    tensor = self.transform(image).unsqueeze(0).to(self.device)

    with torch.no_grad():
      prediction = self.model(tensor)

    score = self._extract_score(prediction)
    score = max(0.0, min(score, 1.0))
    return round(score * 100.0, 2)

  @staticmethod
  def _extract_score(prediction: torch.Tensor | Iterable[torch.Tensor] | dict) -> float:
    if isinstance(prediction, torch.Tensor):
      tensor = prediction
    elif isinstance(prediction, (list, tuple)) and prediction:
      tensor = prediction[0]
    elif isinstance(prediction, dict):
      for key in ("score", "quality", "qa_score"):
        if key in prediction:
          return float(prediction[key])
      raise ValueError("MANIQA dict output missing score key")
    else:
      raise ValueError("Unexpected MANIQA output type")

    return float(tensor.squeeze().item())

  @staticmethod
  def _score_to_level(score: float) -> str:
    if score >= 80:
      return "\u4f18\u79c0"
    elif score >= 60:
      return "\u826f\u597d"
    elif score >= 40:
      return "\u4e00\u822c"
    return "\u8f83\u5dee"

  @staticmethod
  def _build_quality_prompt(score: float) -> str:
    return (
        "图像质量评估协助：\n"
        f"- 图像质量得分：{score:.1f}/100\n"
        "- 请仅基于图像的质量特征生成一句简短的中文描述，"
        "重点分析影响该图片质量分数的方面，"
        "不要提及图像内容或场景，也不要重复分数。"
    )

  async def _generate_explanation(
    self,
    score: float,
    image_base64: str | None,
    provider_profile_id: str | None,
    level: str,
  ) -> str:
    prompt = (
        self._build_quality_prompt(score)
    )

    try:
      description = await call_text_model(
        prompt,
        image_base64=image_base64,
        profile_id=provider_profile_id,
      )
      if not isinstance(description, str) or not description.strip():
        raise ValueError("empty response")
      return description.strip()
    except Exception as exc:  # pragma: no cover - defensive
      logger.warning("Failed to generate quality description | score=%.2f | error=%s", score, exc)
      return f"\uff08\u81ea\u52a8\u63cf\u8ff0\u5931\u8d25\uff09\u56fe\u50cf\u8d28\u91cf\u4e3a {level}\u3002"

async def evaluate_image(image_path: Path, provider_profile_id: str | None = None) -> ManiqaResult:
  service = MANIQAService.instance()
  return await service.evaluate(image_path, provider_profile_id)


async def ping() -> bool:
  try:
    service = MANIQAService.instance()
    await asyncio.to_thread(lambda: MODEL_PATH.exists())
    service.logger.debug("MANIQA ping ok")
    return True
  except Exception:  # pragma: no cover - defensive
    logger.exception("MANIQA ping failed")
    return False
