# ═══════════════════════════════════════════════════════════════
# tests/test_env_keys.py
# PURPOSE: Verify that all API keys in .env are valid and working
#          before we start Phase 3. Tests Groq + GitHub token.
# ═══════════════════════════════════════════════════════════════

import os
import sys
import requests

# Load .env file into environment variables
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─── Groq Key Tests ───────────────────────────────────────────

def test_groq_key(key_name: str):
    """Send a tiny test message to Groq and check we get a response."""
    api_key = os.getenv(key_name)

    if not api_key or api_key.startswith("your_") or api_key.startswith("gsk_xxx"):
        print(f"  ✗ {key_name} not set in .env")
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",   # current free model on Groq
        "messages": [
            {"role": "user", "content": "Reply with just the word: working"}
        ],
        "max_tokens": 10
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"]
            print(f"  ✓ {key_name} is valid — model replied: '{reply.strip()}'")
            return True
        elif response.status_code == 401:
            print(f"  ✗ {key_name} is INVALID — wrong or expired key")
            return False
        elif response.status_code == 429:
            print(f"  ⚠ {key_name} is valid but RATE LIMITED right now (try again in a minute)")
            return True   # key is real, just throttled
        else:
            print(f"  ✗ {key_name} — unexpected status {response.status_code}: {response.text[:100]}")
            return False

    except requests.exceptions.Timeout:
        print(f"  ✗ {key_name} — request timed out (check internet connection)")
        return False
    except Exception as e:
        print(f"  ✗ {key_name} — error: {e}")
        return False


# ─── GitHub Token Test ────────────────────────────────────────

def test_github_token():
    """Call GitHub API /user endpoint to verify the token."""
    token = os.getenv("GITHUB_TOKEN")

    if not token or token.startswith("optional_") or token.startswith("ghp_xxx"):
        print("  ⚠ GITHUB_TOKEN not set — skipping (optional)")
        return True   # not required, so don't fail

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(
            "https://api.github.com/user",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            username = response.json().get("login", "unknown")
            print(f"  ✓ GITHUB_TOKEN is valid — logged in as: {username}")
            return True
        elif response.status_code == 401:
            print(f"  ✗ GITHUB_TOKEN is INVALID — check the token in .env")
            return False
        else:
            print(f"  ✗ GITHUB_TOKEN — unexpected status {response.status_code}")
            return False

    except Exception as e:
        print(f"  ✗ GITHUB_TOKEN — error: {e}")
        return False


# ─── Run all tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  ENV & API KEY TESTS")
    print("═" * 55)

    results = []

    print("\n[TEST] GROQ_API_KEY_1")
    results.append(test_groq_key("GROQ_API_KEY_1"))

    print("\n[TEST] GROQ_API_KEY_2")
    results.append(test_groq_key("GROQ_API_KEY_2"))

    print("\n[TEST] GROQ_API_KEY_3")
    results.append(test_groq_key("GROQ_API_KEY_3"))

    print("\n[TEST] GITHUB_TOKEN")
    results.append(test_github_token())

    passed = sum(results)
    failed = len(results) - passed

    print("\n" + "─" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("─" * 55)

    if failed == 0:
        print("\n  ✅ All keys working — ready for Phase 3!\n")
    else:
        print("\n  ❌ Fix the failed keys before continuing.\n")