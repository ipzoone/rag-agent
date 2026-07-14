"""LLM model configuration with retry + automatic fallback.

Primary:   EdgeOne AI Gateway / Makers  (AI_GATEWAY_*)
Fallback:  Groq                         (LLM_*)

Behaviour:
  * The primary provider is retried a few times with backoff to absorb
    transient 5xx / rate-limit / timeout errors (EdgeOne's AI Gateway
    occasionally returns a transient 502 "upstream temporarily unavailable").
  * If the primary keeps failing, the request automatically retries on the
    fallback provider.
  * IMPORTANT: `.env` is gitignored and not shipped to EdgeOne, so the Groq
    fallback would be missing in production. We therefore read LLM_* from the
    environment first, and fall back to baked-in defaults so the deployed
    agent always has a backup. Prefer setting LLM_* in the EdgeOne environment
    variables and removing the hardcoded defaults for production hygiene.
"""

import asyncio
import os
from typing import AsyncIterator

import httpx
import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Model, OpenAIChatCompletionsModel
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.model_settings import ModelSettings
from agents.models.interface import (
    ModelResponse,
    ModelTracing,
    TResponseInputItem,
    TResponseStreamEvent,
)
from agents.tool import Tool
from openai.types.responses.response_prompt_param import ResponsePromptParam

from ._logger import create_logger

load_dotenv()

logger = create_logger("model")

# ── Retry tuning ──────────────────────────────────────────────────────────────
MAX_RETRIES = 3
BACKOFF_BASE = 1.0  # seconds; attempt n waits BACKOFF_BASE * n
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(e: Exception) -> bool:
    if isinstance(e, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(e, (openai.APIConnectionError, openai.RateLimitError)):
        return True
    if isinstance(e, openai.APIStatusError):
        return getattr(e, "status_code", None) in _RETRYABLE_STATUS
    return False


# ── Model builders ─────────────────────────────────────────────────────────────

def _build_model(api_key: str, base_url: str, model_name: str, label: str) -> Model | None:
    if not (api_key and base_url and model_name):
        logger.warn(f"{label}: incomplete config — skipping")
        return None
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
        ),
    )
    logger.log(f"{label}: {model_name} @ {base_url}")
    return OpenAIChatCompletionsModel(model=model_name, openai_client=client)


def _build_primary() -> Model | None:
    return _build_model(
        os.getenv("AI_GATEWAY_API_KEY", ""),
        os.getenv("AI_GATEWAY_BASE_URL", ""),
        os.getenv("AI_GATEWAY_MODEL", ""),
        "EdgeOne/Makers",
    )


# Groq fallback: prefer env (set LLM_* in EdgeOne env vars), else baked-in
# defaults so production always has a backup (.env is gitignored / not shipped).
_GROQ_API_KEY = os.getenv("LLM_API_KEY") or "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"
_GROQ_BASE_URL = os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1"
_GROQ_MODEL = os.getenv("LLM_MODEL") or "llama-3.3-70b-versatile"


def _build_secondary() -> Model | None:
    return _build_model(_GROQ_API_KEY, _GROQ_BASE_URL, _GROQ_MODEL, "Groq")


_primary = _build_primary()
_secondary = _build_secondary()
_models = [m for m in (_primary, _secondary) if m is not None]
if not _models:
    logger.error("No LLM provider configured (set AI_GATEWAY_* and/or LLM_*)")


class FallbackModel(Model):
    """Tries each model in order; retries transient errors before giving up."""

    def __init__(self, models: list[Model], logger) -> None:
        self._models = models
        self._logger = logger

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> ModelResponse:
        last_err: Exception | None = None
        for i, model in enumerate(self._models):
            for attempt in range(MAX_RETRIES):
                try:
                    return await model.get_response(
                        system_instructions=system_instructions,
                        input=input,
                        model_settings=model_settings,
                        tools=tools,
                        output_schema=output_schema,
                        handoffs=handoffs,
                        tracing=tracing,
                        previous_response_id=previous_response_id,
                        conversation_id=conversation_id,
                        prompt=prompt,
                    )
                except Exception as e:
                    last_err = e
                    if attempt < MAX_RETRIES - 1 and _is_retryable(e):
                        self._logger.warn(
                            f"FallbackModel: provider #{i + 1} attempt {attempt + 1} "
                            f"failed ({type(e).__name__}); retrying in "
                            f"{BACKOFF_BASE * (attempt + 1):.1f}s"
                        )
                        await asyncio.sleep(BACKOFF_BASE * (attempt + 1))
                        continue
                    self._logger.error(
                        f"FallbackModel: provider #{i + 1} failed "
                        f"({type(e).__name__}: {e}); trying next provider"
                    )
                    break
        assert last_err is not None
        raise last_err

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        last_err: Exception | None = None
        for i, model in enumerate(self._models):
            for attempt in range(MAX_RETRIES):
                try:
                    gen = model.stream_response(
                        system_instructions=system_instructions,
                        input=input,
                        model_settings=model_settings,
                        tools=tools,
                        output_schema=output_schema,
                        handoffs=handoffs,
                        tracing=tracing,
                        previous_response_id=previous_response_id,
                        conversation_id=conversation_id,
                        prompt=prompt,
                    )
                    # Probe the first event so connection-level failures (502,
                    # timeout, rate limit) surface before we commit to a provider.
                    first = await gen.__anext__()
                except Exception as e:
                    last_err = e
                    if attempt < MAX_RETRIES - 1 and _is_retryable(e):
                        self._logger.warn(
                            f"FallbackModel: provider #{i + 1} stream attempt {attempt + 1} "
                            f"failed ({type(e).__name__}); retrying in "
                            f"{BACKOFF_BASE * (attempt + 1):.1f}s"
                        )
                        await asyncio.sleep(BACKOFF_BASE * (attempt + 1))
                        continue
                    self._logger.error(
                        f"FallbackModel: provider #{i + 1} stream failed "
                        f"({type(e).__name__}: {e}); trying next provider"
                    )
                    break

                # Committed to this provider.
                yield first
                async for event in gen:
                    yield event
                return

        assert last_err is not None
        raise last_err


llm_model = FallbackModel(_models, logger)
