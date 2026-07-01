"""LiteLLM wrapper: a streaming tool-calling loop for chat, and a one-shot
weekly-review drafter. Provider-agnostic — the model string selects the
provider. No DB access here; tool execution is injected via ``run_tool``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import litellm

from app.models.ai import ResolvedLlmConfig, WeeklyDraftResponse
from app.services.ai_tools import TOOL_SCHEMAS

SYSTEM_PROMPT = (
    "You are NerveTrack's recovery assistant. The user is tracking piriformis / "
    "nerve-pain recovery. Answer using ONLY the tools provided to read their data; "
    "never invent numbers. Call tools to fetch exactly the days/weeks you need. "
    "Pain events and strengthening sessions may be tagged with pain instances "
    "(named issues) via instance_ids; call list_pain_instances to resolve those ids "
    "to names when it helps give per-issue answers. Be concise, specific, and "
    "encouraging. Dates are ISO (YYYY-MM-DD)."
)


def _completion_kwargs(config: ResolvedLlmConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": config.model}
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["api_base"] = config.base_url
    return kwargs


def _system(extra_context: str) -> str:
    return f"{SYSTEM_PROMPT}\n\n{extra_context}" if extra_context else SYSTEM_PROMPT


async def stream_chat(
    config: ResolvedLlmConfig,
    history: list[dict],
    run_tool: Callable[[str, dict], Any],
    max_iters: int = 8,
    extra_context: str = "",
) -> AsyncIterator[dict]:
    """Run the tool loop, streaming assistant tokens. Yields token/tool/final events."""
    messages: list[dict] = [{"role": "system", "content": _system(extra_context)}, *history]

    for _ in range(max_iters):
        stream = await litellm.acompletion(
            messages=messages, tools=TOOL_SCHEMAS, stream=True, **_completion_kwargs(config)
        )
        content_parts: list[str] = []
        tool_acc: dict[int, dict] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content_parts.append(delta.content)
                yield {"type": "token", "text": delta.content}
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_acc.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["args"] += tc.function.arguments

        if not tool_acc:
            yield {"type": "final", "content": "".join(content_parts)}
            return

        # Record the assistant's tool-call turn, then execute each tool.
        messages.append({
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": [
                {"id": s["id"], "type": "function",
                 "function": {"name": s["name"], "arguments": s["args"] or "{}"}}
                for s in tool_acc.values()
            ],
        })
        for s in tool_acc.values():
            yield {"type": "tool", "name": s["name"]}
            try:
                args = json.loads(s["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(s["name"], args)
            messages.append({
                "role": "tool",
                "tool_call_id": s["id"],
                "content": json.dumps(result, default=str),
            })

    # Hit the iteration guard: ask once more for a final answer without tools.
    final = await litellm.acompletion(messages=messages, **_completion_kwargs(config))
    yield {"type": "final", "content": final.choices[0].message.content or ""}


async def draft_weekly(
    config: ResolvedLlmConfig, bundle: dict, extra_context: str = ""
) -> WeeklyDraftResponse:
    prompt = (
        "Draft this week's review from the JSON data below. Respond with ONLY a JSON "
        'object: {"key_observations": <retrospective narrative of what happened, in '
        'the user\'s established concise style>, "next_steps": <forward-looking '
        "suggestions/plan for the upcoming week>}. No prose outside the JSON.\n\n"
        + json.dumps(bundle, default=str)
    )
    resp = await litellm.acompletion(
        messages=[{"role": "system", "content": _system(extra_context)},
                  {"role": "user", "content": prompt}],
        **_completion_kwargs(config),
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    return WeeklyDraftResponse(
        key_observations=data.get("key_observations", ""),
        next_steps=data.get("next_steps", ""),
    )
