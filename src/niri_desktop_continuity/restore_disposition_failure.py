"""In-memory disposition diagnostics; never evidence, admission or retry authority."""

import json
from contextlib import contextmanager
from contextvars import ContextVar

REASONS = frozenset(
    "invalid-arguments invalid-schema ineligible-evidence legacy-linkage-attestation-required "
    "used-inventory-unaccounted evidence-pin-mismatch history-name-mismatch budget-exceeded "
    "expired current-topology-mismatch process-proof-refused publication-unsupported "
    "canonical-conflict io-failed interrupted unexpected".split()
)
PHASES = frozenset(
    "parse route history witness used-inventory current-proof capacity artifact-prepare "
    "artifact-publish dependency-barrier canonical-prepare pre-publish-proof publish "
    "canonical-directory-sync admission result cleanup stage-write stage-file-sync "
    "stage-directory-sync pre-consume-proof consume receipt-write post-consume-barrier "
    "old-v3-stage-write old-v3-stage-file-sync old-v3-stage-file-close "
    "old-v3-stage-directory-sync old-v3-post-stage-check old-v3-post-stage-barrier "
    "old-v3-post-stage-history old-v3-pre-consume-capacity old-v3-pre-consume-proof".split()
)
_active = ContextVar("disposition_failure_tracker", default=None)


class Refusal(ValueError):
    """Static guard-site code; never classify arbitrary exception text."""

    def __init__(self, reason):
        if reason not in REASONS:
            raise ValueError("unknown disposition reason")
        self.reason = reason
        super().__init__(reason)


def guard(reason, message):
    """Create the unchanged ValueError type/text at an explicitly tagged guard site."""
    if reason not in REASONS:
        raise ValueError("unknown disposition reason")
    failure = ValueError(message)
    failure._disposition_reason = reason
    return failure


class Tracker:
    def __init__(self):
        self.phase, self.phase_state = "parse", "entered"
        self.failure = None
        self.failed_phase = None
        self.publication = "not-attempted"
        self.cleanup_failure = False
        self.diagnostic_failures = []

    def enter(self, phase):
        if phase not in PHASES:
            raise ValueError("unknown disposition phase")
        self.phase, self.phase_state = phase, "entered"

    def returned(self):
        self.phase_state = "returned"

    def latch(self, failure):
        if self.failure is None:
            self.failure = failure
            self.failed_phase = (self.phase, self.phase_state)


@contextmanager
def invocation():
    tracker = Tracker()
    token = _active.set(tracker)
    try:
        yield tracker
    finally:
        _active.reset(token)


def latch(failure):
    tracker = _active.get()
    if tracker is not None:
        tracker.latch(failure)


@contextmanager
def phase(name):
    tracker = _active.get()
    if tracker is not None:
        tracker.enter(name)
    try:
        yield
    except BaseException as failure:
        latch(failure)  # Before any enclosing resource unwind.
        raise
    else:
        if tracker is not None:
            tracker.returned()


def publication_attempted():
    tracker = _active.get()
    if tracker is not None:
        tracker.publication = "unknown"


def publication_verified():
    tracker = _active.get()
    if tracker is not None:
        tracker.publication = "confirmed"


def cleanup_failed(failure):
    tracker = _active.get()
    if tracker is not None:
        tracker.cleanup_failure = True
        if tracker.failure is None:
            tracker.enter("cleanup")
            tracker.latch(failure)


def release(primary, callbacks):
    """Callbacks already retired by caller. Preserve primary, prior cause and ALL objects."""
    previous = None if primary is None else BaseException.__cause__.__get__(primary)
    if primary is not None:
        latch(primary)
    failures = []
    for callback in callbacks:
        try:
            callback()
        except BaseException as failure:
            cleanup_failed(failure)
            failures.append(failure)
    if not failures:
        return
    if primary is None:
        if len(failures) == 1:
            raise failures[0]
        raise BaseExceptionGroup("disposition release failures", failures)
    retained = [item for item in [previous, *failures] if item is not None and item is not primary]
    if retained:
        cause = (
            retained[0]
            if len(retained) == 1
            else BaseExceptionGroup("retained disposition release failures", retained)
        )
        raise primary from cause
    raise primary


def failure_objects(root):
    """Actual cause/group edges only. Context, notes and messages confer no classification."""
    seen, pending = set(), [root]
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        cause = BaseException.__cause__.__get__(item)
        if cause is not None:
            pending.append(cause)
        if issubclass(type(item), BaseExceptionGroup):
            pending.extend(reversed(BaseExceptionGroup.exceptions.__get__(item)))


def classification(tracker, failure):
    tracker.latch(failure)
    retained = list(failure_objects(failure))
    codes = set()
    for item in retained:
        if issubclass(type(item), SystemExit):
            code = SystemExit.code.__get__(item)
            codes.add(code if type(code) is int and 1 <= code <= 255 else 1)
    if any(issubclass(type(item), KeyboardInterrupt) for item in retained):
        reason, status = "interrupted", 130
    elif codes:
        reason, status = "interrupted", next(iter(codes)) if len(codes) == 1 else 1
    else:
        original = tracker.failure
        reason = "io-failed" if issubclass(type(original), OSError) else "unexpected"
        tagged = None
        if type(original) is Refusal:
            tagged = original.__dict__.get("reason")
        elif type(original) is ValueError:
            tagged = original.__dict__.get("_disposition_reason")
        if type(tagged) is str and tagged in REASONS:
            reason = tagged
        status = 1 if reason == "unexpected" else 2
    return status, reason


def projection(tracker, failure):
    status, reason = classification(tracker, failure)
    selected_phase, state = tracker.failed_phase
    return status, {
        "status": "error",
        "error": "restore-disposition-refused",
        "diagnostic": {
            "schema": "restore-accounting-failure.v1",
            "phase": selected_phase,
            "phase_state": state,
            "reason": reason,
            "publication": tracker.publication,
            "cleanup_failure": tracker.cleanup_failure,
        },
    }


def report(tracker, failure, stream):
    # Exit selection precedes best-effort encoding/output. Retain the original internally.
    status, _ = classification(tracker, failure)
    try:
        _, value = projection(tracker, failure)
        data = (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            )
            + "\n"
        )
        if len(data.encode("ascii")) > 2048:
            return status
        stream.write(data)
        stream.flush()
    except BaseException as diagnostic_failure:
        tracker.diagnostic_failures.append(diagnostic_failure)
        # No fallback, traceback, retry or replacement of the operation failure.
    return status
