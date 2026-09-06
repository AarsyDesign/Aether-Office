"""Unit tests for automatic LLM failover and fallback chains."""
import unittest
from unittest.mock import patch, MagicMock

from llm import (
    LLMClient,
    call_llm_with_retry,
    LLMError,
    LLMTimeoutError,
    LLMAuthError,
    LLMRateLimitError,
)


class TestLLMFailover(unittest.TestCase):
    """Test suite verifying multi-provider LLM failover behavior."""

    def test_fallback_resolution_from_models(self):
        """Verify that string preset names in fallbacks resolve to full model configs."""
        models = {
            "gemini": {
                "endpoint": "https://gemini.example.com",
                "api_key": "gemini-key",
                "model": "gemini-3.6-flash",
                "timeout": 45,
            },
            "groq": {
                "endpoint": "https://groq.example.com",
                "api_key": "groq-key",
                "model": "qwen-3.8",
                "timeout": 30,
            }
        }
        client = LLMClient(
            endpoint="https://primary.example.com",
            api_key="primary-key",
            model="primary-model",
            models=models,
            fallbacks=["gemini", "groq"],
        )

        resolved = client._resolve_fallbacks()
        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0]["name"], "gemini")
        self.assertEqual(resolved[0]["endpoint"], "https://gemini.example.com")
        self.assertEqual(resolved[0]["model"], "gemini-3.6-flash")
        self.assertEqual(resolved[0]["timeout"], 45)

        self.assertEqual(resolved[1]["name"], "groq")
        self.assertEqual(resolved[1]["endpoint"], "https://groq.example.com")
        self.assertEqual(resolved[1]["model"], "qwen-3.8")
        self.assertEqual(resolved[1]["timeout"], 30)

    def test_role_inherits_fallbacks(self):
        """Verify that role-specific sub-clients inherit fallbacks from parent router."""
        models = {
            "pm": {
                "endpoint": "https://nim.example.com",
                "api_key": "nim-key",
                "model": "kimi-k3",
            },
            "gemini": {
                "endpoint": "https://gemini.example.com",
                "api_key": "gemini-key",
                "model": "gemini-3.6-flash",
            }
        }
        client = LLMClient(
            endpoint="https://default.example.com",
            api_key="default-key",
            model="default-model",
            models=models,
            fallbacks=["gemini"],
        )

        pm_client = client.for_role("pm")
        self.assertEqual(pm_client.model, "kimi-k3")
        self.assertEqual(pm_client.fallbacks, ["gemini"])

    @patch("llm.call_llm")
    def test_seamless_failover_on_timeout(self, mock_call_llm):
        """Verify that when primary model times out, client seamlessly falls back to secondary model."""
        # Side effect: First call (primary) raises Timeout; second call (gemini fallback) succeeds
        def mock_effect(endpoint, api_key, model, messages, *args, **kwargs):
            if "primary.example.com" in endpoint:
                raise LLMTimeoutError("Primary request timed out after 45s")
            if "gemini.example.com" in endpoint:
                return "Response from Gemini Fallback", {"total_tokens": 42}
            raise LLMError("Unknown endpoint")

        mock_call_llm.side_effect = mock_effect

        models = {
            "gemini": {
                "endpoint": "https://gemini.example.com",
                "api_key": "gemini-key",
                "model": "gemini-3.6-flash",
                "timeout": 45,
            }
        }
        client = LLMClient(
            endpoint="https://primary.example.com",
            api_key="primary-key",
            model="primary-model",
            models=models,
            fallbacks=["gemini"],
            max_retries=1,
            timeout=45,
        )

        result = client.chat(system="You are a helpful assistant", user="Hello")
        self.assertEqual(result, "Response from Gemini Fallback")
        self.assertEqual(mock_call_llm.call_count, 2)

    @patch("llm.call_llm")
    def test_failover_on_auth_error_with_fallbacks(self, mock_call_llm):
        """Verify that when primary has auth error (e.g. quota depleted), it falls back to working provider."""
        def mock_effect(endpoint, api_key, model, messages, *args, **kwargs):
            if "exhausted.example.com" in endpoint:
                raise LLMAuthError("Invalid API key / Quota exhausted (401)")
            if "working.example.com" in endpoint:
                return "Response from Working Provider", {"total_tokens": 100}
            raise LLMError("Unknown endpoint")

        mock_call_llm.side_effect = mock_effect

        fallbacks = [{
            "name": "working_backup",
            "endpoint": "https://working.example.com",
            "api_key": "valid-key",
            "model": "backup-model",
            "timeout": 30,
        }]

        client = LLMClient(
            endpoint="https://exhausted.example.com",
            api_key="expired-key",
            model="expired-model",
            fallbacks=fallbacks,
            max_retries=1,
        )

        result = client.chat(system="Hello")
        self.assertEqual(result, "Response from Working Provider")

    @patch("llm.call_llm")
    def test_all_fallbacks_fail_raises_llm_error(self, mock_call_llm):
        """Verify that when primary and all fallbacks fail, LLMError is raised with total count."""
        mock_call_llm.side_effect = LLMTimeoutError("Connection timed out")

        fallbacks = [
            {"endpoint": "https://fb1.com", "api_key": "k1", "model": "m1"},
            {"endpoint": "https://fb2.com", "api_key": "k2", "model": "m2"},
        ]

        client = LLMClient(
            endpoint="https://primary.com",
            api_key="k0",
            model="m0",
            fallbacks=fallbacks,
            max_retries=1,
        )

        with self.assertRaises(LLMError) as ctx:
            client.chat(system="Hello")
        self.assertIn("All LLM targets (3) failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
