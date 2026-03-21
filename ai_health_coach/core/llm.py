"""Shared LLM instance and helpers."""

from __future__ import annotations

import json as _json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ai_health_coach.core.safety.classifier import (
    SAFE_PROMPT_ADDITION,
    check_and_filter_message,
)

_llm = None

MAX_TOOL_ROUNDS = 5  # Safety limit to prevent infinite tool-call loops


def get_llm() -> ChatOpenAI:
    """Return a shared ChatOpenAI instance."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    return _llm


def safe_generate(prompt_messages: list) -> str:
    """Generate a message via LLM with safety check and retry/fallback.

    Use this when the LLM should NOT have access to tools.
    """
    llm = get_llm()
    response = llm.invoke(prompt_messages)
    message_text = response.content

    def regenerate():
        augmented = prompt_messages.copy()
        augmented.append(SystemMessage(content=SAFE_PROMPT_ADDITION))
        return llm.invoke(augmented).content

    result = check_and_filter_message(message_text, regenerate_fn=regenerate)
    return result["final_message"]


def tool_calling_generate(
    prompt_messages: list,
    tools: list,
) -> dict[str, Any]:
    """Generate a message, letting the LLM autonomously call tools.

    The LLM sees the tool definitions and decides whether to call them.
    If it makes tool calls, we execute them and feed results back until
    the LLM produces a final text response.

    Args:
        prompt_messages: The conversation messages to send.
        tools: LangChain tool objects (from get_tools_for_phase).

    Returns:
        Dict with:
            - message: str (the final text response, safety-checked)
            - tool_calls_made: list of {"name": str, "args": dict, "result": dict}
    """
    from ai_health_coach.core.tools.definitions import execute_tool

    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    messages = list(prompt_messages)
    tool_calls_made = []

    for _round in range(MAX_TOOL_ROUNDS):
        response = llm_with_tools.invoke(messages)

        # If no tool calls, we have our final text response
        if not response.tool_calls:
            break

        # LLM wants to call tools — execute each one
        messages.append(response)  # Add the AIMessage with tool_calls

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            result = execute_tool(tool_name, tool_args)
            tool_calls_made.append({
                "name": tool_name,
                "args": tool_args,
                "result": result,
            })

            # Feed the result back to the LLM as a ToolMessage
            messages.append(ToolMessage(
                content=_json.dumps(result),
                tool_call_id=tool_call["id"],
            ))

        # Loop back so the LLM can process tool results and either
        # call more tools or produce a final text response
    else:
        # Hit max rounds — force a text response without tools
        response = llm.invoke(messages)

    # Safety check the final text
    message_text = response.content or ""

    def regenerate():
        augmented = messages.copy()
        augmented.append(SystemMessage(content=SAFE_PROMPT_ADDITION))
        return llm.invoke(augmented).content

    safety_result = check_and_filter_message(message_text, regenerate_fn=regenerate)

    return {
        "message": safety_result["final_message"],
        "tool_calls_made": tool_calls_made,
    }
