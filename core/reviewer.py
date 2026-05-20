# ═══════════════════════════════════════════════════════════════
# core/reviewer.py
# FINAL WORKING VERSION - Phase 3
# ═══════════════════════════════════════════════════════════════

import os
import json
import time
import re
from groq import Groq
from dotenv import load_dotenv

# ── Setup ─────────────────────────────────────────────────────
load_dotenv(override=True)

for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"

# ── Config ────────────────────────────────────────────────────
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5

_key_index = 0


def _get_all_keys():
    keys = []
    for i in range(1, 4):
        val = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if val and len(val) > 30 and not val.startswith("your_"):
            keys.append(val)
    return keys


def _get_next_client():
    global _key_index
    keys = _get_all_keys()
    if not keys:
        raise ValueError("No Groq API keys found!")

    key = keys[_key_index % len(keys)]
    key_num = (_key_index % len(keys)) + 1
    _key_index += 1

    client = Groq(api_key=key)
    return client, key_num


# ── Prompts ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert Python code reviewer.
Respond with ONLY a valid JSON array of review comments.
Return [] if no issues found."""


def _build_user_prompt(chunk):
    parts = [
        "Review this Python code chunk:\n\n",
        f"File: {chunk.get('file')}\n",
        f"Chunk: {chunk.get('name')} ({chunk.get('type')})\n",
        f"Lines: {chunk.get('start_line')}-{chunk.get('end_line')}\n\n"
    ]

    imports = chunk.get("imports") or []
    if imports:
        parts.append("Imports:\n" + "\n".join(str(x) for x in imports[:10]) + "\n\n")

    if chunk.get("is_large"):
        parts.append("Note: Large function.\n")
    if chunk.get("parse_error"):
        parts.append("Note: Syntax error present.\n")

    parts.append("\nCode:\n```python\n" + str(chunk.get('code', '')) + "\n```\n\n")
    parts.append("Return ONLY valid JSON array of comments. Return [] if no issues.")

    return "".join(parts)


def review_chunk(chunk):
    user_prompt = _build_user_prompt(chunk)
    model_used = PRIMARY_MODEL
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            client, key_num = _get_next_client()
            if attempt == 1:
                model_used = FALLBACK_MODEL

            print(f"  [LLM] {str(chunk.get('name',''))[:40]:<40} key={key_num}")

            response = client.chat.completions.create(
                model=model_used,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1200,
            )

            raw_text = response.choices[0].message.content.strip()
            comments = _parse_llm_response(raw_text, chunk)

            # Strong safety net
            if not isinstance(comments, list):
                comments = []

            return {
                "chunk_id": chunk["chunk_id"],
                "file": chunk["file"],
                "name": chunk["name"],
                "type": chunk["type"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "comments": comments,
                "model_used": model_used,
                "key_used": key_num,
                "error": None
            }

        except Exception as e:
            last_error = str(e)
            print(f"  [LLM] Attempt {attempt+1} failed: {last_error[:100]}")
            time.sleep(RETRY_BASE_DELAY * (attempt + 1))

    return {
        "chunk_id": chunk["chunk_id"],
        "file": chunk["file"],
        "name": chunk["name"],
        "type": chunk["type"],
        "start_line": chunk["start_line"],
        "end_line": chunk["end_line"],
        "comments": [],
        "model_used": model_used,
        "key_used": -1,
        "error": last_error
    }


def _parse_llm_response(raw_text: str, chunk: dict) -> list:
    if not raw_text or not isinstance(raw_text, str):
        return []

    text = re.sub(r"```(?:json)?\s*", "", raw_text)
    text = text.replace("```", "").strip()

    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1:
        obj_start = text.find("{")
        obj_end = text.rfind("}")
        if obj_start != -1 and obj_end != -1:
            text = "[" + text[obj_start:obj_end + 1] + "]"
            start = 0
            end = len(text) - 1
        else:
            return []

    json_str = text[start:end + 1]

    try:
        comments = json.loads(json_str)
        if isinstance(comments, dict):
            comments = [comments]
        if not isinstance(comments, list):
            return []
        return [_sanitize_comment(item) for item in comments if isinstance(item, dict)]
    except Exception:
        return []


def _sanitize_comment(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None

    # Accept both description and detail — LLM sometimes uses either field name
    issue = str(raw.get("issue", "")).strip()
    desc = str(raw.get("description", raw.get("detail", ""))).strip()

    if not issue and not desc:
        return None

    severity = str(raw.get("severity", "medium")).lower().strip()
    category = str(raw.get("category", "maintainability")).lower().strip()

    try:
        confidence = int(raw.get("confidence", 70))
        confidence = max(0, min(100, confidence))
    except (ValueError, TypeError):
        confidence = 70

    return {
        "issue": issue or "Code issue detected",
        "description": desc or "Issue found in the code.",
        "suggestion": str(raw.get("suggestion", "Review this section manually.")),
        "severity": severity if severity in {"critical", "high", "medium", "low", "info"} else "medium",
        "category": category if category in {"bug", "security", "performance", "style", "maintainability", "error_handling", "documentation"} else "maintainability",
        "line_hint": str(raw.get("line_hint", "unknown")),
        "confidence": confidence,
        "confidence_tier": _get_confidence_tier(confidence)
    }


def _get_confidence_tier(score: int) -> str:
    if score >= 75:
        return "high"
    elif score >= 50:
        return "medium"
    return "low"


def review_all_chunks(chunks: list, progress_callback=None) -> list:
    results = []
    for i, chunk in enumerate(chunks, 1):
        if progress_callback:
            progress_callback(i, len(chunks), chunk.get("name", ""))
        results.append(review_chunk(chunk))
        time.sleep(0.7)
    return results


def get_review_summary(results: list) -> dict:
    all_comments = []
    for r in results:
        comments = r.get("comments")
        if isinstance(comments, list):
            all_comments.extend(comments)

    severity_counts = {"critical":0, "high":0, "medium":0, "low":0, "info":0}
    for c in all_comments:
        severity_counts[c.get("severity", "medium")] += 1

    tier_counts = {"high":0, "medium":0, "low":0}
    for c in all_comments:
        tier_counts[c.get("confidence_tier", "medium")] += 1

    confidences = [c.get("confidence", 0) for c in all_comments]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0

    return {
        "total_chunks": len(results),
        "total_comments": len(all_comments),
        "severity_counts": severity_counts,
        "tier_counts": tier_counts,
        "avg_confidence": avg_confidence,
        "failed_chunks": sum(1 for r in results if r.get("error")),
        "files_reviewed": len(set(r.get("file", "") for r in results))
    }