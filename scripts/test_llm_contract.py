"""Quick end-to-end test: LLM contract compilation with real DeepSeek."""

import asyncio
import json
import os
import sys

# Ensure the project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# Load .env from project root
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

_LLM_CONTRACT_PROMPT = """You are a requirements analyst. Given a requirement specification,
extract all verifiable contracts as JSON.

For each requirement, produce a contract with:
- id: short kebab-case identifier (e.g. "AUTH-01", "UNIQUE-01")
- checker_type: one of [http, sql, redis, openapi, rabbitmq]
- requirement: the requirement text (max 200 chars)
- expected_behavior: concrete, testable description of expected behavior

Return a JSON array of contract objects. No other text.

Requirement specification:
{spec_text}

Contracts (JSON array):"""


async def test_llm_contracts() -> int:
    req_path = os.path.join(_project_root, "demo", "requirement.txt")
    with open(req_path, encoding="utf-8") as f:
        spec_text = f.read()

    from providers.base import LLMMessage
    from providers.openai_compatible import OpenAICompatibleProvider

    p = OpenAICompatibleProvider()
    prompt = _LLM_CONTRACT_PROMPT.format(spec_text=spec_text[:4000])

    r = await p.chat([LLMMessage(role="user", content=prompt)], timeout=120)
    content = r.content or ""
    print("Raw response (first 400 chars):")
    print(content[:400])
    print()

    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        contracts = json.loads(content[start:end])
        print(f"Contracts extracted: {len(contracts)}")
        for c in contracts:
            print(f"  [{c.get('id')}] {c.get('checker_type')}: {c.get('requirement', '')[:80]}")
    else:
        print("ERROR: Could not extract JSON array")
        print("Full content:", content)

    await p.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(test_llm_contracts()))
