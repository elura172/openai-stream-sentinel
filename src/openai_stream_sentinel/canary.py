"""Run bounded SDK requests and synthetic streaming scenarios."""

import os
import asyncio
import math
from .models import FailureDomain, RCAReport
from .telemetry import TelemetryTracker
from .simulator import simulate_stream
from .rca_engine import RCAEngine

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class CanaryRunner:
    @staticmethod
    async def run_simulation(scenario: FailureDomain) -> RCAReport:
        tracker, meta = await simulate_stream(scenario)
        metrics = tracker.compute_metrics()
        incident = RCAEngine.diagnose(metrics, meta)
        report = RCAEngine.generate_report(incident)
        return report

    @staticmethod
    async def run_live_probe(model: str = "gpt-4o", prompt: str = "Hello, world!", *, timeout: float = 30.0) -> RCAReport:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number of seconds")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set. Use simulation mode instead.")

        if not HAS_OPENAI:
            raise ImportError("openai package not available.")

        tracker = TelemetryTracker(prompt_tokens=len(prompt) // 4)
        async with AsyncOpenAI(api_key=api_key, max_retries=0, timeout=timeout) as client:
            tracker.start_connection()
            try:
                async with asyncio.timeout(timeout):
                    stream = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        stream=True,
                        stream_options={"include_usage": True}
                    )
                    async with stream:
                        tracker.request_id = stream.response.headers.get("x-request-id")
                        async for chunk in stream:
                            if chunk.usage is not None:
                                tracker.record_usage(
                                    completion_tokens=chunk.usage.completion_tokens,
                                    prompt_tokens=chunk.usage.prompt_tokens,
                                )
                            for choice in chunk.choices:
                                if choice.index != 0:
                                    continue
                                if choice.delta and choice.delta.content:
                                    tracker.record_chunk(choice.delta.content)
                                if choice.finish_reason is not None:
                                    tracker.finish_reason = choice.finish_reason
                if tracker.finish_reason is None:
                    tracker.record_error("Stream ended before a model finish_reason was received")
                else:
                    tracker.finish()
            except TimeoutError:
                tracker.record_error(f"Probe deadline exceeded ({timeout:g}s)")
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                tracker.request_id = getattr(e, "request_id", None) or tracker.request_id
                tracker.record_error(f"{type(e).__name__}: {e}", status_code=status_code)

        metrics = tracker.compute_metrics()
        meta = {"model": model, "mode": "LIVE_PROBE"}
        incident = RCAEngine.diagnose(metrics, meta)
        return RCAEngine.generate_report(incident)
