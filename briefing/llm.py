"""Thin Anthropic client wrapper.

Editor stage uses the stronger model; other stages use the default. Auth resolves
from ANTHROPIC_API_KEY (env or a gitignored .env). The client is created lazily, so
importing this module never requires a key — only an actual call does.
"""
from __future__ import annotations

from dotenv import load_dotenv

from .paths import REPO_ROOT

load_dotenv(REPO_ROOT / ".env")  # no-op if absent


class LLM:
    def __init__(self, config: dict, client=None):
        cfg = config.get("llm", {})
        self.default_model = cfg.get("default_model", "claude-sonnet-4-6")
        self.editor_model = cfg.get("editor_model", self.default_model)
        self.script_model = cfg.get("script_model", self.default_model)
        self._client = client                      # injectable for tests

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        return self._client

    def complete(self, system: str, user: str, *, model: str | None = None,
                 max_tokens: int = 16000) -> str:
        """Return the text of a single completion.

        Thinking is left off here: this is a writing task (render a brief into dialogue),
        not a reasoning one — and on Opus, thinking tokens would otherwise consume the
        max_tokens budget and truncate longer segments.
        """
        resp = self.client.messages.create(
            model=model or self.default_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def parse(self, system: str, user: str, schema, *, model: str | None = None,
              max_tokens: int = 16000):
        """Return a validated instance of `schema` (a pydantic model)."""
        resp = self.client.messages.parse(
            model=model or self.default_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            thinking={"type": "adaptive"},
        )
        return resp.parsed_output
