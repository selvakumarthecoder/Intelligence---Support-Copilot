
"""Part D: database-backed refund tools and resumable ReAct agent."""

from pathlib import Path
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone

import mock_llm
from src.policy_rag import PolicyRAG

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "instamart.db"
OUT = ROOT / "outputs"
STATE = ROOT / "state"
LEDGER = OUT / "refund_ledger.jsonl"

rag = PolicyRAG()


def get_order(order_id):
    with sqlite3.connect(DB) as con:
        row = con.execute(
            """
            SELECT order_id, status, order_amount, delivery_minutes
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,)
        ).fetchone()

    if row is None:
        return {"error": "order not found"}

    return {
        "order_id": row[0],
        "status": row[1],
        "order_amount": float(row[2]),
        "delivery_minutes": (
            None if row[3] is None else float(row[3])
        )
    }


def search_policy(query):
    return {"results": rag.retrieve(query, k=3)}


def calculate_refund(order_amount, delivery_minutes):
    if delivery_minutes is None:
        return {"refund_inr": 0.0}

    amount = (
        float(order_amount)
        if float(delivery_minutes) > 45
        else 0.0
    )
    return {"refund_inr": round(amount, 2)}


def _ledger(tool_name, order_id, refund_inr):
    OUT.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "order_id": order_id,
        "refund_inr": round(float(refund_inr), 2)
    }

    with LEDGER.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")

    return {"refund_inr": entry["refund_inr"]}


def issue_refund(order_id, refund_inr):
    return _ledger("issue_refund", order_id, refund_inr)


def escalate_to_human(order_id, refund_inr):
    return _ledger("escalate_to_human", order_id, refund_inr)


TOOL_MAP = {
    "get_order": get_order,
    "search_policy": search_policy,
    "calculate_refund": calculate_refund,
    "issue_refund": issue_refund,
    "escalate_to_human": escalate_to_human
}


TOOLS_SPEC = [
    {
        "name": "get_order",
        "description": "Look up an order in the Instamart database.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"]
        }
    },
    {
        "name": "search_policy",
        "description": "Retrieve relevant policy document chunks.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "calculate_refund",
        "description": "Calculate the eligible late-delivery refund.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_amount": {"type": "number"},
                "delivery_minutes": {"type": "number"}
            },
            "required": ["order_amount", "delivery_minutes"]
        }
    },
    {
        "name": "issue_refund",
        "description": "Record an automatically approved refund.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "refund_inr": {"type": "number"}
            },
            "required": ["order_id", "refund_inr"]
        }
    },
    {
        "name": "escalate_to_human",
        "description": "Record a refund requiring human approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "refund_inr": {"type": "number"}
            },
            "required": ["order_id", "refund_inr"]
        }
    }
]


class SimulatedCrash(Exception):
    """Used to demonstrate recovery from a saved checkpoint."""


def checkpoint_path(run_id):
    return STATE / f"{run_id}.json"


def save_checkpoint(state):
    STATE.mkdir(parents=True, exist_ok=True)
    with checkpoint_path(state["run_id"]).open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(state, file, indent=2, default=str)


def agent_fallback(status, state, reason):
    return {
        "status": status,
        "final_answer": (
            f"{status}: {reason} "
            "Please hand this request to a human support agent."
        ),
        "steps": state["steps"],
        "llm_calls": state["llm_calls"],
        "tokens_used": state["tokens_used"],
        "run_id": state["run_id"]
    }


def continue_agent(state, crash_after_tool=None):
    start_time = time.monotonic()
    tools_this_call = 0

    while state["llm_calls"] < state["max_iterations"]:
        if time.monotonic() - start_time >= state["time_limit_seconds"]:
            return agent_fallback(
                "FALLBACK_TIMEOUT",
                state,
                "The agent reached its execution time limit."
            )

        response = mock_llm.chat(
            state["messages"],
            tools=TOOLS_SPEC
        )
        state["llm_calls"] += 1
        state["tokens_used"] += response.usage.total_tokens

        if state["tokens_used"] > state["token_limit"]:
            save_checkpoint(state)
            return agent_fallback(
                "FALLBACK_TOKEN_LIMIT",
                state,
                "The agent exceeded its token limit."
            )

        message = response.choices[0].message
        tool_calls = message.tool_calls

        if not tool_calls:
            final_answer = message.content or "No final answer was returned."
            status = final_answer.split(":", 1)[0].strip().upper()

            return {
                "status": status,
                "final_answer": final_answer,
                "steps": state["steps"],
                "llm_calls": state["llm_calls"],
                "tokens_used": state["tokens_used"],
                "run_id": state["run_id"]
            }

        assistant_calls = []

        for tool_call in tool_calls:
            arguments = tool_call.arguments
            if isinstance(arguments, str):
                arguments = json.loads(arguments)

            assistant_calls.append({
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": arguments
            })

        state["messages"].append({
            "role": "assistant",
            "content": None,
            "tool_calls": assistant_calls
        })

        for tool_call in assistant_calls:
            tool_name = tool_call["name"]
            arguments = tool_call["arguments"]

            if tool_name not in TOOL_MAP:
                observation = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    observation = TOOL_MAP[tool_name](**arguments)
                except (TypeError, ValueError) as error:
                    observation = {"error": str(error)}

            state["messages"].append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": tool_name,
                "content": json.dumps(observation)
            })

            state["steps"].append({
                "tool": tool_name,
                "arguments": arguments,
                "observation": observation
            })

            state["step_number"] += 1
            state["tools_executed"].append(tool_name)
            tools_this_call += 1

            save_checkpoint(state)

            if (
                crash_after_tool is not None
                and tools_this_call >= crash_after_tool
            ):
                raise SimulatedCrash(
                    f"Simulated crash after tool execution {tools_this_call}."
                )

    return agent_fallback(
        "FALLBACK_MAX_ITERATIONS",
        state,
        "The agent reached its maximum number of model calls."
    )


def run_agent(
    user_message,
    scenario_id="demo",
    max_iterations=6,
    token_limit=6000,
    time_limit_seconds=10,
    run_id=None,
    crash_after_tool=None
):
    run_id = run_id or f"{scenario_id}_{time.time_ns()}"

    state = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an AGENT for the Instamart refund workflow. "
                    "Use the available tools to check the order and relevant policy. "
                    "Follow the refund rules strictly. Only completed orders are eligible. "
                    "Refunds above INR 1000 must be escalated to a human. "
                    "Do not claim that a refund was issued unless the issue_refund tool "
                    "confirms it. Return a concise final answer beginning with "
                    "REFUND, ESCALATE, DENIED, or NOT_FOUND as appropriate."
                )
            },
            {"role": "user", "content": user_message}
        ],
        "steps": [],
        "tokens_used": 0,
        "llm_calls": 0,
        "step_number": 0,
        "tools_executed": [],
        "max_iterations": max_iterations,
        "token_limit": token_limit,
        "time_limit_seconds": time_limit_seconds
    }

    save_checkpoint(state)
    return continue_agent(state, crash_after_tool=crash_after_tool)


def resume_agent(run_id):
    path = checkpoint_path(run_id)

    if not path.exists():
        raise FileNotFoundError(f"No checkpoint found for run: {run_id}")

    with path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    return continue_agent(state)
