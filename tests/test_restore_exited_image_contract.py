"""Real guarded magic-link lookup plus independent order and accepted-race models."""

from pathlib import Path

import pytest
from test_restore_exited_native import isolated_namespace
from test_restore_exited_self_scope import MAPPED_USER


def image_exercise(case):
    import hashlib
    import os
    import subprocess
    import time
    from unittest.mock import patch

    from niri_desktop_continuity import restore_exited_image as elf
    from niri_desktop_continuity import restore_host as host
    from niri_desktop_continuity.restore_exited_scope import Generation, Scope

    # System-owned executable on a non-proc mount. Cooperative EOF, never termination.
    child = subprocess.Popen(["/usr/bin/cat"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    scope = Scope(time.monotonic() + 5)
    generation = Generation(scope, child.pid)
    order, target = [], []
    real_open, real_measure = os.open, host.Image.measure
    real_bracket, real_public, real_check = scope.bracket, scope.public, generation.check

    def opened(path, flags, **kw):
        assert path == "/proc" or "/" not in path
        if path == "exe" and not flags & os.O_PATH:
            order.append("follow")
            # Model a transient substitution limited to the second lookup. This is NOT
            # an actual kernel mount exploit; it demonstrates the accepted observation limit.
            fd = (
                real_open("/usr/bin/true", flags)
                if case == "transient-model"
                else real_open(path, flags, **kw)
            )
            target.append(fd)
            return fd
        if path == "exe":
            order.append("pin")
        return real_open(path, flags, **kw)

    def bracket(fd, expected, parent, name, kind, uid=None):
        if name == "exe":
            order.append("link-check")
            if case == "persistent-drift" and target:
                raise ValueError("observed link drift")
        return real_bracket(fd, expected, parent, name, kind, uid)

    def public():
        order.append("public")
        return real_public()

    def check():
        order.append("generation")
        return real_check()

    def measure(image):
        order.append("measure")
        assert target == [image.fd]
        return real_measure(image)

    try:
        with (
            patch.object(os, "open", opened),
            patch.object(scope, "bracket", bracket),
            patch.object(scope, "public", public),
            patch.object(generation, "check", check),
            patch.object(host.Image, "measure", measure),
        ):
            if case == "persistent-drift":
                with pytest.raises(ValueError, match="observed link drift"):
                    elf.image(scope, generation)
                assert "measure" not in order
            else:
                image = elf.image(scope, generation)
                try:
                    # Handwritten phase relation; expected values do not come from the wrapper.
                    f, m = order.index("follow"), order.index("measure")
                    assert "pin" in order[:f] and "link-check" in order[:f]
                    assert {"link-check", "public", "generation"} <= set(order[f + 1 : m])
                    assert {"link-check", "public", "generation"} <= set(order[m + 1 :])
                    path = "/usr/bin/true" if case == "transient-model" else "/usr/bin/cat"
                    assert (
                        image.pin["sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    )
                    assert os.fstat(image.fd).st_uid != scope.uid
                finally:
                    image.close()
        assert target
        for fd in target:
            with pytest.raises(OSError):
                os.fstat(fd)
    finally:
        generation.close()
        scope.close()
        child.stdin.close()
        assert child.wait(timeout=5) == 0


@pytest.mark.parametrize("case", ["system-owner", "persistent-drift", "transient-model"])
def test_guarded_elf_route_is_not_unconditional_atomic_symlink_provenance(case):
    result = isolated_namespace(
        MAPPED_USER
        + f"""
sys.path.insert(0,{str(Path(__file__).parent)!r})
from test_restore_exited_image_contract import image_exercise
image_exercise({case!r})
"""
    )
    assert result.returncode == 0, result.stdout + result.stderr
