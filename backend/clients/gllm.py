"""Small wrapper around Gemini's streaming API."""

from threading import Lock

from google import genai
from google.genai import types

from config import Configuration

api_key = Configuration().GEMINI_API_KEY
_client = None
_client_lock = Lock()


def _get_client():
    global _client
    if not api_key or api_key == "None":
        raise ValueError("GEMINI_API_KEY is not configured")

    if _client is None:
        with _client_lock:
            if _client is None:
                _client = genai.Client(api_key=api_key)
    return _client


def stream_text(model: str, prompt: str, temperature: float = 0.0):
    """Yield text as Gemini generates it."""
    client = _get_client()
    response_stream = client.models.generate_content_stream(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=temperature),
    )
    for response in response_stream:
        if response.text:
            yield response.text
