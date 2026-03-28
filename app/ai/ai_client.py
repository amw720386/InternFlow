from app.config import OPENAI_API_KEY

from openai import OpenAI

_client: "OpenAI | None" = None


def get_openai_client() -> "OpenAI | None":
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client
