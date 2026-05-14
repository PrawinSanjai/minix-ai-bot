from google import genai
from google.genai import types

from config import Configuration

config = Configuration()
GEMINI_API_KEY = config.GEMINI_API_KEY


class GLLM:
    """
    Class for initialising Gemini AI.
    """
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY, vertexai=True)
    
def get_response_from_llm(llm_config: dict, contents: str, message: str):
    """
    
    """
    config = generate_llm_model_config(llm_config=llm_config)
    model = config.pop("model")
    gllm = GLLM()

    def run_gllm():
        response = gllm.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**config)
        )

        if not response or not getattr(response, 'text', None) or not response.text.strip():
            raise ValueError("Empty response from GLLM")
        
        return response
    
    try:
        run_gllm()
    
    except Exception as e:
        print("[GLLM] Failed to generate a response")
        error_str = str(e)
        is_rate_limited = _is_rate_limited_error(e)
        is_unavailable = "503" in error_str or "UNAVAILABLE" in error_str
        is__retryable = is_rate_limited or is_unavailable

        if is__retryable:
            
            try:
                run_gllm()
            except Exception as ee:
                print("[GLLM][RETRY] Failed to generate a response")
                raise ValueError("GLLM failed to generate a response")


def generate_llm_model_config(llm_config: dict):
    """
    Function for  setting up the LLM model configurations.
    """
    if llm_config:
        model = llm_config.get("model", "gemini-2.5-flash")
        thinking_budget = llm_config.get("thinking_budget", 0)
        temperature = llm_config.get("temperature", 0.0)
        seed = llm_config.get("seed", None)

    config = {
        "temperature": temperature,
        "model": model,
        "thinking_budget": types.ThinkingConfig(thinking_budget=thinking_budget)
    }

    if seed is not None:
        config["seed"] = seed
    
    return config


def _is_rate_limited_error(error: Exception) -> bool:
    error_type = type(error).__name__.lower()
    error_text = str(error).lower()
    return (
        "resourceexhausted" in error_type
        or "toomanyrequests" in error_type
        or "429" in error_text
        or "resource_exhausted" in error_text
        or "rate limit" in error_text
        or "quota" in error_text
    )