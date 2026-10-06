"""Actual owned FD closure, including constructor failure plus a failing close."""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from niri_desktop_continuity import restore_exited_resources as resources
from niri_desktop_continuity import restore_host as host


def test_image_constructor_retains_primary_baseexception_and_releases_fd(monkeypatch):
    closed = []
    primary = KeyboardInterrupt("fabricated primary")
    original = os.close

    def measure(image):
        closed.append(image.fd)
        raise primary

    def close(fd):
        original(fd)
        if fd in closed:
            raise OSError("fabricated post-close failure")

    monkeypatch.setattr(host.Image, "measure", measure)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(KeyboardInterrupt) as observed:
        resources.Image(f"/proc/{os.getpid()}/exe", proc=True)
    assert observed.value is primary and isinstance(primary.__cause__, OSError)
    assert len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_every_callback_runs_when_primary_and_close_fail(tmp_path):
    primary = SystemExit("fabricated primary")
    fds = [os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _ in range(3)]
    seen = []

    def close(fd):
        os.close(fd)
        seen.append(fd)
        raise OSError("fabricated post-close failure")

    with pytest.raises(SystemExit) as observed:
        with resources.resources() as stack:
            for fd in fds:
                stack.callback(close, fd)
            raise primary
    assert observed.value is primary and seen == list(reversed(fds))
    for fd in fds:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_fd_taking_image_constructor_preserves_hash_and_close_failures(tmp_path, monkeypatch):
    path = tmp_path / "fabricated-elf"
    path.write_bytes(b"\x7fELFbody")
    path.chmod(0o700)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    real_close = os.close
    closed = []

    def measure(_):
        raise KeyboardInterrupt("hash interrupted")

    def close(actual):
        closed.append(actual)
        real_close(actual)
        raise OSError("close after hash failed")

    monkeypatch.setattr(host.Image, "measure", measure)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(KeyboardInterrupt, match="hash interrupted") as result:
        resources.FDImage(fd, deadline=1)
    assert isinstance(result.value.__cause__, OSError)
    assert closed == [fd]
    with pytest.raises(OSError):
        os.fstat(fd)


class Cancel(BaseException):
    pass


def graph(root):
    """Handwritten identity oracle: cause/groups only, never exception context."""
    pending, seen, result = [root], set(), []
    while pending:
        item = pending.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        result.append(item)
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions)
        pending.append(item.__cause__)
    return result


def contains(root, expected):
    actual = graph(root)
    assert all(any(item is value for item in actual) for value in expected), (expected, actual)
    assert all(item.__cause__ is not item for item in actual)


def caught(call):
    try:
        call()
    except BaseException as error:
        return error
    raise AssertionError("expected actual failure")


def assert_closed(fds):
    for fd in fds:
        try:
            os.fstat(fd)
        except OSError as error:
            assert error.errno == 9
        else:
            raise AssertionError("owned descriptor not released")


def faults(count):
    # Acquisition-order oracle, deliberately mixing every cancellation category.
    nested = BaseExceptionGroup("existing cleanup group", [OSError("leaf"), Cancel("leaf")])
    values = [
        OSError("first"),
        KeyboardInterrupt("second"),
        SystemExit(23),
        Cancel("fourth"),
        nested,
        OSError("sixth"),
    ][:count]
    causes = [RuntimeError("cleanup prior " + str(i)) for i in range(count)]
    for value, cause in zip(values, causes):
        value.__cause__ = cause
    return values, causes


def invoke(stack, close, primary):
    if primary is None:
        close()
    else:
        try:
            raise primary
        except BaseException:
            resources.close_failed(close)
            raise


def prior_primary(mode):
    if mode == "none":
        return None, []
    primary = Cancel("body primary")
    if mode == "prior":
        prior = BaseExceptionGroup("body prior", [ValueError("prior leaf"), Cancel("prior leaf")])
        primary.__cause__ = prior
        return primary, [primary, prior, *prior.exceptions]
    return primary, [primary]


def direct(root, fs, case):
    # Same three falsifiers as primitive-closure/v06/cleanup.py, real O_TMPFILE FDs.
    target = root / fs
    target.mkdir()
    if fs == "tmpfs":
        subprocess.run(
            ["mount", "-t", "tmpfs", "-o", "mode=0700,size=1m", "tmpfs", str(target)], check=True
        )
    directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    primary, prior = ValueError("primary"), RuntimeError("prior")
    primary.__cause__ = prior
    first = KeyboardInterrupt("first") if case.endswith("cancellation") else OSError("first")
    second = SystemExit(23) if case.endswith("cancellation") else OSError("second")
    owners, fds, released = [], [], []
    real = os.close

    def closing(fd):
        real(fd)
        released.append(fd)
        raise first if fd == fds[0] else second

    def operation():
        with resources.resources() as stack:
            for _ in range(2):
                fd = os.open(".", os.O_TMPFILE | os.O_RDWR | os.O_CLOEXEC, 0o600, dir_fd=directory)
                fds.append(fd)
                owners.append(resources.FD(fd, stack))
            if case.startswith("primary"):
                raise primary

    try:
        with patch.object(os, "close", closing):
            error = caught(operation)
            assert released == list(reversed(fds))
            assert all(owner.fd is None for owner in owners)
            for owner in owners:
                owner.close()
            assert released == list(reversed(fds))
        assert_closed(fds)
        print("REACHED direct actual releases", fs, case, fds, flush=True)
        contains(error, [first, second] + ([primary, prior] if case.startswith("primary") else []))
        if case.startswith("primary"):
            assert error is primary
        else:
            assert isinstance(error, BaseExceptionGroup)
            assert error.exceptions == (second, first)
        assert not list(target.iterdir())
    finally:
        real(directory)


def callbacks(case):
    events, token = [], object()
    manager = resources.resources()
    stack = manager.__enter__()
    if case == "api":

        def func(*args, **kw):
            events.append((args, kw))
            return True

        assert stack.callback(func, token, flag=token) is func
        assert stack.callback(func, token, flag=token) is func
        stack.close()
        stack.close()
        manager.__exit__(None, None, None)
        assert events == [((token,), {"flag": token}), ((token,), {"flag": token})]
        try:
            stack.callback(func)
        except RuntimeError:
            pass
        else:
            raise AssertionError("registration after close accepted")
    elif case == "reentrant":

        def last():
            events.append("last")
            stack.close()
            try:
                stack.callback(lambda: events.append("late"))
            except RuntimeError:
                events.append("rejected")
            else:
                raise AssertionError("registration during close accepted")

        stack.callback(events.append, "first")
        stack.callback(last)
        stack.close()
        stack.close()
        manager.__exit__(None, None, None)
        assert events == ["last", "rejected", "first"]
    elif case == "noerror":
        primary, objects = prior_primary("prior")
        primary.add_note("preexisting body note")
        stack.callback(lambda: True)
        old_cause, old_notes = primary.__cause__, list(primary.__notes__)
        error = caught(lambda: invoke(stack, stack.close, primary))
        assert error is primary and primary.__cause__ is old_cause
        assert primary.__notes__ == old_notes
        contains(error, objects)
        manager.__exit__(None, None, None)
    elif case == "groups":
        a, b = OSError("a"), Cancel("b")
        one = BaseExceptionGroup("one", [a, b])
        two = BaseExceptionGroup("two", [one, a])
        prior = ValueError("group prior")
        one.__cause__ = prior
        prior.__cause__ = one  # Existing cycle; handwritten walker must terminate.

        def fail(error):
            raise error

        stack.callback(fail, one)
        stack.callback(fail, two)
        stack.callback(fail, one)  # Each registration remains an obligation.
        error = caught(stack.close)
        assert isinstance(error, BaseExceptionGroup)
        assert error.exceptions[0] is one and error.exceptions[1] is two
        assert error.exceptions[2] is one
        contains(error, [one, two, a, b, prior])
        stack.close()
        manager.__exit__(None, None, None)
    else:
        primary, objects = prior_primary("prior" if case.endswith("prior") else "body")
        if case.startswith("self"):
            failure = primary
        elif case == "sole":
            failure = OSError("sole actual cleanup")
        else:
            failure = primary.__cause__

        def fail():
            events.append("close")
            raise failure

        stack.callback(fail)
        old_cause, old_notes = primary.__cause__, getattr(primary, "__notes__", None)
        if case == "sole":
            error = caught(lambda: resources.close_failed(stack.close))
            assert error is failure
        else:
            error = caught(lambda: invoke(stack, stack.close, primary))
            assert error is primary
            contains(error, objects + [failure])
            if case.startswith("self"):
                assert primary.__cause__ is old_cause
                assert getattr(primary, "__notes__", None) is old_notes
        saved = primary.__cause__, tuple(getattr(primary, "__notes__", []))
        stack.close()
        try:
            raise primary
        except BaseException:
            resources.close_failed(stack.close)
        assert (primary.__cause__, tuple(getattr(primary, "__notes__", []))) == saved
        manager.__exit__(None, None, None)
        assert events == ["close"]


def handles(owner, name):
    if name == "Scope":
        return [
            owner.fd,
            owner.self_fd,
            owner.own_fd,
            owner.pidns[0],
            owner.userns[0],
            owner.own_directory[0],
        ]
    if name == "Generation":
        return [owner.directory[0], owner.fd, owner.pidns[0], owner.userns[0]]
    return [owner.directory[0], owner.fd]


def construct(name):
    from niri_desktop_continuity import restore_exited_scope as native

    if name == "Scope":
        return native.Scope(time.monotonic() + 30), None
    scope = native.Scope(time.monotonic() + 30)
    return getattr(native, name)(scope, os.getpid()), scope


def native_control(name):
    from niri_desktop_continuity import restore_exited_scope as native

    real_namespace, observed = native.calls.namespace, []

    def namespace(pidfd, command):
        fd = real_namespace(pidfd, command)
        observed.append((pidfd, command, fd))
        return fd

    with patch.object(native.calls, "namespace", namespace):
        owner, scope = construct(name)
        owner.check()
    fds = handles(owner, name)
    assert {command for _, command, _ in observed} == {0xFF05, 0xFF09}
    real, seen = os.close, []

    def close(fd):
        real(fd)
        seen.append(fd)

    try:
        with patch.object(os, "close", close):
            owner.close()
            owner.close()
        assert seen == list(reversed(fds))
        assert_closed(fds)
        if name != "Scope":
            assert owner.fd is None
            error = caught(owner.check)
            assert isinstance(error, ValueError) and "closed" in str(error)
        print("REACHED no-fault native control and actual pidfd ioctls", name, observed, flush=True)
    finally:
        if scope is not None:
            scope.close()


def reuse_file(root):
    path = root / "replacement"
    path.write_bytes(b"INDEPENDENT REPLACEMENT BYTES\x00\xff")
    return path


def replace(fd, path, original_pin, real):
    assert_closed([fd])
    fresh = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    if fresh != fd:
        # Only the just-closed, proved-owned vacant number may be overwritten.
        assert_closed([fd])
        os.dup2(fresh, fd, inheritable=False)
        real(fresh)
    info = os.fstat(fd)
    pin = info.st_dev, info.st_ino
    assert pin != original_pin and not os.get_inheritable(fd)
    assert os.pread(fd, 100, 0) == b"INDEPENDENT REPLACEMENT BYTES\x00\xff"
    print("REACHED real retired-FD replacement", fd, original_pin, pin, flush=True)
    return pin


def intact(fd, pin):
    info = os.fstat(fd)
    assert (info.st_dev, info.st_ino) == pin
    assert os.pread(fd, 100, 0) == b"INDEPENDENT REPLACEMENT BYTES\x00\xff"


def owner_errors(root, name, mode, reuse=False, zero=False):
    if zero:
        os.close(0)  # Disposable worker only; never manager stdio.
    # Generations must allocate their own directory at zero, not Scope's root.
    if zero and name != "Scope":
        reserve = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        assert reserve == 0
        from niri_desktop_continuity import restore_exited_scope as native

        scope = native.Scope(time.monotonic() + 30)
        os.close(reserve)
        owner = getattr(native, name)(scope, os.getpid())
    else:
        owner, scope = construct(name)
    fds = handles(owner, name)
    assert len(set(fds)) == {"Scope": 6, "Generation": 4, "AncestorGeneration": 2}[name]
    owner.check()  # Native preconditions really succeeded before faults.
    assert all(not os.get_inheritable(fd) for fd in fds)
    pins = [(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in fds]
    errors, causes = faults(len(fds))
    primary, expected = prior_primary(mode)
    seen, reused = [], []
    real = os.close
    path = reuse_file(root) if reuse else None

    def closing(fd):
        if fd not in fds:
            return real(fd)
        assert fd not in seen
        real(fd)
        seen.append(fd)
        if reuse and fd == fds[0]:
            reused.append(replace(fd, path, pins[0], real))
        raise errors[fds.index(fd)]

    try:
        with patch.object(os, "close", closing):
            error = caught(lambda: invoke(owner.stack, owner.close, primary))
            assert seen == list(reversed(fds))
            owner.close()
            owner.stack.close()
            assert seen == list(reversed(fds))
            if reuse:
                intact(fds[0], reused[0])
        print("REACHED native owner", name, mode, fds, "reused", bool(reused), flush=True)
        contains(error, expected + errors + causes)
        assert all(value.__cause__ is cause for value, cause in zip(errors, causes))
        if primary is None:
            assert isinstance(error, BaseExceptionGroup)
            assert all(a is b for a, b in zip(error.exceptions, reversed(errors)))
        else:
            assert error is primary
        if zero:
            assert fds[0] == 0
        if reuse:
            intact(fds[0], reused[0])
        assert_closed(fds[1:] if reuse else fds)
    finally:
        if reused:
            real(fds[0])
        if scope is not None:
            scope.close()


def partial(root, name, stage, reuse=False):
    from niri_desktop_continuity import restore_exited_scope as native

    kind = getattr(native, name)
    scope = None if name == "Scope" else native.Scope(time.monotonic() + 30)
    primary, expected = prior_primary("prior")
    observed, fds, seen, reused, ioctls = [], [], [], [], []
    original_init, original_fd = kind.__init__, resources.FD.__init__
    real_close, real_namespace = os.close, native.calls.namespace
    boundary = {
        "zero": 0,
        "first": 1,
        "multiple": 3 if name != "AncestorGeneration" else 2,
        "late": {"Scope": 5, "Generation": 4, "AncestorGeneration": 2}[name],
    }[stage]
    errors, causes = faults(boundary)
    path = reuse_file(root) if reuse else None
    pins = []

    def init(owner, *args, **kw):
        observed.append(owner)
        original_init(owner, *args, **kw)

    def namespace(*args):
        fd = real_namespace(*args)  # Actual pidfd ioctl, no invented proof result.
        ioctls.append((args[1], fd))
        return fd

    def registered(owner, fd, stack):
        original_fd(owner, fd, stack)
        if observed and stack is observed[0].stack:
            fds.append(fd)
            info = os.fstat(fd)
            pins.append((info.st_dev, info.st_ino))
            if len(fds) == boundary:
                raise primary  # Real registered boundary, before caller field assignment.

    original_start = native.calls.profile if scope is None else scope.check

    def start(*args, **kw):
        value = original_start(*args, **kw)
        if boundary == 0:
            raise primary  # Actual profile/check ran, no acquisition yet.
        return value

    def closing(fd):
        if fd not in fds:
            return real_close(fd)
        assert fd not in seen
        real_close(fd)
        seen.append(fd)
        if reuse and fd == fds[0]:
            reused.append(replace(fd, path, pins[0], real_close))
        raise errors[fds.index(fd)]

    target, attr = (native.calls, "profile") if scope is None else (scope, "check")
    try:
        with (
            patch.object(kind, "__init__", init),
            patch.object(resources.FD, "__init__", registered),
            patch.object(native.calls, "namespace", namespace),
            patch.object(target, attr, start),
            patch.object(os, "close", closing),
        ):
            error = caught(
                lambda: kind(time.monotonic() + 30) if scope is None else kind(scope, os.getpid())
            )
            assert len(observed) == 1 and len(fds) == boundary
            assert seen == list(reversed(fds))
            observed[0].close()
            observed[0].stack.close()
            assert seen == list(reversed(fds))
            if reused:
                intact(fds[0], reused[0])
        print("REACHED partial", name, stage, fds, "native ioctls", ioctls, flush=True)
        assert error is primary
        contains(error, expected + errors + causes)
        assert all(value.__cause__ is cause for value, cause in zip(errors, causes))
        if boundary == 0:
            assert primary.__cause__ is expected[1]
        if name == "Generation" and stage == "multiple":
            assert ioctls and ioctls[0][0] == 0xFF05
        assert_closed(fds[1:] if reused else fds)
    finally:
        if reused:
            real_close(fds[0])
        if scope is not None:
            scope.close()


def wrappers(root, name, constructor=False, zero=False):
    path = root / "elf"
    path.write_bytes(b"\x7fELFhandwritten image bytes")
    path.chmod(0o700)
    replacement = reuse_file(root)
    manager = resources.resources()
    stack = manager.__enter__()
    observed, seen, reused = [], [], []
    primary, expected = prior_primary("prior")
    failure = KeyboardInterrupt("actual post-close failure")
    failure.__cause__ = OSError("cleanup prior")
    kind = getattr(resources, name)
    original_init, real, measure = kind.__init__, os.close, host.Image.measure
    if zero:
        real(0)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC) if name != "Image" else None

    def init(owner, *args, **kw):
        observed.append(owner)
        original_init(owner, *args, **kw)
        if constructor and name == "FD":
            raise primary

    def measuring(image):
        result = measure(image)  # Genuine ELF/hash boundary reached before cancellation.
        if constructor:
            raise primary
        return result

    def closing(actual):
        owner = observed[0]
        owned = owner.fd if owner.fd is not None else fd_number[0]
        if actual != owned:
            return real(actual)
        assert not seen
        info = os.fstat(actual)
        real(actual)
        seen.append(actual)
        reused.append(replace(actual, replacement, (info.st_dev, info.st_ino), real))
        raise failure

    fd_number = []

    # Retired self.fd is already None at the syscall; observe entry FD independently.
    def opened(*args, **kw):
        value = real_open(*args, **kw)
        if not fd_number:
            fd_number.append(value)
        return value

    real_open = os.open
    if fd is not None:
        fd_number.append(fd)
    try:
        with (
            patch.object(kind, "__init__", init),
            patch.object(host.Image, "measure", measuring),
            patch.object(os, "open", opened),
            patch.object(os, "close", closing),
        ):

            def operation():
                if name == "Image":
                    owner = kind(path, deadline=time.monotonic() + 30)
                elif name == "FDImage":
                    owner = kind(fd, deadline=time.monotonic() + 30)
                else:
                    owner = kind(fd, stack)
                if not constructor:
                    owner.close()

            if name == "FD" and constructor:

                def failed_fd():
                    try:
                        operation()
                    except BaseException:
                        resources.close_failed(stack.close)
                        raise

                error = caught(failed_fd)
            else:
                error = caught(operation)
            assert observed[0].fd is None and seen == fd_number
            observed[0].close()
            stack.close()
            manager.__exit__(None, None, None)
            assert seen == fd_number
            intact(fd_number[0], reused[0])
        print("REACHED wrapper", name, constructor, zero, fd_number, flush=True)
        assert error is (primary if constructor else failure)
        contains(error, ([*expected] if constructor else []) + [failure, failure.__cause__])
        if zero:
            assert fd_number == [0]
        intact(fd_number[0], reused[0])
    finally:
        if reused:
            real(fd_number[0])


def image_route(root):
    from niri_desktop_continuity import restore_exited_image as elf
    from niri_desktop_continuity import restore_exited_scope as native

    scope = native.Scope(time.monotonic() + 30)
    peer = native.Generation(scope, os.getpid())
    route, target, seen = [], [], []
    errors, causes = faults(3)
    real_component, real_init, real_close = scope.component, resources.FDImage.__init__, os.close

    def component(stack, parent, name, *args, **kw):
        result = real_component(stack, parent, name, *args, **kw)
        if name == "exe" and not route:
            route.extend([parent, result[0]])
        return result

    def init(image, fd, **kw):
        real_init(image, fd, **kw)
        target.append((fd, image))

    def closing(fd):
        owned = [*route, *[item[0] for item in target]]
        if fd not in owned:
            return real_close(fd)
        assert fd not in seen
        real_close(fd)
        seen.append(fd)
        raise errors[owned.index(fd)]

    try:
        with (
            patch.object(scope, "component", component),
            patch.object(resources.FDImage, "__init__", init),
            patch.object(os, "close", closing),
        ):
            error = caught(lambda: elf.image(scope, peer))
            assert len(route) == 2 and len(target) == 1
            assert seen == [route[1], route[0], target[0][0]]
            target[0][1].close()
            assert seen == [route[1], route[0], target[0][0]]
        print("REACHED explicit image-route files.close then measured.close", seen, flush=True)
        assert isinstance(error, BaseExceptionGroup)
        contains(error, errors + causes)
        assert target[0][1].fd is None
        assert_closed(seen)
    finally:
        peer.close()
        scope.close()


def cohort(root):
    from niri_desktop_continuity import restore_exited_image as elf
    from niri_desktop_continuity import restore_exited_scope as native

    assert os.getppid() != 1, "exclusion-only actual non-init parent required"
    primary, expected = prior_primary("prior")
    owners, fds, groups, seen = [], [], [], []
    errors, causes = [], []
    real = os.close

    def closing(fd):
        if fd not in fds:
            return real(fd)
        assert fd not in seen
        real(fd)
        seen.append(fd)
        raise errors[fds.index(fd)]

    def observing(owner):
        try:
            owner.close()
        except BaseException as error:
            groups.append(error)
            raise

    def operation():
        with resources.resources() as stack:
            scope = native.Scope(time.monotonic() + 30)
            stack.callback(observing, scope)
            peer = native.Generation(scope, os.getpid())
            stack.callback(observing, peer)
            image = elf.image(scope, peer)
            stack.callback(observing, image)
            # Nonowning supplied peer, real strong caller and weak parent chain.
            original_weak_close = native.AncestorGeneration.close

            def weak_close(owner):
                try:
                    original_weak_close(owner)
                except BaseException as error:
                    groups.append(error)
                    raise

            with patch.object(native.AncestorGeneration, "close", weak_close):
                value = native.Cohort(scope, stack, {os.getpid()}, 2147483600, peer)
                caller = native.ancestry(scope, value.ancestor)
            value.sealed = True
            ancestor = value.generations[os.getppid()]
            assert isinstance(ancestor, native.AncestorGeneration)
            assert value.full(os.getpid()) is peer
            assert caller["ancestry"][0]["process"]["pid"] == os.getpid()
            assert caller["ancestry"][-1]["ppid"] == 1
            owners.extend([scope, peer, image, ancestor])
            fds.extend(
                handles(scope, "Scope")
                + handles(peer, "Generation")
                + [image.fd]
                + handles(ancestor, "AncestorGeneration")
            )
            assert len(set(fds)) == 13
            for owner in (scope, peer, ancestor):
                owner.check()
            image.validate()
            for count in (6, 4, 1, 2):
                values, previous = faults(count)
                errors.extend(values)
                causes.extend(previous)
            with patch.object(os, "close", closing):
                try:
                    raise primary
                except BaseException:
                    resources.close_failed(stack.close)
                    raise

    error = caught(operation)
    assert seen == list(reversed(fds))
    print("REACHED actual sealed strong/nonowning-peer/exclusion cohort", fds, flush=True)
    contains(error, expected + errors + causes + groups)
    assert error is primary
    # Inner groups themselves, not flattened copies, are the outer group's members.
    outer = primary.__cause__.exceptions[1]
    assert isinstance(outer, BaseExceptionGroup) and len(outer.exceptions) == 4
    assert all(a is b for a, b in zip(outer.exceptions, groups))
    weak = outer.exceptions[0]
    assert isinstance(weak, BaseExceptionGroup)
    assert weak.exceptions[0] is errors[-1] and weak.exceptions[1] is errors[-2]
    for owner in owners:
        owner.close()
    assert seen == list(reversed(fds))
    assert_closed(fds)


RESOURCE_CASES = (
    [
        "direct:" + fs + ":" + case
        for fs in ("backing", "tmpfs")
        for case in ("primary-multiple", "primary-multiple-cancellation", "multiple-only")
    ]
    + [
        "callbacks:" + case
        for case in ("api", "reentrant", "noerror", "groups", "sole", "self", "self-prior", "prior")
    ]
    + [
        "owner:" + name + ":" + mode
        for name in ("Scope", "Generation", "AncestorGeneration")
        for mode in ("none", "body", "prior", "reuse", "zero")
    ]
    + [
        "partial:" + name + ":" + stage
        for name in ("Scope", "Generation", "AncestorGeneration")
        for stage in ("zero", "first", "multiple", "late", "reuse")
    ]
    + [
        "wrapper:" + name + ":" + stage
        for name in ("FD", "FDImage", "Image")
        for stage in ("close", "constructor", "zero", "constructor-zero")
    ]
    + ["control:" + name for name in ("Scope", "Generation", "AncestorGeneration")]
    + ["image-route", "cohort"]
)


def resource_worker(case, root):
    """Same assertions for standalone focused tiers and the unchanged CI fixture."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    assert os.getpid() != 1
    assert not any(
        os.environ.get(k) for k in ("NIRI_SOCKET", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DISPLAY")
    )
    parts = case.split(":")
    if parts[0] == "direct":
        direct(root, *parts[1:])
    elif parts[0] == "callbacks":
        callbacks(parts[1])
    elif parts[0] == "owner":
        mode = parts[2]
        owner_errors(
            root,
            parts[1],
            "prior" if mode in ("reuse", "zero") else mode,
            reuse=mode in ("reuse", "zero"),
            zero=mode == "zero",
        )
    elif parts[0] == "partial":
        partial(
            root,
            parts[1],
            "multiple" if parts[2] == "reuse" else parts[2],
            reuse=parts[2] == "reuse",
        )
    elif parts[0] == "wrapper":
        wrappers(
            root,
            parts[1],
            constructor=parts[2].startswith("constructor"),
            zero=parts[2].endswith("zero"),
        )
    elif parts[0] == "control":
        native_control(parts[1])
    elif case == "image-route":
        image_route(root)
    elif case == "cohort":
        cohort(root)
    else:
        raise AssertionError("unknown resource case")


@pytest.mark.parametrize("case", RESOURCE_CASES)
def test_real_resource_cohort(case, tmp_path):
    from test_restore_exited_native import isolated_namespace

    # One extra cooperative subprocess supplies a genuine non-init parent for ancestry.
    module = str(Path(__file__).parent)
    child = (
        f"import sys;sys.path.insert(0,{module!r});"
        f"from test_restore_exited_resources import resource_worker;"
        f"resource_worker({case!r},{str(tmp_path / 'case')!r})"
    )
    result = isolated_namespace(
        f"""
import subprocess
raise SystemExit(subprocess.call([sys.executable,'-I','-B','-c',{child!r}]))
""",
        data_root=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
