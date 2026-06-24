"""LLM wrapper (injected client, no network) + generate preflight."""
import pytest

from briefing import cli
from briefing.llm import LLM


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, text=None, parsed=None):
        self.content = [_Block(text)] if text is not None else []
        self.parsed_output = parsed


class _Messages:
    def __init__(self):
        self.create_calls, self.parse_calls = [], []

    def create(self, **kw):
        self.create_calls.append(kw)
        return _Resp(text="hello world")

    def parse(self, **kw):
        self.parse_calls.append(kw)
        return _Resp(parsed={"ok": True})


class _Client:
    def __init__(self):
        self.messages = _Messages()


def test_complete_uses_model_and_returns_text():
    c = _Client()
    llm = LLM({"llm": {"default_model": "m-default", "script_model": "m-script"}}, client=c)
    assert llm.complete("sys", "user", model=llm.script_model) == "hello world"
    call = c.messages.create_calls[0]
    assert call["model"] == "m-script"
    assert "thinking" not in call            # writing task → no thinking (avoids truncation)


def test_parse_uses_editor_model_and_schema():
    c = _Client()
    llm = LLM({"llm": {"default_model": "m-default", "editor_model": "m-editor"}}, client=c)
    assert llm.parse("sys", "user", schema=dict, model=llm.editor_model) == {"ok": True}
    call = c.messages.parse_calls[0]
    assert call["model"] == "m-editor" and call["output_format"] is dict


def test_preflight_blocks_without_key(monkeypatch):
    monkeypatch.setattr(cli.os, "getenv", lambda k, d="": "" if k == "ANTHROPIC_API_KEY" else d)
    with pytest.raises(SystemExit):
        cli._preflight({"sources": [{"id": "x"}]})


def test_preflight_blocks_without_sources(monkeypatch):
    monkeypatch.setattr(cli.os, "getenv", lambda k, d="": "sk-ant-x" if k == "ANTHROPIC_API_KEY" else d)
    with pytest.raises(SystemExit):
        cli._preflight({"sources": []})


def test_preflight_passes_with_key_and_sources(monkeypatch):
    monkeypatch.setattr(cli.os, "getenv", lambda k, d="": "sk-ant-x" if k == "ANTHROPIC_API_KEY" else d)
    cli._preflight({"sources": [{"id": "x"}]})   # no raise
