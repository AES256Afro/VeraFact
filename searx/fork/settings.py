# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ``fork:`` section of ``settings.yml``, validated as one msgspec struct.

Every VeraFact option lives under ``fork:`` so an upstream rebase never touches
it.  The struct is wired into :py:data:`searx.settings_defaults.SCHEMA` with one
line; :py:func:`searx.settings_defaults.apply_schema` decodes the YAML mapping
into :py:class:`SettingsFork`, which rejects unknown keys and bad values.

A few fields can come from the environment (the container sets them without a
settings file): see :py:data:`ENVIRON`.  They are applied after the YAML is
decoded, so the environment wins, and are validated like the YAML values.
"""

# pylint: disable=too-few-public-methods

# Struct fields aren't discovered in Python 3.14
# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

__all__ = ["SettingsFork", "ENVIRON"]

import os
import typing as t
from collections.abc import Mapping

import msgspec

LlmBackend = t.Literal["disabled", "openai_compat", "anthropic", "openai"]
OcrBackend = t.Literal["tesseract_http", "vision_llm"]
Look = t.Literal["default", "classic", "modern", "engineering", "familiar", "cyberpunk"]
Mark = t.Literal["grid-check", "lens", "funnel"]
Wordmark = t.Literal["two-tone", "mono", "mark-only"]


class FactCheck(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """``fork.factcheck``: the claim → verdict → source mode."""

    enabled: bool = True
    offer_on_heuristic: bool = True
    """Show the "check this as a claim?" banner when a query looks like a claim."""
    google_api_key: str = ""
    """Google Fact Check Tools API key; ``FORK_FACTCHECK_GOOGLE_API_KEY``."""
    enrich_top: int = 5
    """Fetch ClaimReview JSON-LD for the top N results that have no verdict yet."""


class Ocr(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """``fork.ocr``: reading a claim out of a screenshot."""

    enabled: bool = False
    backend: OcrBackend = "tesseract_http"
    url: str = "http://ocr:8884"
    """The Tesseract sidecar; ``FORK_OCR_URL``."""
    max_upload_mb: int = 8
    languages: list[str] = msgspec.field(default_factory=lambda: ["eng"])


class Llm(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """``fork.llm``: the optional model layer.  Off unless the owner turns it on."""

    backend: LlmBackend = "disabled"
    """``FORK_LLM_BACKEND``."""
    base_url: str = ""
    """``openai_compat`` only (Ollama, llama.cpp, vLLM, ...); ``FORK_LLM_BASE_URL``."""
    model: str = ""
    """``FORK_LLM_MODEL``."""
    api_key: str = ""
    """``FORK_LLM_API_KEY``; prefer the environment over settings.yml on disk."""
    timeout: int = 20
    max_tokens: int = 400
    allow_images: bool = False
    """Let the OCR backend send screenshots to this model."""
    summarise_factchecks: bool = True
    extract_claims: bool = True
    search_assist: bool = False
    """Frontier backends only: the model searches the web and answers above the results."""
    search_assist_default: bool = False
    """Even when search_assist is on, the user enables it per search unless this is true."""
    search_assist_local: bool = False
    """Let an openai_compat server that can search the web run the search assist too (off: frontier only)."""
    search_assist_max_fetches: int = 6
    search_assist_timeout: int = 8


class ModelFit(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """``fork.modelfit``: the offline "which model fits this box" helper."""

    enabled: bool = True


class Appearance(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """``fork.appearance``: the owner's defaults; users can override them in Preferences."""

    look: Look = "default"
    mark: Mark = "grid-check"
    wordmark: Wordmark = "two-tone"


ENVIRON: dict[str, tuple[str, str]] = {
    "FORK_FACTCHECK_GOOGLE_API_KEY": ("factcheck", "google_api_key"),
    "FORK_OCR_URL": ("ocr", "url"),
    "FORK_LLM_BACKEND": ("llm", "backend"),
    "FORK_LLM_BASE_URL": ("llm", "base_url"),
    "FORK_LLM_MODEL": ("llm", "model"),
    "FORK_LLM_API_KEY": ("llm", "api_key"),
}
"""Environment variables that override a ``fork.<section>.<field>`` value."""


class SettingsFork(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """The ``fork:`` section.

    .. code:: yaml

       fork:
         factcheck:
           enabled: true
         llm:
           backend: disabled
         appearance:
           look: default
           mark: grid-check
           wordmark: two-tone
    """

    factcheck: FactCheck = msgspec.field(default_factory=FactCheck)
    ocr: Ocr = msgspec.field(default_factory=Ocr)
    llm: Llm = msgspec.field(default_factory=Llm)
    modelfit: ModelFit = msgspec.field(default_factory=ModelFit)
    appearance: Appearance = msgspec.field(default_factory=Appearance)

    def __post_init__(self):
        self.apply_environ(os.environ)

    def apply_environ(self, environ: Mapping[str, str]) -> None:
        """Overlay the variables in :py:data:`ENVIRON` that are set in ``environ``.

        A value that does not fit the field's type raises
        :py:class:`msgspec.ValidationError` naming the variable, exactly as a
        bad YAML value would name its key.
        """
        for name, (section_name, field_name) in ENVIRON.items():
            raw = environ.get(name)
            if raw is None:
                continue
            section: msgspec.Struct = getattr(self, section_name)
            hints = t.get_type_hints(type(section))
            try:
                value = msgspec.convert(raw, hints[field_name], strict=False)
            except msgspec.ValidationError as exc:
                raise msgspec.ValidationError(f"{exc} - from environment variable {name}") from exc
            setattr(section, field_name, value)
