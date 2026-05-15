"""Lazy singleton text embedder backed by fastembed + BAAI/bge-m3."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

log = logging.getLogger(__name__)

EMBED_DIM = 1024
_DEFAULT_MODEL = "BAAI/bge-m3"


class FastEmbedder:
    """Wraps fastembed TextEmbedding with lazy initialization and async interface."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: TextEmbedding | None = None

    def _ensure_model(self) -> TextEmbedding:
        if self._model is None:
            from fastembed import TextEmbedding

            log.info("Loading embedding model %s (first use)", self._model_name)
            self._model = TextEmbedding(self._model_name)
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        return [e.tolist() for e in model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* and return a list of float vectors (dim=EMBED_DIM)."""
        return await asyncio.to_thread(self._embed_sync, texts)
