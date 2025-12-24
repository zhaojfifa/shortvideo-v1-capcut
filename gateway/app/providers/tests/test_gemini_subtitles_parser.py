import pytest

from gateway.app.providers import gemini_subtitles as gs


def test_parse_strict_json_ok():
    raw = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":[]}'
    data = gs.parse_gemini_subtitle_payload(raw)
    assert data["language"] == "zh"
    assert isinstance(data["segments"], list)


def test_parse_fenced_json_ok():
    raw = """```json
{"language":"zh","segments":[],"scenes":[]}
```"""
    data = gs.parse_gemini_subtitle_payload(raw)
    assert data["language"] == "zh"


def test_parse_json_with_raw_newline_in_string_sanitized():
    raw = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"line1\nline2","mm":"b","scene_id":1}],"scenes":[]}'
    data = gs.parse_gemini_subtitle_payload(raw)
    assert data["segments"][0]["origin"].startswith("line1")


def test_parse_python_literal_eval_fallback():
    raw = "{'language':'zh','segments':[],'scenes':[]}"
    data = gs.parse_gemini_subtitle_payload(raw)
    assert data["language"] == "zh"


def test_parse_repair_fallback(monkeypatch):
    broken = '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":['

    def _fake_repair(_: str) -> str:
        return '{"language":"zh","segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}],"scenes":[]}'

    monkeypatch.setattr(gs, "_repair_json_with_gemini", _fake_repair)
    data = gs.parse_gemini_subtitle_payload(broken)
    assert data["language"] == "zh"
