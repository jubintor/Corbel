"""Provider-neutral embedding abstraction for Corbel RAG.

Adheres to ADR-010 (Provider-Neutral Architecture) and Phase 9 RAG specifications.
Supports hosted models (e.g. OpenAI text-embedding-3-small) and deterministic mock embeddings
for reproducible tests, CI pipelines, and offline evaluation.
"""

import hashlib
import logging
import math
import random
from abc import ABC, abstractmethod

import httpx

from corbel.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingException(Exception):
    """Base exception for embedding generation failures."""


class IncompatibleEmbeddingDimensionException(EmbeddingException):
    """Raised when the returned vector dimension does not match expected dimension."""

    def __init__(self, expected: int, received: int) -> None:
        super().__init__(
            f"Embedding dimension mismatch: expected {expected}, received {received}"
        )
        self.expected = expected
        self.received = received


class EmbeddingProvider(ABC):
    """Abstract contract for provider-neutral embedding generation."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the embedding provider (e.g., 'openai', 'fake')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model (e.g., 'text-embedding-3-small')."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of produced vectors (e.g., 1536)."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Version string identifying embedding schema/generation algorithm."""
        ...

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text snippet."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of text snippets."""
        ...


class DeterministicFakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, unit-normalized embedding provider for tests, CI, and local dev without credentials.

    Produces strictly 1536-dimensional float vectors that:
    1. Are deterministic for identical inputs.
    2. Have higher cosine similarity for texts sharing key enterprise terms.
    3. Satisfy Euclidean unit norm: ||v||_2 = 1.0.
    """

    def __init__(self, dimension: int = 1536, model_name: str = "text-embedding-3-small") -> None:
        self._dimension = dimension
        self._model_name = model_name
        self._version = "fake-v1.0"

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def version(self) -> str:
        return self._version

    def _generate_vector(self, text: str) -> list[float]:
        clean_text = text.strip().lower()
        if not clean_text:
            vec = [0.0] * self._dimension
            vec[0] = 1.0
            return vec

        # Use SHA-256 as deterministic seed
        seed_int = int(hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed_int)

        # Base pseudorandom vector
        raw_vec = [rng.gauss(0.0, 1.0) for _ in range(self._dimension)]

        # Semantic term bias: boost specific dimension buckets based on token hashes
        tokens = [t for t in clean_text.split() if len(t) > 2]
        for token in set(tokens):
            tok_seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
            bucket = tok_seed % self._dimension
            raw_vec[bucket] += 3.0

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in raw_vec))
        if norm > 0.0:
            return [round(x / norm, 6) for x in raw_vec]
        vec = [0.0] * self._dimension
        vec[0] = 1.0
        return vec

    async def embed_text(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]


class HostedOpenAIEmbeddingProvider(EmbeddingProvider):
    """Hosted OpenAI embeddings provider leveraging text-embedding-3-small (1536 dims)."""

    def __init__(
        self,
        api_key: str | None,
        model_name: str = "text-embedding-3-small",
        dimension: int = 1536,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._dimension = dimension
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._version = "openai-v1.0"

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def version(self) -> str:
        return self._version

    async def _call_api(self, input_texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingException(
                "OpenAI API key is missing. Set EMBEDDING_API_KEY or OPENAI_API_KEY environment variable."
            )

        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": input_texts,
            "model": self._model_name,
            "dimensions": self._dimension,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        embeddings_data = data.get("data", [])
                        embeddings = [item["embedding"] for item in embeddings_data]
                        for emb in embeddings:
                            if len(emb) != self._dimension:
                                raise IncompatibleEmbeddingDimensionException(
                                    expected=self._dimension, received=len(emb)
                                )
                        return embeddings
                    elif response.status_code in [429, 500, 502, 503, 504] and attempt < self._max_retries:
                        logger.warning(
                            "Transient OpenAI embedding error (status=%d), retrying attempt %d...",
                            response.status_code,
                            attempt + 1,
                        )
                        continue
                    else:
                        raise EmbeddingException(
                            f"OpenAI embedding API failed with HTTP {response.status_code}: {response.text}"
                        )
                except httpx.RequestError as exc:
                    if attempt < self._max_retries:
                        logger.warning("Network error calling OpenAI embeddings, retrying: %s", exc)
                        continue
                    raise EmbeddingException(f"OpenAI embedding connection error: {exc}") from exc

        raise EmbeddingException("Exceeded maximum retries calling OpenAI embeddings.")

    async def embed_text(self, text: str) -> list[float]:
        res = await self._call_api([text])
        return res[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._call_api(texts)


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Resolve configured embedding provider based on environment settings."""
    cfg = settings or get_settings()
    provider_type = cfg.EMBEDDING_PROVIDER.lower().strip()

    if provider_type == "openai":
        api_key = cfg.EMBEDDING_API_KEY or cfg.OPENAI_API_KEY
        return HostedOpenAIEmbeddingProvider(
            api_key=api_key,
            model_name=cfg.EMBEDDING_MODEL,
            dimension=cfg.EMBEDDING_DIMENSIONS,
            timeout_seconds=cfg.AI_REQUEST_TIMEOUT_SECONDS,
            max_retries=cfg.AI_MAX_RETRIES,
        )

    # Default to deterministic fake provider for test/ci/local reliability
    return DeterministicFakeEmbeddingProvider(
        dimension=cfg.EMBEDDING_DIMENSIONS,
        model_name=cfg.EMBEDDING_MODEL,
    )
