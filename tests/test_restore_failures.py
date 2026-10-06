"""Error recovery never becomes launch, ownership, history or action replay authority."""

import errno
import subprocess

import pytest
from test_restore_handshake import fabricated_elf as fabricated_elf  # noqa: F401
from test_restore_queries import run_boundary

from niri_desktop_continuity import restore, restore_producer


@pytest.mark.parametrize("query", ["windows", "workspaces", "outputs"])
def test_real_executor_exhaustion_and_separate_diagnostic_read(tmp_path, fabricated_elf, query):
    run_boundary(tmp_path, fabricated_elf, "persistent", query=query)


@pytest.mark.parametrize("damage", ["unowned", "surplus", "exit", "outputs", "malformed"])
def test_real_proofs_still_refuse_changed_sample_after_retry(tmp_path, fabricated_elf, damage):
    run_boundary(tmp_path, fabricated_elf, damage=damage)


@pytest.mark.parametrize("fault", ["constructor", "timeout", "nonzero"])
def test_real_executor_layout_ambiguity_keeps_one_dispatch_and_pending_intent(
    tmp_path, fabricated_elf, fault
):
    run_boundary(tmp_path, fabricated_elf, failures=0, effect_fault=fault)


@pytest.mark.parametrize("fault", ["constructor", "timeout", "nonzero"])
def test_real_producer_spawn_ambiguity_keeps_one_ticket_and_pending_intent(
    tmp_path, fabricated_elf, fault
):
    run_boundary(tmp_path, fabricated_elf, failures=0, spawn_fault=fault)


@pytest.mark.parametrize("target", ["action", "spawn", "producer"])
def test_constructor_eagain_never_retries_any_effect(monkeypatch, target):
    error = BlockingIOError(errno.EAGAIN, "effect")
    calls = []

    def construct(argv, **kwargs):
        calls.append(argv)
        raise error

    monkeypatch.setattr(subprocess, "Popen", construct)

    def call():
        if target == "producer":
            monkeypatch.setattr(restore_producer.host, "route", lambda identity: None)
            return restore_producer.niri_spawn(
                ["fabricated"],
                {"niri_socket": "fabricated"},
                restore_producer.time.monotonic() + 10,
            )
        if target == "spawn":
            return restore.LiveDesktop().spawn(["fabricated"])
        return restore.LiveDesktop().action("focus-window", "--id", "1")

    with pytest.raises(BlockingIOError) as raised:
        call()
    assert raised.value is error and len(calls) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        "poll-budget",
        "shared-expiry",
        "persist-expiry",
        "postcondition-limit",
        "protected-overlap",
        "protected-drift",
        "stale-generation",
        "pending-exit",
        "split-1",
        "split-3",
        "split-4",
        "split-reference",
        "split-drift",
        "split-malformed",
        "outputs-nonzero",
        "version-persistent",
        "version-nonzero",
    ],
)
def test_actual_executor_retry_coupled_budget_proof_and_split_boundaries(
    tmp_path, fabricated_elf, scenario
):
    run_boundary(tmp_path, fabricated_elf, scenario=scenario)


@pytest.mark.parametrize(
    "scenario", ["cancel-communicate", "cancel-sleep", "cancel-decode", "cancel-action"]
)
@pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit])
def test_actual_executor_reached_cancellation_unwinds_without_new_authority(
    tmp_path, fabricated_elf, scenario, kind
):
    # Fixture verifies actual process-observed boundary, exact exception identity,
    # unresolved canonical history/pointer and no cleanup before re-raising.
    with pytest.raises(kind, match="fabricated reached cancellation"):
        run_boundary(tmp_path, fabricated_elf, scenario=scenario, cancellation=kind)
    assert (tmp_path / "cancellation-evidence.json").is_file()
