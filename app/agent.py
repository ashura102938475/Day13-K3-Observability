from __future__ import annotations

import time
from dataclasses import dataclass

from opentelemetry.trace import Status, StatusCode

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .prompt_management import resolve_prompt
from .tracing import set_span_attributes, start_span


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    prompt_name: str
    prompt_label: str
    prompt_version: str
    rag_result_count: int


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    def run(self, user_id: str, feature: str, session_id: str, message: str) -> AgentResult:
        del user_id, session_id  # Raw identifiers must never be attached to spans.
        started = time.perf_counter()

        with start_span(
            "agent.run",
            {"feature": feature, "llm.model": self.model, "status": "running"},
        ) as agent_span:
            with start_span("rag.retrieve", {"status": "running"}) as rag_span:
                docs = retrieve(message)
                set_span_attributes(
                    rag_span,
                    {"rag.result_count": len(docs), "status": "ok"},
                )
                rag_span.set_status(Status(StatusCode.OK))

            with start_span("prompt.resolve", {"status": "running"}) as prompt_span:
                prompt = resolve_prompt(
                    feature=feature,
                    docs=docs,
                    message=message,
                )
                prompt_attributes = {
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                }
                set_span_attributes(
                    prompt_span, {**prompt_attributes, "status": "ok"}
                )
                prompt_span.set_status(Status(StatusCode.OK))
                set_span_attributes(agent_span, prompt_attributes)

            with start_span(
                "llm.generate",
                {
                    **prompt_attributes,
                    "llm.model": self.model,
                    "status": "running",
                },
            ) as llm_span:
                response = self.llm.generate(prompt.text)
                cost_usd = self._estimate_cost(
                    response.usage.input_tokens, response.usage.output_tokens
                )
                set_span_attributes(
                    llm_span,
                    {
                        "llm.tokens.input": response.usage.input_tokens,
                        "llm.tokens.output": response.usage.output_tokens,
                        "llm.cost_usd": cost_usd,
                        "status": "ok",
                    },
                )
                llm_span.set_status(Status(StatusCode.OK))

            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            set_span_attributes(
                agent_span,
                {
                    "rag.result_count": len(docs),
                    "llm.tokens.input": response.usage.input_tokens,
                    "llm.tokens.output": response.usage.output_tokens,
                    "llm.cost_usd": cost_usd,
                    "quality.score": quality_score,
                    "latency_ms": latency_ms,
                    "status": "ok",
                },
            )
            agent_span.set_status(Status(StatusCode.OK))

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
            model=self.model,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            prompt_name=prompt.name,
            prompt_label=prompt.label,
            prompt_version=prompt.version,
            rag_result_count=len(docs),
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(
            token in answer.lower() for token in question.lower().split()[:3]
        ):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
