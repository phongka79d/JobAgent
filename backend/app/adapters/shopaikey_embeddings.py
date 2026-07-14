"""Sole production ShopAIKey embedding adapter (Plan 5 §7.5 / Master §17.1).

Owns OpenAI-compatible transport to ``POST /v1/embeddings`` with locked
``text-embedding-3-small``, ``dimensions=1536``, and ``encoding_format=float``.
Validates ordered finite vectors through :mod:`app.schemas.embeddings`. No
model/dimension fallback, no Candidate builder, no persistence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Final

from langchain_openai import OpenAIEmbeddings

from app.core.settings import Settings, get_settings
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    LOCKED_ENCODING_FORMAT,
    EmbeddingVectorError,
    require_locked_embedding_contract,
    validate_embedding_data_list,
)
from app.services.provider_retry import is_rate_limit_error, is_timeout_error

# Stable sanitized transport/validation codes (no secrets or full bodies).
FAILURE_EMBEDDING_TIMEOUT: Final[str] = "EMBEDDING_TIMEOUT"
FAILURE_EMBEDDING_RATE_LIMIT: Final[str] = "EMBEDDING_RATE_LIMIT"
FAILURE_EMBEDDING_INVALID_RESPONSE: Final[str] = "EMBEDDING_INVALID_RESPONSE"

# Default request timeout for embedding calls (seconds).
DEFAULT_EMBEDDING_TIMEOUT_S: Final[float] = 60.0

# Injected create callable: (input, model, dimensions, encoding_format) -> response.
EmbeddingCreateFn = Callable[..., Any]


class EmbeddingAdapterError(Exception):
    """Stable sanitized embedding transport or validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _guard_settings(settings: Settings) -> None:
    """Reject alternate model/dimension config before any client work."""
    try:
        require_locked_embedding_contract(
            model=settings.EMBEDDING_MODEL,
            dimensions=int(settings.EMBEDDING_DIMENSIONS),
        )
    except EmbeddingVectorError as exc:
        raise EmbeddingAdapterError(
            FAILURE_EMBEDDING_INVALID_RESPONSE,
            f"invalid embedding configuration ({exc.code})",
        ) from exc


def build_shopaikey_embeddings(
    settings: Settings | None = None,
) -> OpenAIEmbeddings:
    """Build ``OpenAIEmbeddings`` from the root Settings boundary.

    Construction performs no network I/O. Rejects any settings model/dimensions
    other than the locked contract, then builds with locked wire values only.
    Token-length pre-chunking is disabled so inputs are sent as text with
    explicit ``dimensions`` on the wire.
    """
    cfg = settings if settings is not None else get_settings()
    _guard_settings(cfg)
    base_url = str(cfg.SHOPAIKEY_BASE_URL).rstrip("/")
    return OpenAIEmbeddings(
        model=LOCKED_EMBEDDING_MODEL,
        dimensions=LOCKED_EMBEDDING_DIMENSIONS,
        api_key=cfg.SHOPAIKEY_API_KEY,
        base_url=base_url,
        check_embedding_ctx_length=False,
        timeout=DEFAULT_EMBEDDING_TIMEOUT_S,
        model_kwargs={"encoding_format": LOCKED_ENCODING_FORMAT},
    )


def _response_to_data(response: Any) -> Any:
    """Normalize OpenAI SDK / dict embedding responses to a ``data`` list."""
    if isinstance(response, dict):
        return response.get("data")
    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            return dumped.get("data")
    data = getattr(response, "data", None)
    if data is None:
        raise EmbeddingAdapterError(
            FAILURE_EMBEDDING_INVALID_RESPONSE,
            "missing embedding data",
        )
    # SDK object list: map to dicts with index/embedding for the validator.
    items: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            items.append(item)
            continue
        items.append(
            {
                "index": getattr(item, "index"),
                "embedding": getattr(item, "embedding"),
            }
        )
    return items


def _classify_transport_error(exc: BaseException) -> EmbeddingAdapterError:
    if is_timeout_error(exc):
        return EmbeddingAdapterError(
            FAILURE_EMBEDDING_TIMEOUT,
            "embedding request timed out",
        )
    if is_rate_limit_error(exc):
        return EmbeddingAdapterError(
            FAILURE_EMBEDDING_RATE_LIMIT,
            "embedding rate limit exceeded",
        )
    return EmbeddingAdapterError(
        FAILURE_EMBEDDING_INVALID_RESPONSE,
        "embedding provider error",
    )


def _map_vector_error(exc: EmbeddingVectorError) -> EmbeddingAdapterError:
    return EmbeddingAdapterError(
        FAILURE_EMBEDDING_INVALID_RESPONSE,
        f"invalid embedding response ({exc.code})",
    )


class ShopAIKeyEmbeddingAdapter:
    """Production ordered scalar/batch embedding adapter (no fallback)."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        embeddings: OpenAIEmbeddings | None = None,
        create_fn: EmbeddingCreateFn | None = None,
    ) -> None:
        """Configure transport.

        Parameters
        ----------
        settings:
            Root settings (model, dimensions, base URL, API key). Must match
            the locked embedding contract.
        embeddings:
            Optional pre-built ``OpenAIEmbeddings`` (tests inject construction).
        create_fn:
            Optional raw create callable for fake-backed unit tests. Signature:
            ``create_fn(*, input, model, dimensions, encoding_format)``.
        """
        self._settings = settings if settings is not None else get_settings()
        _guard_settings(self._settings)
        self._embeddings = embeddings
        self._create_fn = create_fn

    @property
    def model(self) -> str:
        return LOCKED_EMBEDDING_MODEL

    @property
    def dimensions(self) -> int:
        return LOCKED_EMBEDDING_DIMENSIONS

    @property
    def encoding_format(self) -> str:
        return LOCKED_ENCODING_FORMAT

    def _client_embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = build_shopaikey_embeddings(self._settings)
        return self._embeddings

    def _create(
        self,
        *,
        inputs: list[str],
        model: str,
        dimensions: int,
        encoding_format: str,
    ) -> Any:
        if self._create_fn is not None:
            return self._create_fn(
                input=inputs,
                model=model,
                dimensions=dimensions,
                encoding_format=encoding_format,
            )
        client = self._client_embeddings().client
        return client.create(
            input=inputs,
            model=model,
            dimensions=dimensions,
            encoding_format=encoding_format,
        )

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed ordered texts; returns one 1536-d finite vector per input.

        Preserves input order. Empty input returns an empty list without a
        provider call. Raises :class:`EmbeddingAdapterError` on timeout,
        rate-limit, invalid configuration, or invalid response (count/index/vector).
        """
        inputs = list(texts)
        if not inputs:
            return []

        # Re-check before any client call (settings must remain locked).
        _guard_settings(self._settings)
        model = LOCKED_EMBEDDING_MODEL
        dimensions = LOCKED_EMBEDDING_DIMENSIONS
        encoding = LOCKED_ENCODING_FORMAT

        try:
            response = self._create(
                inputs=inputs,
                model=model,
                dimensions=dimensions,
                encoding_format=encoding,
            )
            data = _response_to_data(response)
            return validate_embedding_data_list(
                data,
                expected_count=len(inputs),
            )
        except EmbeddingAdapterError:
            raise
        except EmbeddingVectorError as exc:
            raise _map_vector_error(exc) from exc
        except Exception as exc:
            raise _classify_transport_error(exc) from exc

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text; returns one 1536-d finite vector."""
        vectors = self.embed_texts([text])
        return vectors[0]


def embed_texts(
    texts: Sequence[str],
    *,
    settings: Settings | None = None,
    create_fn: EmbeddingCreateFn | None = None,
) -> list[list[float]]:
    """Module-level ordered embed using the sole production adapter."""
    adapter = ShopAIKeyEmbeddingAdapter(settings=settings, create_fn=create_fn)
    return adapter.embed_texts(texts)


def embed_text(
    text: str,
    *,
    settings: Settings | None = None,
    create_fn: EmbeddingCreateFn | None = None,
) -> list[float]:
    """Module-level scalar embed using the sole production adapter."""
    adapter = ShopAIKeyEmbeddingAdapter(settings=settings, create_fn=create_fn)
    return adapter.embed_text(text)


# Re-export locked constants for callers and diagnostics.
__all__ = [
    "DEFAULT_EMBEDDING_TIMEOUT_S",
    "FAILURE_EMBEDDING_INVALID_RESPONSE",
    "FAILURE_EMBEDDING_RATE_LIMIT",
    "FAILURE_EMBEDDING_TIMEOUT",
    "LOCKED_EMBEDDING_DIMENSIONS",
    "LOCKED_EMBEDDING_MODEL",
    "LOCKED_ENCODING_FORMAT",
    "EmbeddingAdapterError",
    "EmbeddingCreateFn",
    "ShopAIKeyEmbeddingAdapter",
    "build_shopaikey_embeddings",
    "embed_text",
    "embed_texts",
]
