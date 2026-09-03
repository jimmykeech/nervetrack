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


async def test_litellm_http_clients_disable_redirects_and_restore_globals():
    previous_async = llm.litellm.aclient_session
    previous_sync = llm.litellm.client_session

    async with llm.litellm_http_clients():
        assert llm.litellm.aclient_session.follow_redirects is False
        assert llm.litellm.client_session.follow_redirects is False
        assert llm.litellm.aclient_session is not previous_async
        assert llm.litellm.client_session is not previous_sync

    assert llm.litellm.aclient_session is previous_async
    assert llm.litellm.client_session is previous_sync


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


async def test_extra_context_reaches_system_prompt(monkeypatch, cfg):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _aiter([_chunk(content="ok")])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    async for _ in llm.stream_chat(
        cfg, [{"role": "user", "content": "hi"}], lambda n, a: None,
        extra_context="PATIENT BACKGROUND:\n- Sex: male",
    ):
        pass
    system = captured["messages"][0]
    assert system["role"] == "system"
    assert "PATIENT BACKGROUND" in system["content"]


def test_parse_draft_splits_on_markers():
    raw = (
        "<<<KEY_OBSERVATIONS>>>\n"
        "### The week at a glance\n"
        "All seven days green.\n\n"
        "### Analysis\n"
        "**The painting weekend absorbed without a flare.**\n"
        "<<<NEXT_STEPS>>>\n"
        "Hold the volume.\n\n"
        "1. Keep the 3-set goblet squat\n"
    )

    out = llm._parse_draft(raw)

    assert out.key_observations.startswith("### The week at a glance")
    assert "### Analysis" in out.key_observations
    assert "**The painting weekend absorbed without a flare.**" in out.key_observations
    assert out.next_steps.startswith("Hold the volume.")
    assert "1. Keep the 3-set goblet squat" in out.next_steps
    # The markers themselves never leak into the stored fields.
    assert llm.KEY_MARKER not in out.key_observations
    assert llm.NEXT_MARKER not in out.key_observations


def test_parse_draft_without_next_marker_keeps_everything_as_observations():
    out = llm._parse_draft("<<<KEY_OBSERVATIONS>>>\n### Analysis\nSteady week.")

    assert out.key_observations == "### Analysis\nSteady week."
    assert out.next_steps == ""


def test_parse_draft_without_markers_never_raises():
    out = llm._parse_draft("Sorry, I could not read the data.")

    assert out.key_observations == "Sorry, I could not read the data."
    assert out.next_steps == ""


def test_parse_draft_ignores_preamble_before_the_first_marker():
    out = llm._parse_draft("Here you go:\n<<<KEY_OBSERVATIONS>>>\nSteady.\n<<<NEXT_STEPS>>>\nWalk.")

    assert out.key_observations == "Steady."
    assert out.next_steps == "Walk."


def test_parse_draft_splits_on_next_marker_even_without_the_key_marker():
    out = llm._parse_draft("Steady week.\n<<<NEXT_STEPS>>>\nWalk more.")

    assert out.key_observations == "Steady week."
    assert out.next_steps == "Walk more."


def test_parse_draft_strips_markers_the_model_echoed_back():
    raw = (
        "<<<KEY_OBSERVATIONS>>>\n"
        "Steady.\n"
        "<<<KEY_OBSERVATIONS>>>\n"
        "Still steady.\n"
        "<<<NEXT_STEPS>>>\n"
        "Walk.\n"
        "<<<NEXT_STEPS>>>\n"
        "And stretch.\n"
    )

    out = llm._parse_draft(raw)

    for field in (out.key_observations, out.next_steps):
        assert llm.KEY_MARKER not in field
        assert llm.NEXT_MARKER not in field
    assert "Still steady." in out.key_observations
    assert "And stretch." in out.next_steps


async def test_draft_weekly_returns_parsed_fields(monkeypatch, cfg):
    async def fake_acompletion(**kwargs):
        msg = types.SimpleNamespace(
            content="<<<KEY_OBSERVATIONS>>>\nsteady\n<<<NEXT_STEPS>>>\nwalk more"
        )
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    out = await llm.draft_weekly(cfg, {"week_start": "2026-06-22", "days": []})
    assert out.key_observations == "steady" and out.next_steps == "walk more"


async def test_draft_weekly_prompt_requests_sections_and_includes_history(monkeypatch, cfg):
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        msg = types.SimpleNamespace(content="<<<KEY_OBSERVATIONS>>>\nx\n<<<NEXT_STEPS>>>\ny")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    bundle = {
        "week_start": "2026-08-04",
        "program_week": 21,
        "days": [],
        "history": [{"program_week": 8, "avg_tingling_level": "1.1"}],
        "recent_reviews": [],
    }

    await llm.draft_weekly(cfg, bundle)

    prompt = captured["messages"][1]["content"]
    # The section menu the model is told to choose from.
    assert "### The week at a glance" in prompt
    assert "### What stood out" in prompt
    assert "### Analysis" in prompt
    assert "### Watch-outs" in prompt
    # The response contract matches what _parse_draft reads.
    assert llm.KEY_MARKER in prompt
    assert llm.NEXT_MARKER in prompt
    # History is serialised into the prompt so past weeks can be cited.
    assert '"program_week": 8' in prompt
    # Safety property in a health tracker, not a style preference — pin it.
    assert "never invent a number" in prompt
