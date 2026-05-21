import os, json, re
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

# Use a hardcoded test — simulates exactly what the LLM returns
# for a simple buggy function

SYSTEM_PROMPT = """You are an expert Python code reviewer.
Respond with ONLY a valid JSON array of review comments.
Return [] if no issues found."""

USER_PROMPT = """Review this Python code chunk:

File: codetiming/_timer.py
Chunk: Timer.__init__ (function)
Lines: 1-20

Code:
```python
def __init__(self, name=None, text="Elapsed time: {:0.4f} seconds", logger=print, initial_text=False):
    self.name = name
    self.text = text
    self.logger = logger
    self.initial_text = initial_text
    self._start_time = None
```

Return ONLY valid JSON array of comments. Return [] if no issues."""

keys = []
for i in range(1, 4):
    val = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
    if val and len(val) > 30:
        keys.append(val)

if not keys:
    print("NO KEYS FOUND - check .env file")
else:
    print(f"Found {len(keys)} key(s)")
    client = Groq(api_key=keys[0])
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0.1,
        max_tokens=1200,
    )
    raw = response.choices[0].message.content.strip()
    print("\n=== RAW LLM RESPONSE ===")
    print(raw)
    print("\n=== PARSED JSON ===")
    try:
        text = re.sub(r"```(?:json)?\s*", "", raw)
        text = text.replace("```", "").strip()
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            parsed = json.loads(text[start:end+1])
            print(json.dumps(parsed, indent=2))
            print(f"\n=== FIELD NAMES IN FIRST COMMENT ===")
            if parsed:
                print(list(parsed[0].keys()))
        else:
            print("No JSON array found in response")
    except Exception as e:
        print(f"Parse error: {e}")