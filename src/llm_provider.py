"""Unified LLM Provider Strategy with Automatic Failover across Gemini & OpenAI-Compatible APIs."""

from __future__ import annotations

import asyncio
import logging

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE_URL,
    OPENAI_COMPAT_MODEL,
)

logger = logging.getLogger(__name__)

_gemini_client: genai.Client | None = None
_http_client: httpx.AsyncClient | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing from configuration.")
        _gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=60_000),
        )
    return _gemini_client


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=15.0, pool=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _http_client


async def close_llm_clients() -> None:
    """Gracefully close shared HTTP clients on application shutdown."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def _generate_via_gemini(
    *,
    system_instruction: str,
    user_prompt: str,
    temperature: float,
) -> str:
    client = _get_gemini_client()
    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""
        except APIError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            raise
    return ""


async def _generate_via_openai_compatible(
    *,
    system_instruction: str,
    user_prompt: str,
    temperature: float,
) -> str:
    """Call Groq or any OpenAI-compatible endpoint via /v1/chat/completions."""
    if not OPENAI_COMPAT_API_KEY:
        raise RuntimeError("OPENAI_COMPAT_API_KEY is missing from configuration.")

    effective_system = system_instruction
    if "json" not in effective_system.lower():
        effective_system += "\nRespond strictly with a valid JSON object."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_COMPAT_API_KEY}",
    }

    payload = {
        "model": OPENAI_COMPAT_MODEL,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": effective_system},
            {"role": "user", "content": user_prompt},
        ],
    }

    client = _get_http_client()
    for attempt in range(2):
        try:
            resp = await client.post(
                f"{OPENAI_COMPAT_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("LLM provider returned empty choices.")
            return choices.get("message", {}).get("content") or ""
        except httpx.TransportError:
            if attempt == 0:
                await asyncio.sleep(1.5)
                continue
            raise
    return ""


async def _dispatch_to_provider(
    provider: str,
    *,
    system_instruction: str,
    user_prompt: str,
    temperature: float,
) -> str:
    if provider == "gemini":
        return await _generate_via_gemini(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            temperature=temperature,
        )
    if provider in {"openai_compatible", "groq"}:
        return await _generate_via_openai_compatible(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            temperature=temperature,
        )
    raise RuntimeError(f"Unsupported LLM provider configured: {provider}")


async def generate_raw_json_completion(
    *,
    system_instruction: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> str:
    """Execute generation on primary LLM_PROVIDER with automatic failover to LLM_FALLBACK_PROVIDER."""
    try:
        return await _dispatch_to_provider(
            LLM_PROVIDER,
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            temperature=temperature,
        )
    except Exception as primary_exc:
        if LLM_FALLBACK_PROVIDER and LLM_FALLBACK_PROVIDER != LLM_PROVIDER:
            logger.warning(
                "Primary LLM provider '%s' failed (%s); failing over to '%s'.",
                LLM_PROVIDER,
                type(primary_exc).__name__,
                LLM_FALLBACK_PROVIDER,
            )
            return await _dispatch_to_provider(
                LLM_FALLBACK_PROVIDER,
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                temperature=temperature,
            )
        raise
