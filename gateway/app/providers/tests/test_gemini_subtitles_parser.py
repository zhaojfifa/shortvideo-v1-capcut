import unittest

from gateway.app.providers import gemini_subtitles as gs


class TestGeminiSubtitlesParser(unittest.TestCase):
    def test_parse_strict_json_ok(self):
        raw = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":[]}'
        data = gs.parse_gemini_subtitle_payload(raw)
        self.assertEqual(data["language"], "zh")
        self.assertIsInstance(data["segments"], list)

    def test_parse_fenced_json_ok(self):
        raw = """```json
{"language":"zh","segments":[],"scenes":[]}
```"""
        data = gs.parse_gemini_subtitle_payload(raw)
        self.assertEqual(data["language"], "zh")

    def test_parse_json_with_raw_newline_in_string_sanitized(self):
        raw = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"line1\nline2","mm":"b","scene_id":1}],"scenes":[]}'
        data = gs.parse_gemini_subtitle_payload(raw)
        self.assertTrue(data["segments"][0]["origin"].startswith("line1"))

    def test_parse_python_literal_eval_fallback(self):
        raw = "{'language':'zh','segments':[],'scenes':[]}"
        data = gs.parse_gemini_subtitle_payload(raw)
        self.assertEqual(data["language"], "zh")

    def test_parse_repair_fallback(self):
        broken = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":['

        def _fake_repair(_: str) -> str:
            return '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":[]}'

        original = gs._repair_json_with_gemini
        gs._repair_json_with_gemini = _fake_repair  # type: ignore[assignment]
        try:
            data = gs.parse_gemini_subtitle_payload(broken)
            self.assertEqual(data["language"], "zh")
        finally:
            gs._repair_json_with_gemini = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
