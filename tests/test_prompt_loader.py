from __future__ import annotations


def test_review_brief_prompt_loader_default(monkeypatch) -> None:
    from gateway.app.services import gemini_brief

    monkeypatch.delenv("REVIEW_BRIEF_PROMPT_VERSION", raising=False)
    prompt = gemini_brief._load_review_brief_prompt()
    assert prompt.strip()


def test_review_brief_prompt_loader_fallback(monkeypatch) -> None:
    from gateway.app.services import gemini_brief

    monkeypatch.setenv("REVIEW_BRIEF_PROMPT_VERSION", "missing_version")
    prompt = gemini_brief._load_review_brief_prompt()
    assert prompt.strip()
