from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import metrics, tracing
from .mock_llm import FakeLLM, FakeResponse
from .mock_rag import retrieve
from .pii import hash_user_id, scrub_text, summarize_text
from .prompt_management import ResolvedPrompt, resolve_prompt
from .tracing import get_langfuse_client, observe, propagate_attributes, tracing_enabled

INPUT_PRICE_PER_MTOK = 3
OUTPUT_PRICE_PER_MTOK = 15


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        with propagate_attributes(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            trace_name="day13-agent-request",
            environment=os.getenv("APP_ENV", "dev"),
            metadata={
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        ):
            started = time.perf_counter()
            docs = self._retrieve(message)
            prompt = self._resolve_prompt(langfuse_client, feature=feature, docs=docs, message=message)
            langfuse_client.update_current_span(
                metadata={
                    "doc_count": len(docs),
                    "query_preview": summarize_text(message),
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error or "",
                },
                version=prompt.version,
            )
            with propagate_attributes(prompt=prompt.managed_prompt):
                response = self._generate(prompt)
            quality_score = self._heuristic_quality(message, response.text, docs)
            # Gửi quality proxy lên Langfuse dưới dạng score của trace để dashboard Langfuse vẽ được panel quality
            tracing.get_langfuse_client().score_current_trace(
                name="quality_score",
                value=quality_score,
                data_type="NUMERIC",
                comment="heuristic quality proxy 0-1",
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    # Child observations: @observe lồng chúng dưới root `lab-agent-run` theo context OTel.
    # Cập nhật observation hiện tại qua SDK client (tracing.get_langfuse_client), và chỉ ghi
    # bản preview đã scrub PII — không capture raw input/output.
    @observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
    def _retrieve(self, message: str) -> list[str]:
        started = time.perf_counter()
        docs = retrieve(message)
        tracing.get_langfuse_client().update_current_span(
            input={"query_preview": summarize_text(message)},
            output={"doc_count": len(docs), "doc_previews": [summarize_text(doc, 60) for doc in docs]},
            metadata={"doc_count": len(docs), "retrieval_ms": int((time.perf_counter() - started) * 1000)},
        )
        return docs

    # Fetch prompt từ Langfuse nằm trên đường request (timeout 2s, cache 60s) — tách span riêng
    # để waterfall thấy được thời gian này thay vì một khoảng trống trong root.
    @observe(name="prompt-fetch", as_type="span", capture_input=False, capture_output=False)
    def _resolve_prompt(self, langfuse_client, *, feature: str, docs: list[str], message: str) -> ResolvedPrompt:
        prompt = resolve_prompt(
            langfuse_client,
            feature=feature,
            docs=docs,
            message=message,
            enabled=tracing_enabled(),
        )
        tracing.get_langfuse_client().update_current_span(
            metadata={
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
                "prompt_source": prompt.source,
                "prompt_fetch_error": prompt.fetch_error or "",
            },
            level="WARNING" if prompt.source == "local-fallback" else "DEFAULT",
        )
        return prompt

    @observe(name="llm-generation", as_type="generation", capture_input=False, capture_output=False)
    def _generate(self, prompt: ResolvedPrompt) -> FakeResponse:
        started_at = datetime.now(timezone.utc)
        response = self.llm.generate(prompt.text)
        input_cost, output_cost = self._cost_breakdown(
            response.usage.input_tokens, response.usage.output_tokens
        )
        tracing.get_langfuse_client().update_current_generation(
            model=response.model,
            input=scrub_text(prompt.text),
            output=summarize_text(response.text, max_len=200),
            usage_details={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
            cost_details={"input": input_cost, "output": output_cost},
            completion_start_time=started_at + timedelta(milliseconds=response.ttft_ms),
            prompt=prompt.managed_prompt,
            metadata={
                "ttft_ms": response.ttft_ms,
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
            },
        )
        return response

    def _cost_breakdown(self, tokens_in: int, tokens_out: int) -> tuple[float, float]:
        input_cost = (tokens_in / 1_000_000) * INPUT_PRICE_PER_MTOK
        output_cost = (tokens_out / 1_000_000) * OUTPUT_PRICE_PER_MTOK
        return input_cost, output_cost

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost, output_cost = self._cost_breakdown(tokens_in, tokens_out)
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
