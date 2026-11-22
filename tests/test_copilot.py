from __future__ import annotations

import io
import json

import pytest

from p2p_lens import copilot
from p2p_lens.copilot import (
    BackendError,
    OllamaBackend,
    OpenAICompatBackend,
    ask,
    check_grounding,
    retrieve,
)
from p2p_lens.findings import build_findings


class FakeBackend:
    name = "fake"

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture(scope="module")
def findings(analysis):
    return build_findings(analysis)


def test_retrieval_finds_the_right_finding(findings) -> None:
    assert retrieve("how many invoices are paid late", findings)[0].id == "F08"
    assert retrieve("which vendors deliver slowly", findings)[0].id == "F10"
    assert retrieve("how much rework is there", findings)[0].id == "F03"
    assert retrieve("duplicate invoices", findings)[0].id == "F07"


def test_retrieval_returns_nothing_for_unrelated_questions(findings) -> None:
    assert retrieve("what is the weather in Madrid", findings) == []
    assert retrieve("the of and", findings) == []
    assert retrieve("rework", []) == []


def test_extractive_answer_is_grounded(findings) -> None:
    answer = ask("how much rework is there", findings)
    assert answer.backend == "extractive"
    assert "F03" in answer.citations
    assert check_grounding(answer.text, findings).ok


def test_unanswerable_question(findings) -> None:
    answer = ask("what is the weather in Madrid", findings)
    assert answer.text == copilot.NOT_FOUND
    assert answer.citations == []


def test_good_llm_answer_is_accepted(findings) -> None:
    f = next(x for x in findings if x.id == "F03")
    reply = f"{f.metrics['rework_pct']}% of orders were reworked [F03]."
    backend = FakeBackend(reply)
    answer = ask("how much rework is there", findings, backend)
    assert not answer.fell_back
    assert answer.backend == "fake"
    assert answer.text == reply
    assert "[F03]" in backend.prompts[0]


def test_hallucinated_number_triggers_fallback(findings) -> None:
    answer = ask(
        "how much rework is there", findings, FakeBackend("About 99.9% were reworked [F03].")
    )
    assert answer.fell_back
    assert answer.backend == "extractive"
    assert "99.9" in (answer.reason or "")


def test_missing_or_unknown_citation_triggers_fallback(findings) -> None:
    no_cite = ask("how much rework is there", findings, FakeBackend("Quite a lot."))
    assert no_cite.fell_back and "citations present: False" in (no_cite.reason or "")
    fake_cite = ask("how much rework is there", findings, FakeBackend("Many [F99]."))
    assert fake_cite.fell_back and "F99" in (fake_cite.reason or "")


def test_backend_error_triggers_fallback(findings) -> None:
    answer = ask("how much rework is there", findings, FakeBackend(BackendError("boom")))
    assert answer.fell_back and "boom" in (answer.reason or "")


def test_grounding_allows_numbers_from_question_and_ignores_list_markers(findings) -> None:
    f = next(x for x in findings if x.id == "F03")
    text = f"1. You asked about 7 things. {f.metrics['rework_cases']:.0f} orders [F03]"
    assert check_grounding(text, findings, "Tell me 7 things").ok
    assert not check_grounding(text, findings, "").ok


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _patch(monkeypatch: pytest.MonkeyPatch, payload: object | Exception) -> list[object]:
    seen: list[object] = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        seen.append(request)
        if isinstance(payload, Exception):
            raise payload
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr(copilot.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_ollama_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch(monkeypatch, {"response": "hello [F01]"})
    assert OllamaBackend().complete("hi") == "hello [F01]"
    assert seen[0].full_url.endswith("/api/generate")  # type: ignore[attr-defined]


def test_openai_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch(monkeypatch, {"choices": [{"message": {"content": "ok"}}]})
    backend = OpenAICompatBackend("https://example.test/v1/", "key", "m")
    assert backend.complete("hi") == "ok"
    assert seen[0].headers["Authorization"] == "Bearer key"  # type: ignore[attr-defined]


def test_backend_failures_are_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, copilot.urllib.error.URLError("down"))
    with pytest.raises(BackendError):
        OllamaBackend().complete("hi")
    _patch(monkeypatch, {"unexpected": 1})
    with pytest.raises(BackendError, match="shape"):
        OllamaBackend().complete("hi")
    with pytest.raises(BackendError, match="shape"):
        OpenAICompatBackend("https://x.test", "k", "m").complete("hi")
    with pytest.raises(BackendError, match="scheme"):
        OllamaBackend(host="file:///etc/passwd").complete("hi")


def test_openai_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("P2P_LENS_BASE_URL", "P2P_LENS_API_KEY", "P2P_LENS_MODEL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(BackendError, match="P2P_LENS_BASE_URL"):
        OpenAICompatBackend.from_env()
    monkeypatch.setenv("P2P_LENS_BASE_URL", "https://x.test/v1")
    monkeypatch.setenv("P2P_LENS_API_KEY", "k")
    monkeypatch.setenv("P2P_LENS_MODEL", "m")
    assert OpenAICompatBackend.from_env().model == "m"
