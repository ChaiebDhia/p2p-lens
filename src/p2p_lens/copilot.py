"""Grounded Q&A over findings: retrieve, answer, verify, and fall back deterministically.

An LLM backend is optional. Whatever it returns must pass a grounding check (every claim
cites a retrieved finding, every number appears in a cited finding) or the answer is
replaced by an extractive one built directly from the findings.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from p2p_lens.findings import Finding

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "which",
        "who",
        "why",
        "with",
        "many",
        "much",
        "our",
        "we",
        "us",
    ]
)
CITATION = re.compile(r"\[(F\d{2})\]")
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
NOT_FOUND = "No finding in the analysis covers that question."


class BackendError(RuntimeError):
    """Raised when an LLM backend cannot produce an answer."""


class Backend(Protocol):
    """Anything that turns a prompt into text."""

    name: str

    def complete(self, prompt: str) -> str: ...


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def _doc_tokens(f: Finding) -> list[str]:
    return tokenize(f"{f.title} {f.text} {' '.join(f.tags)}") + tokenize(" ".join(f.tags)) * 2


def retrieve(question: str, findings: list[Finding], k: int = 3) -> list[Finding]:
    """Rank findings by TF-IDF cosine similarity to the question; keep the top ``k`` matches."""
    q = Counter(tokenize(question))
    if not q or not findings:
        return []
    docs = [Counter(_doc_tokens(f)) for f in findings]
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vec(counts: Counter[str]) -> dict[str, float]:
        return {t: c * idf.get(t, 1.0) for t, c in counts.items()}

    qv = vec(q)
    qn = math.sqrt(sum(v * v for v in qv.values()))
    scored: list[tuple[float, int]] = []
    for i, d in enumerate(docs):
        dv = vec(d)
        dn = math.sqrt(sum(v * v for v in dv.values()))
        dot = sum(qv[t] * dv[t] for t in qv if t in dv)
        if dot > 0 and qn and dn:
            scored.append((dot / (qn * dn), i))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [findings[i] for _, i in scored[:k]]


def build_prompt(question: str, context: list[Finding]) -> str:
    blocks = "\n".join(f"[{f.id}] {f.title}: {f.text}" for f in context)
    return (
        "You answer questions about a procure-to-pay process analysis.\n"
        "Use ONLY the findings below. Cite every claim with its finding id in square brackets, "
        "for example [F03]. Copy numbers exactly as written. If the findings do not answer the "
        "question, say so.\n\n"
        f"Findings:\n{blocks}\n\nQuestion: {question}\nAnswer:"
    )


@dataclass
class GroundingReport:
    """Result of verifying an answer against the findings it may cite."""

    ok: bool
    unknown_citations: list[str] = field(default_factory=list)
    ungrounded_numbers: list[str] = field(default_factory=list)
    has_citations: bool = True


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in NUMBER.findall(text)]


def check_grounding(answer: str, findings: list[Finding], question: str = "") -> GroundingReport:
    """Check that citations exist and that every number is backed by a cited finding."""
    by_id = {f.id: f for f in findings}
    cited = CITATION.findall(answer)
    unknown = sorted({c for c in cited if c not in by_id})
    body = LIST_MARKER.sub("", CITATION.sub("", answer))
    allowed = set(_numbers(question))
    for c in cited:
        if c in by_id:
            allowed.update(_numbers(by_id[c].text))
    bad = [m for m in NUMBER.findall(body) if float(m.replace(",", "")) not in allowed]
    return GroundingReport(
        ok=bool(cited) and not unknown and not bad,
        unknown_citations=unknown,
        ungrounded_numbers=bad,
        has_citations=bool(cited),
    )


@dataclass
class Answer:
    """A final answer plus how it was produced."""

    question: str
    text: str
    citations: list[str]
    grounded: bool
    backend: str
    fell_back: bool = False
    reason: str | None = None


def extractive_answer(context: list[Finding]) -> str:
    return "\n".join(f"{f.text} [{f.id}]" for f in context)


def ask(
    question: str, findings: list[Finding], backend: Backend | None = None, k: int = 3
) -> Answer:
    """Answer ``question`` from ``findings``. Always returns a grounded answer."""
    context = retrieve(question, findings, k=k)
    if not context:
        return Answer(question, NOT_FOUND, [], True, "none")
    extractive = extractive_answer(context)
    ids = [f.id for f in context]
    if backend is None:
        return Answer(question, extractive, ids, True, "extractive")
    try:
        text = backend.complete(build_prompt(question, context)).strip()
    except BackendError as exc:
        return Answer(question, extractive, ids, True, "extractive", True, f"backend error: {exc}")
    report = check_grounding(text, context, question)
    if not report.ok:
        detail = (
            f"unknown citations {report.unknown_citations}, "
            f"ungrounded numbers {report.ungrounded_numbers}, citations present: "
            f"{report.has_citations}"
        )
        return Answer(
            question, extractive, ids, True, "extractive", True, f"grounding failed: {detail}"
        )
    return Answer(question, text, sorted(set(CITATION.findall(text))), True, backend.name)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    if urlparse(url).scheme not in ("http", "https"):
        raise BackendError(f"unsupported URL scheme: {url}")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise BackendError(str(exc)) from exc


@dataclass
class OllamaBackend:
    """Local, free LLM via Ollama (https://ollama.com). No API key, no data leaves the machine."""

    model: str = "llama3.2"
    host: str = "http://localhost:11434"
    timeout: float = 120.0
    name: str = "ollama"

    def complete(self, prompt: str) -> str:
        data = _post_json(
            f"{self.host.rstrip('/')}/api/generate",
            {"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
            {},
            self.timeout,
        )
        try:
            return str(data["response"])
        except (KeyError, TypeError) as exc:
            raise BackendError("unexpected Ollama response shape") from exc


@dataclass
class OpenAICompatBackend:
    """Any OpenAI-compatible chat endpoint (many providers have free tiers)."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    name: str = "openai-compatible"

    @classmethod
    def from_env(cls) -> OpenAICompatBackend:
        """Read P2P_LENS_BASE_URL, P2P_LENS_API_KEY and P2P_LENS_MODEL."""
        try:
            return cls(
                base_url=os.environ["P2P_LENS_BASE_URL"],
                api_key=os.environ["P2P_LENS_API_KEY"],
                model=os.environ["P2P_LENS_MODEL"],
            )
        except KeyError as exc:
            raise BackendError(f"environment variable {exc.args[0]} is not set") from exc

    def complete(self, prompt: str) -> str:
        data = _post_json(
            f"{self.base_url.rstrip('/')}/chat/completions",
            {
                "model": self.model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            {"Authorization": f"Bearer {self.api_key}"},
            self.timeout,
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("unexpected chat-completions response shape") from exc
