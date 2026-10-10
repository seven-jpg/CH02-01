"""Provider adapter controls; all responses are synthetic and network-free."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from unittest.mock import Mock

from models.text_agent import GenerationError, TextAgent, retry_generate


class GenerationAdapterTests(unittest.TestCase):
    def test_nvidia_payload_uses_text_messages_and_shared_generation_parameters(self):
        agent = TextAgent({"provider": "nvidia", "model": "synthetic-model", "temperature": 0,
                           "top_p": 1, "max_tokens": 100, "seed": 42})
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]
        self.assertEqual({"model": "synthetic-model", "messages": messages, "temperature": 0,
                          "top_p": 1, "max_tokens": 100, "seed": 42}, agent.public_request(messages))

    def test_successful_idk_is_normal_response_and_usage_is_read(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {
            "choices": [{"message": {"content": "I don't know."}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
        agent = TextAgent({"provider": "nvidia", "model": "synthetic-model"}, session=session)
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "synthetic-test-key"}):
            result = agent.generate([{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}])
        self.assertEqual("I don't know.", result.response)
        self.assertEqual((12, 4), (result.input_tokens, result.output_tokens))

    def test_empty_provider_response_is_technical_failure(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {"choices": [{"message": {"content": "  "}}]}
        agent = TextAgent({"provider": "nvidia", "model": "synthetic-model"}, session=session)
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "synthetic-test-key"}):
            with self.assertRaises(GenerationError) as raised:
                agent.generate([{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}])
        self.assertEqual("empty_response", raised.exception.code)

    def test_nonretryable_credential_error_does_not_sleep_or_retry(self):
        agent = Mock()
        agent.generate.side_effect = GenerationError("missing_credentials", retryable=False)
        result, code, retries = retry_generate(agent, [], max_retries=2, backoff_s=0)
        self.assertIsNone(result)
        self.assertEqual("missing_credentials", code)
        self.assertEqual(0, retries)
        agent.generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
