import os
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

class LLMClient(ABC):
    """Abstract base class for LLM provider clients."""

    @abstractmethod
    def complete(self, prompt: str, history: list | None = None) -> str:
        """Send a prompt and return the model's text response.

        Args:
            prompt: The user prompt to send to the model.
            history: Optional list of prior turns as dicts with ``"role"``
                and ``"content"`` keys, ordered oldest-first.  When provided,
                these messages are prepended before the current prompt so the
                model has conversational context.

        Returns:
            The model's text response as a string.
        """


class OpenAIClient(LLMClient):
    """LLM client backed by the OpenAI chat completions API."""

    def __init__(self, model: str, api_key: str):
        """Initialize the OpenAI client.

        Args:
            model: The OpenAI model identifier (e.g. "gpt-4o-mini").
            api_key: The OpenAI API key.
        """
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def complete(self, prompt: str, history: list | None = None) -> str:
        """Send a prompt to OpenAI and return the response text.

        Args:
            prompt: The user prompt to send.
            history: Optional prior conversation turns (role/content dicts).

        Returns:
            The assistant's reply as a string.
        """
        messages = list(history or []) + [{"role": "user", "content": prompt}]
        resp = self._client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content


class AnthropicClient(LLMClient):
    """LLM client backed by the Anthropic Messages API."""

    def __init__(self, model: str, api_key: str):
        """Initialize the Anthropic client.

        Args:
            model: The Anthropic model identifier (e.g. "claude-sonnet-4-6").
            api_key: The Anthropic API key.
        """
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, prompt: str, history: list | None = None) -> str:
        """Send a prompt to Anthropic and return the response text.

        Args:
            prompt: The user prompt to send.
            history: Optional prior conversation turns (role/content dicts).

        Returns:
            The assistant's reply as a string.
        """
        messages = list(history or []) + [{"role": "user", "content": prompt}]
        msg = self._client.messages.create(model=self.model, max_tokens=1024, messages=messages)
        return msg.content[0].text


class OllamaClient(LLMClient):
    """LLM client backed by a local Ollama server."""

    def __init__(self, model: str, base_url: str):
        """Initialize the Ollama client.

        Args:
            model: The Ollama model name (e.g. "llama3").
            base_url: Base URL of the Ollama server (e.g. "http://localhost:11434").
        """
        self.model = model
        self.base_url = base_url

    def complete(self, prompt: str, history: list | None = None) -> str:
        """Send a prompt to Ollama and return the response text.

        Uses the ``/api/chat`` endpoint so that conversation history is passed
        as a proper messages array (role/content dicts).

        Args:
            prompt: The user prompt to send.
            history: Optional prior conversation turns (role/content dicts).

        Returns:
            The model's reply as a string.
        """
        import requests
        messages = list(history or []) + [{"role": "user", "content": prompt}]
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=120,
        )
        return resp.json()["message"]["content"]


def get_llm_client() -> LLMClient:
    """Instantiate an LLM client from environment variables.

    Reads LLM_PROVIDER, LLM_MODEL, and the relevant API key / URL from the
    environment (or a .env file loaded at module import time).

    Returns:
        A concrete LLMClient instance for the configured provider.

    Raises:
        ValueError: If LLM_PROVIDER is not one of "openai", "anthropic", "ollama".
    """
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if provider == "openai":
        return OpenAIClient(model=model, api_key=os.environ["OPENAI_API_KEY"])
    elif provider == "anthropic":
        return AnthropicClient(model=model, api_key=os.environ["ANTHROPIC_API_KEY"])
    elif provider == "ollama":
        return OllamaClient(model=model, base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
