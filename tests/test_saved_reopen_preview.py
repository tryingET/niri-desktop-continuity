"""Handwritten offline saved-scope ledger oracles; previews never gain effect authority."""

from copy import deepcopy
from pathlib import Path

import pytest
from test_recovery_orchestration import command
from test_recovery_review_regressions import repin
from test_saved_reopen import effects, plan, settings
from test_saved_reopen import saved_fixture as saved_fixture
from test_saved_reopen_backend import REF, SAVED_SET

from niri_desktop_continuity.map_preview import render_html
from niri_desktop_continuity.store import Store


@pytest.mark.parametrize("present", [False, True])
def test_cli_preview_distinguishes_missing_from_noop(saved, present):
    data = saved(present=present)
    key = plan(data)
    value, code = command(data, "preview", key, "--kind", "plans")
    rendered = Path(value["html"]).read_text()
    assert code == 0 and value["runtime_effects"] == "none"
    assert not effects(data)
    assert f"Exact proposal digest: <code>{key}</code>" in rendered
    assert f"Saved-set digest: <code>{SAVED_SET}</code>" in rendered
    assert "Selected saved conversations: 1." in rendered
    missing = "None" if present else f"<code>{REF}</code>"
    existing = f"<code>{REF}</code>" if present else "None"
    assert (
        f'<th scope="row">Missing (to reopen)</th><td>{int(not present)}</td><td>{missing}</td>'
    ) in rendered
    assert (
        f'<th scope="row">Already present (preserved)</th><td>{int(present)}</td><td>{existing}</td>'
    ) in rendered
    assert '<th scope="row">Unresolved (blocks approval)</th><td>0</td><td>None</td>' in rendered
    assert (
        "No launches planned: all selected references are already present." in rendered
    ) is present
    assert (
        "Only the listed missing references may be reopened after exact approval." in rendered
    ) is not present
    assert rendered.index('id="saved-set-scope"') < rendered.index("01 / Current observation")
    assert "this preview grants no approval" in rendered
    assert "Layout and hidden tabs are not reconstructed" in rendered
    # The extra scope markup does not introduce new styling or alter the token contract.
    baseline = render_html(data["snapshot"])
    assert (
        rendered.split("<style>")[1].split("</style>")[0]
        == baseline.split("<style>")[1].split("</style>")[0]
    )


def test_unresolved_scope_lists_all_exact_refs_instead_of_claiming_noop(saved):
    data = saved()
    value = settings(data)
    refs = ["a" * 64, REF, "f" * 64]
    value["observation"].update(
        session_refs=refs,
        saved_selection={
            "missing_refs": [refs[0]],
            "present_refs": [refs[1]],
            "unresolved_refs": [refs[2]],
        },
    )
    repin(data, value)
    key = plan(data)
    stored = Store(data["root"] / "state").get("plans", key)
    rendered = render_html(data["snapshot"], plan=stored, plan_digest=key)
    assert "Selected saved conversations: 3." in rendered
    assert '<th scope="row">Missing (to reopen)</th><td>1</td><td><code>' + refs[0] in rendered
    assert (
        '<th scope="row">Already present (preserved)</th><td>1</td><td><code>' + refs[1] in rendered
    )
    assert (
        '<th scope="row">Unresolved (blocks approval)</th><td>1</td><td><code>' + refs[2]
        in rendered
    )
    assert "Unresolved references block approval of this exact saved set." in rendered
    assert "No launches planned" not in rendered
    assert not effects(data)


def test_scope_markup_escapes_values_and_never_displays_private_manifest(saved):
    data = saved()
    key = plan(data)
    stored = deepcopy(Store(data["root"] / "state").get("plans", key))
    # Deliberately malformed display data: offline rendering still must not execute markup.
    attack = '<script data-x="bad">&\x00</script>'
    stored["recovery"]["saved_set"] = attack
    stored["recovery"]["observation"]["saved_selection"]["missing_refs"] = [attack]
    stored["recovery"]["observation"]["private_ref"] = "FABRICATED-NATIVE-MANIFEST"
    stored["recovery"]["observation"]["native_private_data"] = "FABRICATED-TRANSCRIPT-SECRET"
    rendered = render_html(data["snapshot"], plan=stored, plan_digest=key)
    escaped = "&lt;script data-x=&quot;bad&quot;&gt;&amp;&lt;/script&gt;"
    assert rendered.count(escaped) == 2
    assert "<script" not in rendered and "\x00" not in rendered
    assert "FABRICATED-NATIVE-MANIFEST" not in rendered
    assert "FABRICATED-TRANSCRIPT-SECRET" not in rendered
    assert "Content-Security-Policy" in rendered and "form-action 'none'" in rendered


def test_non_additive_preview_has_no_saved_scope_panel(saved):
    data = saved()
    assert "saved-set-scope" not in render_html(data["snapshot"])
