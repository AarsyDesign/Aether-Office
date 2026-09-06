"""LLM wrapper — OpenAI-compatible API with reliability."""

from __future__ import annotations
import os
import json
import time
import logging
import requests
from typing import Any

logger = logging.getLogger("aether.llm")


def _generate_mock_response(messages: list[dict], json_mode: bool = False) -> tuple[str, dict | None]:
    """Generate realistic offline simulation responses for Aether Office agents."""
    last_msg = str(messages[-1].get("content", "")) if messages else ""
    system_msg = str(messages[0].get("content", "")) if len(messages) > 1 else ""
    sys_lower = system_msg.lower()
    user_lower = last_msg.lower()

    usage = {"prompt_tokens": 150, "completion_tokens": 120, "total_tokens": 270}

    # 1. Developer Planner (Software Architect / Implementation Plan)
    if "developer planner" in sys_lower or "software architect" in sys_lower or ("files" in sys_lower and "project_summary" in sys_lower):
        res = {
            "project_summary": "Modular application with robust design",
            "tech_stack": "Python 3.11, SQLite",
            "files": [
                {
                    "path": "core.py",
                    "purpose": "Core business logic and handlers",
                    "dependencies": [],
                    "exports": ["run_app"],
                    "depends_on": [],
                    "priority": 1,
                },
                {
                    "path": "test_core.py",
                    "purpose": "Automated test suite",
                    "dependencies": [],
                    "exports": ["TestApp"],
                    "depends_on": ["core.py"],
                    "priority": 2,
                }
            ],
            "generation_order": ["core.py", "test_core.py"]
        }
        return (json.dumps(res), usage) if json_mode else (json.dumps(res), usage)

    # 2. QA Agent (Test Runner / Verdict)
    if "qa" in sys_lower or "verdict" in sys_lower:
        res = {
            "verdict": "PASS",
            "summary": "Automated verification completed with 0 errors. All test suites passed.",
            "criteria_results": [
                {"criterion": "Application core runs successfully", "status": "PASS", "evidence": "Verified with clean exit code 0", "severity": "minor"}
            ],
            "bugs_found": [],
            "test_commands_to_run": ["python -m compileall . -q"],
            "fix_instructions": ""
        }
        return (json.dumps(res), usage) if json_mode else ("VERDICT: PASS\nAll tests passed successfully.", usage)

    # 3. Project Manager (Brief breakdown into tasks)
    if "project manager" in sys_lower or "product manager" in sys_lower or "breakdown" in sys_lower or "brief" in user_lower:
        res = {
            "project_name": "Aether Automated Project",
            "project_description": "Autonomous end-to-end outcome verified by Aether Office.",
            "tasks": [
                {"title": "Setup project core architecture", "description": "Initialize modules", "priority": 5, "dependencies": []},
                {"title": "Implement core services and logic", "description": "Business logic implementation", "priority": 4, "dependencies": [0]},
                {"title": "Add test suites and verification", "description": "Automated tests", "priority": 3, "dependencies": [1]},
            ]
        }
        return (json.dumps(res), usage) if json_mode else (json.dumps(res), usage)

    # 4. Product Conceptor (Requirements & Specifications)
    if "conceptor" in sys_lower or "requirements" in sys_lower and "acceptance criteria" in sys_lower:
        req_doc = (
            "# System Requirements Specification\n\n"
            "## Acceptance Criteria\n"
            "1. Application core runs successfully with verified exit code 0.\n"
            "2. All business logic functions return valid structured payload.\n"
            "3. Automated test cases pass without regressions.\n\n"
            "## Technical Design\n"
            "Modular architecture in Python with unit testing."
        )
        return (json.dumps({"requirements": req_doc}), usage) if json_mode else (req_doc, usage)

    # 5. Developer Code Generator (Generating file content)
    if "developer" in sys_lower or "code" in user_lower or "unit" in user_lower:
        if "test" in user_lower:
            code_body = '"""Automated test suite."""\nimport unittest\n\nclass TestApp(unittest.TestCase):\n    def test_core(self):\n        self.assertTrue(True)\n\nif __name__ == "__main__":\n    unittest.main()\n\n'
            target_path = "test_core.py"
        else:
            code_body = '"""Core module implementation."""\n\ndef run_app():\n    return {"status": "ok", "message": "Outcome verified"}\n\nif __name__ == "__main__":\n    print(run_app())\n\n'
            target_path = "core.py"

        if json_mode:
            return json.dumps({"path": target_path, "content": code_body}), usage
        return f"```python\n{code_body}```\n", usage

    # Default fallback
    if json_mode:
        return json.dumps({"status": "COMPLETED", "message": "Simulation response"}), usage
    return "Aether Office agent successfully processed instruction in offline mode.", usage


class LLMError(Exception):
    """Base LLM error."""
    def __init__(self, message: str, attempt: int = 0, retries_left: int = 0):
        super().__init__(message)
        self.attempt = attempt
        self.retries_left = retries_left


class LLMAuthError(LLMError):
    """Auth failure — no retry."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limited — retry with backoff."""
    pass


class LLMTimeoutError(LLMError):
    """Request timeout — retry."""
    pass


class LLMResponseError(LLMError):
    """Empty, malformed, or invalid response — retry."""
    pass


def _clean_raw(text: str) -> str:
    """Strip trailing SSE artifacts from response."""
    text = text.strip()
    # Some providers append "data: [DONE]" after JSON
    idx = text.rfind("data: [DONE]")
    if idx >= 0:
        text = text[:idx].strip()
    return text


def _extract_content(msg: dict) -> str:
    """Extract text from message, handling reasoning models."""
    content = msg.get("content")
    reasoning = msg.get("reasoning_content") or msg.get("reasoning")
    if content:
        return content
    if reasoning:
        return reasoning
    return ""


def _extract_usage(data: dict) -> dict | None:
    """Extract token usage from response."""
    usage = data.get("usage")
    if usage:
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
    return None


def call_llm(
    endpoint: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    timeout: int = 300,
    extra_body: dict | None = None,
) -> tuple[str, dict | None]:
    """Call LLM. Returns (content, usage). Raises LLMError on failure."""
    # Check offline mock mode
    if endpoint.startswith("mock://") or os.environ.get("AETHER_MOCK_LLM") == "1":
        return _generate_mock_response(messages, json_mode=json_mode)

    ep = endpoint.rstrip('/')
    url = ep if ep.endswith("/chat/completions") else f"{ep}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra_body and isinstance(extra_body, dict):
        payload.update(extra_body)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # --- HTTP call ---
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        raise LLMTimeoutError(f"Connection failed: {e}")
    except requests.exceptions.Timeout as e:
        raise LLMTimeoutError(f"Request timed out ({timeout}s): {e}")
    except requests.exceptions.RequestException as e:
        raise LLMError(f"HTTP error: {e}")

    # --- HTTP status ---
    if resp.status_code == 401:
        raise LLMAuthError("Invalid API key (401)")
    if resp.status_code == 403:
        raise LLMAuthError("Access denied (403)")
    if resp.status_code == 429:
        raise LLMRateLimitError(f"Rate limited (429)")
    if resp.status_code >= 500:
        raise LLMError(f"Server error ({resp.status_code})")
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    # --- Parse response ---
    raw = _clean_raw(resp.text)
    if not raw:
        raise LLMResponseError("Empty response body")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMResponseError(f"Malformed JSON: {e}")

    # --- Validate structure ---
    choices = data.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        raise LLMResponseError("No choices in response")

    msg = choices[0].get("message")
    if not msg:
        raise LLMResponseError("No message in choice")

    content = _extract_content(msg)
    usage = _extract_usage(data)

    if not content:
        raise LLMResponseError("Empty content in message (content=null, no reasoning_content)")

    return content, usage


def call_llm_json(
    endpoint: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = 300,
    extra_body: dict | None = None,
) -> tuple[dict, dict | None]:
    """Call LLM expecting JSON. Returns (parsed_dict, usage)."""
    import re
    content, usage = call_llm(endpoint, api_key, model, messages,
                              temperature, max_tokens, json_mode=True, timeout=timeout, extra_body=extra_body)
    # Strip reasoning tags if present
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # 1. Direct parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed, usage
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed, usage
        except json.JSONDecodeError:
            pass

    # 3. Extract from first { to last }
    json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed, usage
        except json.JSONDecodeError:
            pass

    raise LLMResponseError(f"Could not parse valid JSON object from response: {content[:200]}")


# --- Retry wrapper ---

def call_llm_with_retry(
    endpoint: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    timeout: int = 300,
    max_retries: int = 3,
    extra_body: dict | None = None,
) -> tuple[str | dict, dict | None]:
    """Call LLM with retry. Returns (content_or_dict, usage). Raises after max_retries."""
    last_error = None
    for attempt in range(max_retries):
        try:
            if json_mode:
                result, usage = call_llm_json(endpoint, api_key, model, messages,
                                              temperature, max_tokens, timeout, extra_body=extra_body)
                return result, usage
            else:
                result, usage = call_llm(endpoint, api_key, model, messages,
                                         temperature, max_tokens, json_mode=False, timeout=timeout, extra_body=extra_body)
                return result, usage
        except LLMAuthError:
            raise  # Never retry auth errors
        except (LLMRateLimitError, LLMTimeoutError, LLMResponseError, LLMError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = min((2 ** attempt) * 5, 60)  # 5s, 10s, 20s, cap 60s
                logger.warning(f"LLM attempt {attempt+1}/{max_retries} failed: {e}. Retry in {wait}s")
                print(f"   ⚠ Attempt {attempt+1}/{max_retries}: {e}. Retry in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"LLM failed after {max_retries} attempts: {e}")

    raise LLMError(f"LLM failed after {max_retries} attempts: {last_error}",
                   attempt=max_retries, retries_left=0)


class LLMClient:
    """Reusable LLM client supporting single endpoints or central LLM Routers (with multiple models)."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout: int = 300,
        extra_body: dict | None = None,
        models: dict | None = None,
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self.extra_body = dict(extra_body) if extra_body else {}
        self.models = dict(models) if models else {}

    def for_model(self, model_name: str, extra_body: dict | None = None) -> "LLMClient":
        """Spawn a new LLMClient sharing the same router credentials but targeting a different model."""
        return LLMClient(
            endpoint=self.endpoint,
            api_key=self.api_key,
            model=model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            max_retries=self.max_retries,
            timeout=self.timeout,
            extra_body=extra_body if extra_body is not None else self.extra_body,
            models=self.models,
        )

    def for_role(self, role: str) -> "LLMClient":
        """Resolve and return an LLMClient instance configured for a specific role on this router."""
        if not self.models:
            return self
        role_lower = (role or "").lower()
        target = self.models.get(role_lower)
        if not target and "_" in role_lower:
            for part in role_lower.split("_"):
                if part in self.models:
                    target = self.models[part]
                    break
        if not target:
            target = self.models.get("default", self.model)

        if isinstance(target, dict):
            return LLMClient(
                endpoint=target.get("endpoint", self.endpoint),
                api_key=target.get("api_key", self.api_key),
                model=target.get("model", self.model),
                temperature=target.get("temperature", self.temperature),
                max_tokens=target.get("max_tokens", self.max_tokens),
                max_retries=target.get("max_retries", self.max_retries),
                timeout=target.get("timeout", self.timeout),
                extra_body=target.get("extra_body", self.extra_body),
                models=self.models,
            )
        elif isinstance(target, str) and target != self.model:
            return self.for_model(target)
        return self

    def list_available_models(self) -> list[str]:
        """Query the router's /models endpoint to discover all routed models."""
        if self.endpoint.startswith("mock://") or os.environ.get("AETHER_MOCK_LLM") == "1":
            return ["mock-model", "mock-fast", "mock-smart"]
        try:
            url = f"{self.endpoint.rstrip('/')}/models"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                raw_models = data.get("data", [])
                if isinstance(raw_models, list):
                    return [
                        m.get("id") for m in raw_models
                        if isinstance(m, dict) and "id" in m
                    ]
        except Exception as e:
            logger.debug(f"Could not query router models at {self.endpoint}: {e}")
        return []

    def chat(
        self,
        system: str,
        user: str | None = None,
        json_mode: bool = False,
        model: str | None = None,
        extra_body: dict | None = None,
    ) -> str | dict:
        """Single-turn chat. Supports router model override."""
        if isinstance(user, bool):
            json_mode = user
            user = None
        if not user:
            messages = [{"role": "user", "content": system}]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        target_model = model or self.model
        body = dict(self.extra_body)
        if extra_body:
            body.update(extra_body)
        result, _usage = call_llm_with_retry(
            self.endpoint, self.api_key, target_model, messages,
            self.temperature, self.max_tokens, json_mode, self.timeout, self.max_retries,
            extra_body=body if body else None,
        )
        return result

    def chat_multi(
        self,
        messages: list[dict],
        json_mode: bool = False,
        model: str | None = None,
        extra_body: dict | None = None,
    ) -> str | dict:
        """Multi-turn chat. Supports router model override."""
        target_model = model or self.model
        body = dict(self.extra_body)
        if extra_body:
            body.update(extra_body)
        result, _usage = call_llm_with_retry(
            self.endpoint, self.api_key, target_model, messages,
            self.temperature, self.max_tokens, json_mode, self.timeout, self.max_retries,
            extra_body=body if body else None,
        )
        return result
