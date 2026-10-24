"""Canary probe runner supporting both live OpenAI API probes and offline simulation profiles.

References:
- MIT 6.033: Computer System Engineering (Fault tolerance, synthetic probe monitoring)
"""

import os
import time
import asyncio
from typing import Dict, Any, Tuple, Optional
from .models import FailureDomain, StreamingMetrics, IncidentRecord, RCAReport
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
    async def run_live_probe(model: str = "gpt-4o", prompt: str = "Hello, world!") -> RCAReport:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set. Use simulation mode instead.")

        if not HAS_OPENAI:
            raise ImportError("openai package not available.")

        client = AsyncOpenAI(api_key=api_key)
        tracker = TelemetryTracker(prompt_tokens=len(prompt) // 4)
        tracker.start_connection()
        tracker.record_handshake()

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True}
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    tracker.record_chunk(chunk.choices[0].delta.content)
            tracker.finish()
        except Exception as e:
            tracker.record_error(str(e))

        metrics = tracker.compute_metrics()
        meta = {"model": model, "mode": "LIVE_PROBE"}
        incident = RCAEngine.diagnose(metrics, meta)
        return RCAEngine.generate_report(incident)
