import json
import types

import pytest

from app.models.ai import ResolvedLlmConfig
from app.services import llm


def _chunk(content=None, tool_calls=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = types.SimpleNamespace(delta=delta)
    return types.SimpleNamespace(choices=[choice])


def _tool_call_delta(idx, call_id, name, args):
    fn = types.SimpleNamespace(name=name, arguments=args)
    return types.SimpleNamespace(index=idx, id=call_id, function=fn)


async def _aiter(chunks):
    for c in chunks:
        yield c


@pytest.fixture
def cfg():
    return ResolvedLlmConfig(model="anthropic/claude-sonnet-5", api_key="k")


async def test_stream_chat_plain_answer(monkeypatch, cfg):
    async def fake_acompletion(**kwargs):
        return _aiter([_chunk(content="Hel"), _chunk(content="lo")])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)

    events = [e async for e in llm.stream_chat(cfg, [{"role": "user", "content": "hi"}], lambda n, a: None)]
    assert {"type": "token", "text": "Hel"} in events
    assert events[-1] == {"type": "final", "content": "Hello"}


async def test_stream_chat_runs_tool_then_answers(monkeypatch, cfg):
    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _aiter([_chunk(tool_calls=[
                _tool_call_delta(0, "c1", "list_weeks", "{}")
            ])])
        return _aiter([_chunk(content="You have 2 weeks")])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)

    seen = []
    def run_tool(name, args):
        seen.append(name)
        return [{"week_start": "2026-06-22"}]

    events = [e async for e in llm.stream_chat(cfg, [{"role": "user", "content": "how many weeks"}], run_tool)]
    assert seen == ["list_weeks"]
    assert {"type": "tool", "name": "list_weeks"} in events
    assert events[-1] == {"type": "final", "content": "You have 2 weeks"}


async def test_max_iters_guard(monkeypatch, cfg):
    async def always_tool(**kwargs):
        if kwargs.get("stream"):
            return _aiter([_chunk(tool_calls=[_tool_call_delta(0, "c", "list_weeks", "{}")])])
        msg = types.SimpleNamespace(content="stopping")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm.litellm, "acompletion", always_tool)
    events = [e async for e in llm.stream_chat(cfg, [{"role": "user", "content": "x"}], lambda n, a: [], max_iters=3)]
    # Terminates with a final event rather than looping forever.
    assert events[-1]["type"] == "final"


async def test_draft_weekly_parses_json(monkeypatch, cfg):
    async def fake_acompletion(**kwargs):
        msg = types.SimpleNamespace(
            content=json.dumps({"key_observations": "steady", "next_steps": "walk more"})
        )
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    out = await llm.draft_weekly(cfg, {"week_start": "2026-06-22", "days": []})
    assert out.key_observations == "steady" and out.next_steps == "walk more"
