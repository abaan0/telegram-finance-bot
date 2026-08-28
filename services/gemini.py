import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()


GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

GEMINI_FALLBACK_MODELS = list(
    dict.fromkeys(
        [
            GEMINI_MODEL,
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ]
    )
)


client = genai.Client(
    api_key=GEMINI_API_KEY
)


def generate_json_with_fallback(
    prompt: str,
    response_schema: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """
    Generate structured JSON using the Gemini fallback chain.

    Returns:
        tuple:
            - Parsed JSON dictionary
            - Model that successfully generated the response
    """

    last_error: Exception | None = None

    for model in GEMINI_FALLBACK_MODELS:
        try:
            print(
                f"Trying Gemini model: {model}"
            )

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                ),
            )

            if not response.text:
                raise ValueError(
                    "Gemini returned an empty response"
                )

            data = json.loads(
                response.text
            )

            if not isinstance(data, dict):
                raise ValueError(
                    "Gemini response was not a JSON object"
                )

            print(
                f"Gemini success: {model}"
            )

            return data, model

        except Exception as error:
            last_error = error

            print(
                f"Gemini model {model} failed: {error}"
            )

    if last_error:
        raise last_error

    raise RuntimeError(
        "No Gemini models are configured"
    )


async def generate_json_with_fallback_async(
    prompt: str,
    response_schema: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """
    Async wrapper around the synchronous Gemini SDK.

    Runs the SDK call in a worker thread so the
    Telegram event loop is not blocked.
    """

    return await asyncio.to_thread(
        generate_json_with_fallback,
        prompt,
        response_schema,
    )