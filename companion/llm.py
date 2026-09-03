from google import genai
from google.genai import types

from companion import config


def make_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = make_client()
    return _client


def generate(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    history: list[types.Content] | None = None,
    json_mode: bool = False,
    temperature: float = 0.7,
) -> str:
    client = get_client()
    config_kwargs: dict = {
        "temperature": temperature,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if system:
        config_kwargs["system_instruction"] = system
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    contents = list(history or [])
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    response = client.models.generate_content(
        model=model or config.CHAT_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return response.text or ""


def generate_stream(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    history: list[types.Content] | None = None,
    temperature: float = 0.7,
):
    client = get_client()
    config_kwargs: dict = {
        "temperature": temperature,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if system:
        config_kwargs["system_instruction"] = system
    contents = list(history or [])
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    for chunk in client.models.generate_content_stream(
        model=model or config.CHAT_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    ):
        if chunk.text:
            yield chunk.text
