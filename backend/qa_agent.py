"""Free-form Q&A over reconciliation results, via Ollama tool-calling.

Replaces the Phase 4 pattern-matched stub. The agent has NO knowledge of
this batch's data except what it gets back from tool calls into audit.py —
it cannot answer from memory or guess, only from what a tool actually
returned. Every record ID surfaced by a tool call is tracked and returned
as `sourced_from`, so a caller can independently verify the answer is
grounded in real data, not invented.

Tool-calling was verified to work with the cloud model during Phase 5 build
(unlike the `format=` structured-output constraint from Phase 2, which
isn't honored for cloud models — see docs/BUILD-CHALLENGES.md).
"""

import json
import os

import ollama

import audit

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b-cloud")
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = """You are a reconciliation assistant for a finance-ops team. You answer questions about a Razorpay settlement reconciliation batch using ONLY the tools provided — you have no other knowledge of this batch's data.

Rules:
- Call tools to get real data before answering. Never state a number, amount, or record ID that did not come from a tool result.
- If the tools don't have the information needed to answer, say so plainly — do not guess or estimate.
- When you cite a record, use its exact ID (settlement_id or txn_id) as returned by the tools.
- Keep answers concise and specific."""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Get summary statistics for the reconciliation run: match rate, total settlements, matched count (rule vs LLM), and exception counts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_exceptions",
            "description": "List all exception records (settlements or bank entries that could not be matched), each with its reason.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_matches",
            "description": "List matched records, optionally filtered by confidence tier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confidence": {
                        "type": "string",
                        "description": "Filter to one confidence tier",
                        "enum": ["exact", "fuzzy-date", "fuzzy-amount", "fuzzy-date-amount", "llm-reasoned"],
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trace",
            "description": "Get the full decision trace for one record: its match/exception status, reason, and the exact source settlement/bank row(s) it is based on.",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {
                        "type": "string",
                        "description": "A settlement_id (e.g. STL12345678) or bank txn_id (e.g. BTXN1234567890)",
                    }
                },
                "required": ["record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unmatched_bank_entries_over_amount",
            "description": "List bank entries with no settlement match (bank-side exceptions) with amount greater than a given threshold, in Rupees.",
            "parameters": {
                "type": "object",
                "properties": {"min_amount": {"type": "number", "description": "Threshold amount in Rupees"}},
                "required": ["min_amount"],
            },
        },
    },
]


def _build_tool_dispatch(conn, run_id):
    def get_stats():
        run = audit.get_run(conn, run_id)
        return json.loads(run["stats_json"]) if run else {"error": "run not found"}

    def list_exceptions():
        rows = audit.list_exceptions(conn, run_id)
        return [{"settlement_ref": r["settlement_ref"], "bank_ref": r["bank_ref"], "reason": r["reason"]}
                for r in rows]

    def list_matches(confidence=None):
        rows = audit.list_matches(conn, run_id)
        if confidence:
            rows = [r for r in rows if r["confidence"] == confidence]
        return [{"settlement_ref": r["settlement_ref"], "bank_ref": r["bank_ref"],
                  "confidence": r["confidence"], "reason": r["reason"]} for r in rows]

    def get_trace(record_id):
        return audit.get_trace(conn, record_id, run_id)

    def list_unmatched_bank_entries_over_amount(min_amount):
        return audit.list_unmatched_bank_entries_over_amount(conn, run_id, min_amount)

    return {
        "get_stats": get_stats,
        "list_exceptions": list_exceptions,
        "list_matches": list_matches,
        "get_trace": get_trace,
        "list_unmatched_bank_entries_over_amount": list_unmatched_bank_entries_over_amount,
    }


_ID_PREFIXES = ("STL", "BTXN")


def _extract_record_ids(obj, found):
    """Walk a tool result and collect anything that looks like a record id,
    so the caller can see exactly what data grounded the answer. Handles
    both dicts keyed by field name (e.g. settlement_ref) and plain lists of
    bare ID strings (e.g. candidates_considered)."""
    if isinstance(obj, dict):
        for key in ("settlement_ref", "bank_ref", "settlement_id", "txn_id", "record_id"):
            v = obj.get(key)
            if isinstance(v, str) and v:
                found.add(v)
        for v in obj.values():
            _extract_record_ids(v, found)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str) and item.startswith(_ID_PREFIXES):
                found.add(item)
            else:
                _extract_record_ids(item, found)


def answer(question, conn, run_id=None, model=None):
    """Returns {"answer": str, "sourced_from": [record_ids], "tool_calls": [...]}."""
    run_id = run_id or audit.latest_run_id(conn)
    if not run_id:
        return {"answer": "No reconciliation run found. Run /reconcile first.", "sourced_from": [], "tool_calls": []}
    if not audit.get_run(conn, run_id):
        return {"answer": f"No such run_id: '{run_id}'.", "sourced_from": [], "tool_calls": []}

    model = model or DEFAULT_MODEL
    dispatch = _build_tool_dispatch(conn, run_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    sourced_ids = set()
    tool_call_log = []

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            resp = ollama.chat(model=model, messages=messages, tools=TOOLS_SCHEMA, options={"temperature": 0})
        except Exception as e:
            return {
                "answer": f"The Q&A agent couldn't reach the LLM: {e}",
                "sourced_from": sorted(sourced_ids),
                "tool_calls": tool_call_log,
            }

        msg = resp["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # Aggregate answers (e.g. get_stats) carry no individual record
            # IDs; fall back to the run_id so every answer names what it's
            # grounded in.
            sources = sorted(sourced_ids) if sourced_ids else ([run_id] if tool_call_log else [])
            return {"answer": msg.get("content") or "", "sourced_from": sources, "tool_calls": tool_call_log}

        for call in tool_calls:
            name = call["function"]["name"]
            args = call["function"]["arguments"] or {}
            fn = dispatch.get(name)
            if fn is None:
                result = {"error": f"unknown tool '{name}'"}
            else:
                try:
                    result = fn(**args)
                except Exception as e:
                    result = {"error": str(e)}
            tool_call_log.append({"tool": name, "arguments": dict(args)})
            _extract_record_ids(result, sourced_ids)
            messages.append({"role": "tool", "content": json.dumps(result, default=str)})

    return {
        "answer": "I wasn't able to settle on an answer within the tool-call budget for this question.",
        "sourced_from": sorted(sourced_ids),
        "tool_calls": tool_call_log,
    }
