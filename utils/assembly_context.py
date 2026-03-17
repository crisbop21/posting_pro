"""Thread-safe coordination context for video assembly.

Solves four structural problems with the previous dict-based approach:

1. Race condition: state is written BEFORE done_event is set, so the UI
   thread never reads an incomplete result.
2. Zombie threads: cancel_event lets the UI signal old threads to stop.
3. Stale results: gen_id is embedded in the context and validated on read.
4. Filename collision: run_id produces unique temp file paths per run.

Usage in app.py:

    ctx = AssemblyContext(gen_id=next_id)
    st.session_state["_assembly_ctx"] = ctx

    # Worker thread:
    try:
        result = assemble.run(state, ctx=ctx)
        ctx.complete(result)
    except CancelledError:
        ctx.fail("Cancelled by user")
    except Exception as e:
        ctx.fail(str(e))

    # UI polling:
    if ctx.is_done:
        state, error = ctx.read_result()
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """Raised when a worker thread detects that cancellation was requested."""


@dataclass
class AssemblyContext:
    """Coordinates a single assembly run between the worker thread and UI."""

    gen_id: int
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # Signalling primitives
    cancel_event: threading.Event = field(default_factory=threading.Event)
    done_event: threading.Event = field(default_factory=threading.Event)

    # Internal state — protected by _lock
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _state: dict | None = field(default=None, repr=False)
    _error: str | None = field(default=None, repr=False)
    _log: list[str] = field(default_factory=list)

    # ── Public queries ────────────────────────────────────────────

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    @property
    def is_done(self) -> bool:
        return self.done_event.is_set()

    # ── Worker-thread API ─────────────────────────────────────────

    def check_cancelled(self, stage: str = "") -> None:
        """Raise CancelledError if the UI requested cancellation.

        Call this at natural checkpoints in the worker thread (before
        voiceover generation, before compositing, etc.).
        """
        if self.cancel_event.is_set():
            msg = "Assembly cancelled"
            if stage:
                msg += f" during {stage}"
            logger.info(msg)
            raise CancelledError(msg)

    def log(self, msg: str) -> None:
        """Append a timestamped message to the shared log."""
        import datetime as _dt

        ts = _dt.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with self._lock:
            self._log.append(line)
        logger.info(msg)

    def complete(self, state: dict) -> None:
        """Signal successful completion.

        IMPORTANT: writes state under lock BEFORE setting done_event,
        guaranteeing that any reader who sees is_done=True will also
        see the fully-written state dict.
        """
        with self._lock:
            self._state = state
        self.done_event.set()

    def fail(self, error: str) -> None:
        """Signal failure.

        Writes error under lock BEFORE setting done_event.
        """
        with self._lock:
            self._error = error
        self.done_event.set()

    # ── UI-thread API ─────────────────────────────────────────────

    def read_result(self) -> tuple[dict | None, str | None]:
        """Read the final result.  Only valid after is_done is True.

        Returns:
            (state_dict, None) on success, or (None, error_string) on failure.
        """
        with self._lock:
            return self._state, self._error

    def get_log(self) -> list[str]:
        """Return a snapshot of the current log lines (thread-safe copy)."""
        with self._lock:
            return list(self._log)

    # ── Unique paths ──────────────────────────────────────────────

    def voiceover_path(self) -> str:
        """Return a unique voiceover filename for this run."""
        return f"tmp/voiceover_{self.run_id}.mp3"
