from __future__ import annotations

import random
import time
from dataclasses import dataclass
import os

from .incidents import STATE


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    text: str
    usage: FakeUsage
    model: str


class FakeLLM:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.max_output_tokens = self._read_output_token_cap()

    @staticmethod
    def _read_output_token_cap() -> int | None:
        """Read an optional output-token budget from the environment.

        The default remains uncapped so existing lab behaviour is unchanged.
        A cap is applied after an incident multiplier, making the cost-spike
        exercise measurable without changing the rest of the request flow.
        """
        raw_value = os.getenv("LLM_MAX_OUTPUT_TOKENS", "").strip()
        if not raw_value:
            return None
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError("LLM_MAX_OUTPUT_TOKENS must be a positive integer") from exc
        if value <= 0:
            raise ValueError("LLM_MAX_OUTPUT_TOKENS must be a positive integer")
        return value

    def generate(self, prompt: str) -> FakeResponse:
        time.sleep(0.15)
        input_tokens = max(20, len(prompt) // 4)
        output_tokens = random.randint(80, 180)
        if STATE["cost_spike"]:
            output_tokens *= 4
        if self.max_output_tokens is not None:
            output_tokens = min(output_tokens, self.max_output_tokens)
        answer = (
            "Starter answer. Teams should improve this output logic and add better quality checks. "
            "Use retrieved context and keep responses concise."
        )
        return FakeResponse(text=answer, usage=FakeUsage(input_tokens, output_tokens), model=self.model)
