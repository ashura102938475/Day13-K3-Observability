from __future__ import annotations

import pytest

from app.prompt_management import resolve_prompt


def test_default_prompt_resolves_to_production_v1(monkeypatch) -> None:
    monkeypatch.delenv("PROMPT_NAME", raising=False)
    monkeypatch.delenv("PROMPT_LABEL", raising=False)
    monkeypatch.delenv("PROMPT_VERSION", raising=False)

    resolved = resolve_prompt(
        feature="qa",
        docs=["Refund within 7 days", "Proof of purchase is required"],
        message="What is the refund policy?",
    )

    assert resolved.source == "local"
    assert resolved.name == "day13-chat"
    assert resolved.label == "production"
    assert resolved.version == "v1"
    assert resolved.text == (
        "Feature=qa\n"
        "Docs=Refund within 7 days\nProof of purchase is required\n"
        "Question=What is the refund policy?"
    )


def test_candidate_label_resolves_v2(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("PROMPT_LABEL", "canary")
    monkeypatch.setenv("PROMPT_VERSION", "v2")

    resolved = resolve_prompt(
        feature="monitoring",
        docs=["Trace first", "Confirm with logs"],
        message="Where is the bottleneck?",
    )

    assert (resolved.name, resolved.label, resolved.version) == (
        "day13-chat",
        "canary",
        "v2",
    )
    assert "Answer only from the supplied documents" in resolved.text


def test_rollback_returns_to_production_v1(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_LABEL", "canary")
    monkeypatch.setenv("PROMPT_VERSION", "v2")
    candidate = resolve_prompt(feature="qa", docs=["Trace first"], message="Why?")

    monkeypatch.setenv("PROMPT_LABEL", "production")
    monkeypatch.setenv("PROMPT_VERSION", "v1")
    rollback = resolve_prompt(feature="qa", docs=["Trace first"], message="Why?")

    assert (candidate.label, candidate.version) == ("canary", "v2")
    assert (rollback.label, rollback.version) == ("production", "v1")
    assert candidate.text != rollback.text


def test_unknown_prompt_version_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_VERSION", "v999")

    with pytest.raises(ValueError, match="Unsupported prompt version: v999"):
        resolve_prompt(feature="qa", docs=["Trace first"], message="Why?")
