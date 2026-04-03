import re
import json
import logging
import litellm
from fastapi import HTTPException
from app.config import settings

litellm.set_verbose = False

logger = logging.getLogger(__name__)

_AI_TIMEOUT = 60  # seconds


def _classify_error(err: Exception, model: str) -> HTTPException:
    msg = str(err).lower()
    raw = str(err)

    if "401" in raw or "wrong api key" in msg or "invalid api key" in msg or "unauthorized" in msg:
        return HTTPException(status_code=401, detail=f"Invalid API key for model '{model}'. Check your .env API_KEY.")
    if "429" in raw or "rate limit" in msg or "too many requests" in msg:
        return HTTPException(status_code=429, detail=f"Rate limit hit for '{model}'. Try again or switch fallback.")
    if "404" in raw or "model not found" in msg or "does not exist" in msg:
        return HTTPException(status_code=404, detail=f"Model '{model}' not found. Check MODEL in .env.")
    if "context" in msg and ("length" in msg or "limit" in msg or "token" in msg):
        return HTTPException(status_code=413, detail=f"Input too long for '{model}'.")
    if "timeout" in msg or "timed out" in msg:
        return HTTPException(status_code=504, detail=f"Model '{model}' timed out.")
    return HTTPException(status_code=500, detail=f"AI error from '{model}': {raw}")


async def call_ai(
    messages: list[dict],
    json_mode: bool = True,
    temperature: float = 0.2,
) -> str:
    kwargs = {
        "model": settings.MODEL,
        "api_key": settings.API_KEY,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "request_timeout": _AI_TIMEOUT,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content

    except Exception as primary_err:
        if not settings.FALLBACK_MODEL:
            raise _classify_error(primary_err, settings.MODEL)

        try:
            kwargs["model"] = settings.FALLBACK_MODEL
            kwargs["api_key"] = settings.FALLBACK_API_KEY or settings.API_KEY
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content

        except Exception as fallback_err:
            raise HTTPException(status_code=500, detail={
                "primary": _classify_error(primary_err, settings.MODEL).detail,
                "fallback": _classify_error(fallback_err, settings.FALLBACK_MODEL).detail,
                "hint": "Both primary and fallback models failed. Check your API keys in .env."
            })


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
        # json_repair handles missing quotes, unescaped newlines, comments, trailing commas, 
        # and unescaped backslashes found in LaTeX snippets automatically!
        result = json_repair.loads(cleaned)
        if isinstance(result, dict):
            return result
        # if it parsed but wasn't a dict, fallback to exception below
    except Exception as e:
        logger.error(f"json_repair failed: {e}")

    # Log full response on failure to help debug.
    logger.error(f"Failed to parse JSON. Raw content:\n{raw}")
    raise HTTPException(status_code=500, detail="AI returned malformed JSON. Try again.")
