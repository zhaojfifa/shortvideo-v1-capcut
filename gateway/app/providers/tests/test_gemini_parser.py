import unittest

from gateway.app.providers.gemini_subtitles import parse_gemini_subtitle_payload


class ParseGeminiSubtitlePayloadTests(unittest.TestCase):
    def _assert_payload(self, payload):
        self.assertIn("language", payload)
        segments = payload.get("segments")
        self.assertIsInstance(segments, list)
        self.assertGreater(len(segments), 0)
        for seg in segments:
            for key in ["scene_id", "index", "start", "end", "origin"]:
                self.assertIn(key, seg)

    def test_clean_json(self):
        payload = parse_gemini_subtitle_payload(
            '{"language":"zh","segments":[{"index":1,"start":0,"end":1,"origin":"hi","mm":"hello","scene_id":1}],"scenes":[{"scene_id":1,"start":0,"end":1,"title":"t","mm_title":"mt"}]}'
        )
        self._assert_payload(payload)

    def test_fenced_json(self):
        payload = parse_gemini_subtitle_payload(
            """```json
{"language": "zh-CN", "segments": [{"index": 1, "start": 0, "end": 1.5, "origin": "你好", "mm": "မင်္ဂလာပါ", "scene_id": 2}], "scenes": [{"scene_id": 2, "start": 0, "end": 1.5, "title": "t", "mm_title": "mt"}]}
```"""
        )
        self._assert_payload(payload)

    def test_python_style_dict(self):
        payload = parse_gemini_subtitle_payload(
            "{ 'language': 'zh', 'segments': [ { 'index': 1, 'start': 0.0, 'end': 1.0, 'origin': 'foo', 'mm': 'bar', 'scene_id': 3 } ], 'scenes': [ { 'scene_id': 3, 'start': 0.0, 'end': 1.0, 'title': 't', 'mm_title': 'mt' } ] }"
        )
        self._assert_payload(payload)


if __name__ == "__main__":
    unittest.main()
