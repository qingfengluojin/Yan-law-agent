from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from lawagent.llm import OpenAICompatibleProvider, ProviderError


class ProviderTests(unittest.TestCase):
    def test_missing_api_key_has_actionable_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError) as context:
                OpenAICompatibleProvider()
        self.assertIn("OPENAI_API_KEY", str(context.exception))


if __name__ == "__main__":
    unittest.main()
