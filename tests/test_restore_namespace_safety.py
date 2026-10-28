"""Source-only checks: run directly with Python, never import the native fixture.

These AST/string checks do not execute shell, namespace or product code and do not
prove kernel isolation. The behavioral regression requires a separate-kernel guest.
"""

import ast
import shlex
import unittest
from pathlib import Path


class NamespaceSafetySourceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name("test_restore_exited_native.py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        helpers = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "isolated_namespace"
        ]
        self.assertEqual(len(helpers), 1)
        self.helper = helpers[0]
        scripts = [
            node
            for node in ast.walk(self.helper)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "script" for t in node.targets)
        ]
        self.assertEqual(len(scripts), 1)
        self.assertIsInstance(scripts[0].value, ast.Constant)
        self.assertIsInstance(scripts[0].value.value, str)
        self.script = scripts[0].value.value
        self.lines = [line.strip() for line in self.script.splitlines() if line.strip()]

    def test_old_root_detached_and_removed_before_only_payload_exec(self):
        self.assertEqual(self.lines.count("pivot_root . old-root"), 1)
        pivot = self.lines.index("pivot_root . old-root")
        # Exact unconditional suffix: no pipeline, conditional, background job or
        # failure-masking command can intervene between teardown and payload exec.
        self.assertEqual(
            self.lines[pivot - 1 :],
            [
                'cd "$jail"',
                "pivot_root . old-root",
                "cd /",
                "umount -l /old-root",
                "rmdir /old-root",
                'exec chroot / "$@"',
            ],
        )
        self.assertEqual(
            [line for line in self.lines if line.startswith("exec ")],
            ['exec chroot / "$@"'],
        )

    def test_errexit_is_enabled_without_overrides(self):
        self.assertEqual(self.lines[0], "set -eu")
        tokens = shlex.split(self.script, comments=True)
        self.assertEqual(tokens.count("set"), 1)
        self.assertNotIn("trap", tokens)
        self.assertNotIn("eval", tokens)
        # The literal script must be the sole value of this binding.
        self.assertEqual(
            sum(
                isinstance(node, ast.Name)
                and node.id == "script"
                and isinstance(node.ctx, ast.Store)
                for node in ast.walk(self.helper)
            ),
            1,
        )

    def test_private_namespace_runner_uses_the_checked_script(self):
        statement = self.helper.body[-1]
        self.assertIsInstance(statement, ast.Return)
        call = statement.value
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(
            ast.dump(call.func), ast.dump(ast.parse("subprocess.run", mode="eval").body)
        )
        # Handwritten argv oracle: the shell runs the literal script as its
        # top-level command, inside the private mount/PID (and optional user) scope.
        expected = ast.parse(
            """[
                'unshare',
                *([] if os.getuid() == 0 else ['--user', '--map-root-user']),
                '--mount', '--pid', '--fork', '--', '/bin/sh', '-c', script,
                'fixture', str(jail), str(candidate), str(evidence), str(alias),
                python, '-I', '-B', '-c', init,
            ]""",
            mode="eval",
        ).body
        self.assertEqual(len(call.args), 1)
        self.assertEqual(ast.dump(call.args[0]), ast.dump(expected))

    def test_mount_privacy_and_readonly_bindings_are_retained(self):
        private = self.lines.index("mount --make-rprivate /")
        self.assertEqual(
            next(line for line in self.lines if line.startswith("mount ")),
            "mount --make-rprivate /",
        )
        self.assertLess(private, self.lines.index('mount --bind "$jail" "$jail"'))
        self.assertEqual(
            [line for line in self.lines if line.startswith("mount -o remount,bind,ro ")],
            [
                'mount -o remount,bind,ro "$jail/$dir"',
                'mount -o remount,bind,ro "$jail/candidate"',
                'mount -o remount,bind,ro "$jail$alias"',
                'mount -o remount,bind,ro "$jail/dev/urandom"',
            ],
        )
        self.assertIn("for dir in usr lib lib64; do", self.lines)


if __name__ == "__main__":
    unittest.main()
