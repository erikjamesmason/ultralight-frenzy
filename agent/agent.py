"""Claude agentic loop for gear queries."""

from __future__ import annotations

import logging
import os
from typing import Any

import anthropic

from agent.tools import TOOL_DEFINITIONS, dispatch_tool

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_ITERATIONS = 10

SYSTEM_PROMPT = """\
You are an expert ultralight backpacking gear assistant with access to a curated \
gear database. You help hikers find, compare, and choose gear for minimizing pack weight \
without sacrificing safety or comfort.

When answering queries:
- Use the tools available to search and retrieve gear data.
- Always cite specific item names, weights, and prices from the database.
- Convert weights to both grams and lbs/oz when relevant.
- For kit-building, consider balance across shelter, sleep, pack, and layers.
- Be concise but specific — hikers want numbers, not generalities.
"""


async def run_query(user_message: str) -> str:
    """
    Run an agentic query against the gear database.
    Returns the final text response from Claude.
    """
    client = anthropic.AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_message}
    ]

    for iteration in range(MAX_ITERATIONS):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
            messages=messages,
        )

        logger.debug(
            "Agent iteration %d — stop_reason=%s, blocks=%d",
            iteration + 1,
            response.stop_reason,
            len(response.content),
        )

        if response.stop_reason == "end_turn":
            # Extract final text response
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "(No text response)"

        if response.stop_reason != "tool_use":
            # Unexpected stop reason
            for block in response.content:
                if block.type == "text":
                    return block.text
            return f"Stopped unexpectedly: {response.stop_reason}"

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        # Execute all tool calls and collect results
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, list(block.input.keys()))
                result_text = dispatch_tool(block.name, dict(block.input))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        messages.append({"role": "user", "content": tool_results})

    return "Reached maximum iterations without a final response."


def run_query_sync(user_message: str) -> str:
    """Synchronous wrapper for CLI use."""
    import asyncio
    return asyncio.run(run_query(user_message))
