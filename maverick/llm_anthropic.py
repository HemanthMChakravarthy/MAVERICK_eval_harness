"""Anthropic Claude implementation of LLMClient with full provenance logging.

The API key is read from the ANTHROPIC_API_KEY environment variable only; it is
never written to logs. Every request/response pair is appended to a JSONL log so
that runs are auditable and can be released as supplementary material.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .agents import LLMClient

DEFAULT_MODEL = os.environ.get("MAVERICK_MODEL_ID", "claude-opus-5-5")


class AnthropicClient(LLMClient):
    def __init__(self, model_id: str = DEFAULT_MODEL, max_tokens: int = 8000,
                 log_path: str | Path = "results/llm_calls.jsonl", system: str = ""):
        import anthropic  # imported lazily so the structural harness has no hard dependency

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("Set ANTHROPIC_API_KEY in your environment before running LLM configurations.")
        self.client = anthropic.Anthropic()
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.system = system
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def complete(self, prompt: str, seed: int = 0, temperature: float = 0.0) -> str:
        # The Messages API has no seed parameter; the seed is recorded for run pairing only.
        started = time.time()
        response = self.client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            temperature=temperature,
            system=self.system or None,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        record = {
            "timestamp": started,
            "latency_s": round(time.time() - started, 3),
            "requested_model": self.model_id,
            "served_model": getattr(response, "model", None),
            "seed": seed,
            "temperature": temperature,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
            "stop_reason": getattr(response, "stop_reason", None),
            "prompt": prompt,
            "response": text,
        }
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        return text
