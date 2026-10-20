from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lawagent.cli import main

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class CLITests(unittest.TestCase):
    def test_agent_json_output(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "--agent",
                    "--provider",
                    "mock",
                    "--data",
                    str(FIXTURE),
                    "--json",
                    "测试劳动法第2条是什么？",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "agent")
        self.assertEqual(payload["answer"]["status"], "ok")
        self.assertTrue(payload["answer"]["citations"])

    def test_baseline_json_output(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "--baseline",
                    "--data",
                    str(FIXTURE),
                    "--json",
                    "经济补偿",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "baseline")
        self.assertTrue(payload["answer"]["citations"])

    def test_empty_production_data_exits_with_2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "articles.jsonl"
            empty.write_text("", encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                code = main(
                    [
                        "--agent",
                        "--provider",
                        "mock",
                        "--data",
                        str(empty),
                        "测试问题",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("数据文件为空", error.getvalue())


if __name__ == "__main__":
    unittest.main()