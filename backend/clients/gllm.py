from google import genai
from google.genai import types

from config import Configuration

config = Configuration()
GEMINI_API_KEY = config.GEMINI_API_KEY


class GLLM:
    """Gemini LLM client. Works with regular Gemini API (not Vertex AI by default)."""
    def __init__(self, use_vertex=False):
        if not GEMINI_API_KEY or GEMINI_API_KEY == "None":
            raise ValueError("GEMINI_API_KEY is not configured")
        self.client = genai.Client(api_key=GEMINI_API_KEY, vertexai=use_vertex)

    def generate(self, model: str, contents: str | list[str], temperature: float = 0.7, seed: int | None = None):
        kwargs = {
            "model": model,
            "contents": contents,
            "config": types.GenerateContentConfig(temperature=temperature, seed=seed),
        }
        response = self.client.models.generate_content(**kwargs)
        if not response or not getattr(response, 'text', None) or not response.text.strip():
            raise ValueError("Empty response from Gemini")
        return response.text.strip()

    def generate_chat(self, model: str, system_instruction: str, messages: list[dict], temperature: float = 0.7):
        chat = self.client.models.start_chat(
            model=model,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
            ),
        )
        for msg in messages:
            if msg["role"] == "user":
                chat.send_message(msg["content"])
        last = messages[-1]["content"] if messages else ""
        response = chat.send_message(last)
        if not response or not getattr(response, 'text', None) or not response.text.strip():
            raise ValueError("Empty response from Gemini chat")
        return response.text.strip()

    def embed(self, text: str, model: str = "text-embedding-004") -> list[float]:
        result = self.client.models.embed_content(model=model, contents=text)
        if not result or not result.embeddings:
            raise ValueError("Empty embedding response from Gemini")
        return result.embeddings[0].values


def get_response_from_llm(llm_config: dict, contents: str, message: str) -> str:
    """Send a prompt to Gemini and return the response text."""
    model_cfg = _build_model_config(llm_config)
    model = model_cfg.pop("model")
    try:
        gllm = GLLM()
        response = gllm.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**model_cfg),
        )
        if not response or not getattr(response, 'text', None) or not response.text.strip():
            raise ValueError("Empty response from GLLM")
        return response.text.strip()
    except Exception as e:
        print(f"[GLLM] Failed: {e}")
        error_str = str(e)
        if _is_rate_limited(e) or "503" in error_str or "UNAVAILABLE" in error_str:
            try:
                gllm = GLLM()
                response = gllm.client.models.generate_content(
                    model=model, contents=contents,
                    config=types.GenerateContentConfig(**model_cfg),
                )
                if response and getattr(response, 'text', None) and response.text.strip():
                    return response.text.strip()
            except Exception as ee:
                print(f"[GLLM][RETRY] Failed: {ee}")
        raise ValueError("GLLM failed to generate a response")


def _build_model_config(llm_config: dict) -> dict:
    model = llm_config.get("model", "gemini-2.5-flash")
    thinking_budget = llm_config.get("thinking_budget", 0)
    temperature = llm_config.get("temperature", 0.0)
    seed = llm_config.get("seed", None)
    cfg = {"temperature": temperature, "model": model}
    if thinking_budget > 0:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    if seed is not None:
        cfg["seed"] = seed
    return cfg


def _is_rate_limited(error: Exception) -> bool:
    err_type = type(error).__name__.lower()
    err_text = str(error).lower()
    return (
        "resourceexhausted" in err_type
        or "toomanyrequests" in err_type
        or "429" in err_text
        or "resource_exhausted" in err_text
        or "rate limit" in err_text
        or "quota" in err_text
    )
