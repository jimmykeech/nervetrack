"""LiteLLM wrapper: a streaming tool-calling loop for chat, and a one-shot
weekly-review drafter. Provider-agnostic — the model string selects the
provider. No DB access here; tool execution is injected via ``run_tool``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
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

KEY_MARKER = "<<<KEY_OBSERVATIONS>>>"
NEXT_MARKER = "<<<NEXT_STEPS>>>"


@asynccontextmanager
async def litellm_http_clients() -> AsyncIterator[None]:
    """Install application-owned LiteLLM clients that never follow redirects."""
    previous_async = litellm.aclient_session
    previous_sync = litellm.client_session
    async_client = httpx.AsyncClient(follow_redirects=False)
    sync_client = httpx.Client(follow_redirects=False)
    litellm.aclient_session = async_client
    litellm.client_session = sync_client
    try:
        yield
    finally:
        litellm.aclient_session = previous_async
        litellm.client_session = previous_sync
        await async_client.aclose()
        sync_client.close()


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


def _strip_markers(text: str) -> str:
    """Drop any stray marker the model echoed back, so none reaches the user."""
    return text.replace(KEY_MARKER, "").replace(NEXT_MARKER, "").strip()


def _parse_draft(raw: str) -> WeeklyDraftResponse:
    """Split a delimited draft into its two fields.

    Never raises: a malformed reply still yields something the user can edit
    rather than a 500. Delimiters are used instead of JSON because the payload
    is multi-line markdown, which models routinely fail to escape inside a JSON
    string value.

    Markers are located by position rather than by membership, so a reply that
    carries only the NEXT marker still splits correctly instead of dumping the
    marker text into key_observations. Repeated markers are stripped: the
    prompt instructs the model to emit these exact strings, so a model echoing
    its own instructions is a realistic reply, and the result is rendered
    straight to the user.
    """
    key_at = raw.find(KEY_MARKER)
    body = raw[key_at + len(KEY_MARKER) :] if key_at != -1 else raw
    next_at = body.find(NEXT_MARKER)
    if next_at == -1:
        obs, nxt = body, ""
    else:
        obs = body[:next_at]
        nxt = body[next_at + len(NEXT_MARKER) :]
    return WeeklyDraftResponse(
        key_observations=_strip_markers(obs), next_steps=_strip_markers(nxt)
    )


async def draft_weekly(
    config: ResolvedLlmConfig, bundle: dict, extra_context: str = ""
) -> WeeklyDraftResponse:
    prompt = (
        "Draft this week's review from the JSON data below.\n\n"
        "Write both fields as markdown. Structure the key observations with `###` "
        "headings drawn from this menu, using ONLY the sections this week's data "
        "supports — skip any you would have to pad:\n\n"
        "  ### The week at a glance   — the headline numbers and how they compare\n"
        "  ### What stood out         — the notable events, sessions, and symptoms\n"
        "  ### Analysis               — why it matters\n"
        "  ### Watch-outs             — anything to keep an eye on\n\n"
        "Open Analysis with a single bolded sentence naming the most significant "
        "thing in this week's data, then argue it from the sequence of days: name "
        "the days, the numbers, and the exercises involved. Where `history` "
        'supports it, compare against earlier program weeks by number (e.g. "matching '
        'W8, W11, W17"). Never cite a week that is not present in `history`, and '
        "never invent a number.\n\n"
        "`recent_reviews` shows what you already told the user in previous weeks — "
        "build on it and note what changed; never repeat it back.\n\n"
        "Aim for 350-500 words of key observations and 100-150 words of next steps. "
        "Write next steps as a short lead sentence followed by a numbered list.\n\n"
        "Respond in exactly this format, with no prose outside it:\n\n"
        f"{KEY_MARKER}\n(markdown)\n{NEXT_MARKER}\n(markdown)\n\n"
        "DATA:\n" + json.dumps(bundle, default=str)
    )
    resp = await litellm.acompletion(
        messages=[{"role": "system", "content": _system(extra_context)},
                  {"role": "user", "content": prompt}],
        **_completion_kwargs(config),
    )
    return _parse_draft(resp.choices[0].message.content or "")
