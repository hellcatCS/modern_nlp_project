"""Локальный эмбеддер с Hugging Face при недоступности OpenAI API по региону."""
from __future__ import annotations

import logging
import os

from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

# Уменьшает предупреждения tokenizers при fork
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class SentenceTransformerEmbeddings(Embeddings):
    """Обёртка над sentence-transformers для LangChain."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        logger.info("Загрузка локального эмбеддера с Hugging Face: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        emb = self._model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return emb.tolist()

    def embed_query(self, text: str) -> list[float]:
        emb = self._model.encode(
            [text],
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return emb[0].tolist()


def is_openai_geo_blocked_error(exc: BaseException) -> bool:
    """403 unsupported_country_region_territory от OpenAI (SDK может не дублировать код в str)."""
    try:
        from openai import PermissionDeniedError as OpenAIPermissionDenied
    except ImportError:
        OpenAIPermissionDenied = ()

    if OpenAIPermissionDenied and isinstance(exc, OpenAIPermissionDenied):
        code = _extract_openai_error_code(exc)
        if code == "unsupported_country_region_territory":
            return True

    code = _extract_openai_error_code(exc)
    if code == "unsupported_country_region_territory":
        return True
    msg = str(exc).lower()
    if "unsupported_country_region_territory" in msg:
        return True
    if "country, region, or territory not supported" in msg:
        return True
    return False


def _extract_openai_error_code(exc: BaseException) -> str | None:
    # OpenAI SDK v1+: тело ошибки в разных полях
    for attr in ("body", "_body"):
        raw = getattr(exc, attr, None)
        if isinstance(raw, dict):
            err = raw.get("error")
            if isinstance(err, dict) and err.get("code"):
                return str(err["code"])
            if raw.get("code"):
                return str(raw["code"])
        if isinstance(raw, str):
            try:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    err = parsed.get("error")
                    if isinstance(err, dict) and err.get("code"):
                        return str(err["code"])
            except Exception:
                pass

    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            data = resp.json()
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict) and err.get("code"):
                return str(err["code"])
        except Exception:
            pass
    return None
