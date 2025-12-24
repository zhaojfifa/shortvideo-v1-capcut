import unittest

from gateway.app.providers.gemini_subtitles import parse_gemini_subtitle_payload


class TestGeminiPayloadParsing(unittest.TestCase):
    def test_parse_valid_json(self):
        raw = (
            '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,'
            '"origin":"你好","mm":"မင်္ဂလာပါ","scene_id":1}],"scenes":[]}'
        )
        obj = parse_gemini_subtitle_payload(raw)
        self.assertEqual(obj["language"], "zh")
        self.assertTrue(isinstance(obj["segments"], list))

    def test_parse_json_with_raw_newline_in_string(self):
        raw = (
            '{ "language":"zh", "segments":[{"index":1,"start":0.0,"end":1.0,'
            '"origin":"hello","mm":"line1\nline2","scene_id":1}], "scenes":[] }'
        )
        obj = parse_gemini_subtitle_payload(raw)
        self.assertEqual(obj["segments"][0]["scene_id"], 1)

    def test_parse_wrapped_in_code_fence(self):
        raw = '```json\n{ "language":"zh", "segments":[], "scenes":[] }\n```'
        obj = parse_gemini_subtitle_payload(raw)
        self.assertEqual(obj["language"], "zh")


if __name__ == "__main__":
    unittest.main()
