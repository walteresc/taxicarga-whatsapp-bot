"""Latency tracking for bot generation pipeline."""
import time
from contextlib import contextmanager
from typing import Dict, Any, Optional


class GenerationTelemetry:
    """Track latency of each pipeline step in bot generation."""

    def __init__(self, generation_id: str):
        self.generation_id = generation_id
        self.steps: Dict[str, Dict[str, Any]] = {}
        self.global_start = time.time()

    @contextmanager
    def measure(self, step_name: str):
        """Context manager to measure a pipeline step."""
        start = time.time()
        try:
            yield
        finally:
            elapsed_ms = (time.time() - start) * 1000
            self.steps[step_name] = {
                "duration_ms": round(elapsed_ms, 1),
                "timestamp": time.time()
            }

    def mark_openai_call(self, purpose: str, duration_ms: float, model: str, input_tokens: int, output_tokens: int, retries: int = 0):
        """Record an OpenAI API call."""
        key = f"openai_{purpose}"
        if key not in self.steps:
            self.steps[key] = {"calls": []}

        self.steps[key]["calls"].append({
            "duration_ms": round(duration_ms, 1),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "retries": retries
        })

    def mark_from_ai_result(self, purpose: str, ai_result: "AIResult"):
        """Record an OpenAI call from AIResult object."""
        self.mark_openai_call(
            purpose=purpose,
            duration_ms=ai_result.latency_ms,
            model=ai_result.model,
            input_tokens=ai_result.input_tokens or 0,
            output_tokens=ai_result.output_tokens or 0,
            retries=ai_result.retry_count
        )

    def get_total_ms(self) -> float:
        """Get total elapsed time in milliseconds."""
        return round((time.time() - self.global_start) * 1000, 1)

    def get_summary(self) -> Dict[str, Any]:
        """Get sanitized summary for storage (no PII, no full prompts)."""
        summary = {
            "generation_id": self.generation_id,
            "total_ms": self.get_total_ms(),
            "steps": {}
        }

        for step_name, data in self.steps.items():
            if "calls" in data:
                # OpenAI calls aggregated
                summary["steps"][step_name] = {
                    "count": len(data["calls"]),
                    "calls": data["calls"]
                }
            else:
                # Regular step timing
                summary["steps"][step_name] = data

        return summary

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata dict for storage in BotGeneration."""
        summary = self.get_summary()
        # Include high-level metrics + openai call details
        steps = {}
        for k, v in summary["steps"].items():
            if "calls" in v:
                # OpenAI call aggregation
                steps[k] = {
                    "count": v["count"],
                    "calls": v["calls"]
                }
            else:
                # Regular step timing
                steps[k] = v.get("duration_ms", v)

        return {
            "total_ms": summary["total_ms"],
            "steps": steps
        }
