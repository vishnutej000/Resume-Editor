import re
import logging
import litellm
from fastapi import HTTPException
from app.config import settings

litellm.set_verbose = False

logger = logging.getLogger(__name__)


def _classify_error(err: Exception, model: str) -> HTTPException:
    msg = str(err).lower()
    raw = str(err)
    if "401" in raw or "wrong api key" in msg or "invalid api key" in msg or "unauthorized" in msg:
        return HTTPException(status_code=401, detail=f"Invalid API key for '{model}'. Check your .env.")
    if "429" in raw or "rate limit" in msg or "too many requests" in msg:
        return HTTPException(status_code=429, detail=f"Rate limit hit for '{model}'. Try again or switch model.")
    if "404" in raw or "model not found" in msg or "does not exist" in msg:
        return HTTPException(status_code=404, detail=f"Model '{model}' not found. Check COMPLEX_MODEL in .env.")
    if "context" in msg and ("length" in msg or "limit" in msg or "token" in msg):
        return HTTPException(status_code=413, detail=f"Input too long for '{model}'.")
    if "timeout" in msg or "timed out" in msg:
        return HTTPException(status_code=504, detail=f"Model '{model}' timed out after {settings.AI_TIMEOUT}s.")
    return HTTPException(status_code=500, detail=f"AI error from '{model}': {raw}")


async def call_ai_complex(messages: list[dict], json_mode: bool = True) -> str:
    """
    DeepSeek V3 via NVIDIA NIM — all complex tasks:
    JD analysis, project/experience selection, bullet rewriting.
    Falls back to FALLBACK_MODEL on failure.
    """
    kwargs = {
        "model": settings.COMPLEX_MODEL,
        "api_key": settings.NVIDIA_API_KEY,
        "api_base": settings.NVIDIA_BASE_URL,
        "messages": messages,
        "temperature": settings.COMPLEX_TEMPERATURE,
        "max_tokens": settings.MAX_TOKENS,
        "request_timeout": settings.AI_TIMEOUT,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content

    except Exception as primary_err:
        if not settings.FALLBACK_MODEL:
            raise _classify_error(primary_err, settings.COMPLEX_MODEL)

        logger.warning("Complex model '%s' failed, trying fallback '%s': %s",
                       settings.COMPLEX_MODEL, settings.FALLBACK_MODEL, primary_err)
        try:
            fallback_key = settings.FALLBACK_API_KEY or settings.GROQ_API_KEY
            fallback_kwargs = {
                "model": settings.FALLBACK_MODEL,
                "api_key": fallback_key,
                "messages": messages,
                "temperature": settings.COMPLEX_TEMPERATURE,
                "max_tokens": settings.MAX_TOKENS,
                "request_timeout": settings.AI_TIMEOUT,
            }
            if json_mode:
                fallback_kwargs["response_format"] = {"type": "json_object"}
            response = await litellm.acompletion(**fallback_kwargs)
            return response.choices[0].message.content

        except Exception as fallback_err:
            raise HTTPException(status_code=500, detail={
                "primary": _classify_error(primary_err, settings.COMPLEX_MODEL).detail,
                "fallback": _classify_error(fallback_err, settings.FALLBACK_MODEL).detail,
                "hint": "Both complex and fallback models failed. Check NVIDIA_API_KEY and FALLBACK_API_KEY in .env.",
            })


async def call_ai_simple(messages: list[dict], json_mode: bool = True) -> str:
    """
    Groq Llama — fast and cheap.
    Used for lightweight tasks only.
    """
    kwargs = {
        "model": settings.SIMPLE_MODEL,
        "api_key": settings.GROQ_API_KEY,
        "messages": messages,
        "temperature": settings.SIMPLE_TEMPERATURE,
        "max_tokens": settings.MAX_TOKENS,
        "request_timeout": settings.AI_TIMEOUT,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content
    except Exception as err:
        raise _classify_error(err, settings.SIMPLE_MODEL)


# Backward-compat alias — routes to complex model
async def call_ai(messages: list[dict], json_mode: bool = True, temperature: float = None) -> str:
    return await call_ai_complex(messages, json_mode=json_mode)


def _clean(raw: str) -> str:
    raw = raw.strip()
    if "```" in raw:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if match:
            raw = match.group(1).strip()
    return raw


import json_repair

def parse_json(raw: str) -> dict:
    logger.debug("parse_json raw response (first 300 chars): %s", repr(raw[:300]))

    cleaned = _clean(raw)

    try:
        result = json_repair.loads(cleaned)
        if isinstance(result, dict):
            return result
    except Exception as e:
        logger.error(f"json_repair failed: {e}")

    logger.error(f"Failed to parse JSON. Raw content:\n{raw}")
    raise HTTPException(status_code=500, detail="AI returned malformed JSON. Try again.")
