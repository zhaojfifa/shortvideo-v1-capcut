from __future__ import annotations

from gateway.app.providers import gemini_subtitles as gs


def _make_resp(text: str) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}],
                }
            }
        ]
    }


def test_translate_segments_retries_on_truncated(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_call(_prompt: str):
        calls["count"] += 1
        if calls["count"] == 1:
            return _make_resp('{"translations":[{"index":1,"mm":"ok"}]')
        return _make_resp('{"translations":[{"index":1,"mm":"ok"}]}')

    monkeypatch.setattr(gs, "_call_gemini", fake_call)

    translations = gs.translate_segments_with_gemini(
        segments=[{"index": 1, "origin": "hi"}],
        target_lang="my",
        chunk_size=1,
        retries=1,
    )

    assert translations[1] == "ok"
