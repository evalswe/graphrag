"""Runtime fixes for LiteLLM async shutdown/logging behavior."""

from __future__ import annotations

import asyncio
from typing import Coroutine


_PATCHED = False


def apply_litellm_runtime_fixes() -> None:
    """Patch LiteLLM logging worker to avoid un-awaited coroutines."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    original_enqueue = GLOBAL_LOGGING_WORKER.ensure_initialized_and_enqueue

    def _safe_enqueue(async_coroutine: Coroutine) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop: run the coroutine synchronously to avoid warnings.
            try:
                asyncio.run(async_coroutine)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(async_coroutine)
                finally:
                    loop.close()
            return
        original_enqueue(async_coroutine)

    GLOBAL_LOGGING_WORKER.ensure_initialized_and_enqueue = _safe_enqueue
