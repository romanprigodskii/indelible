"""The contributor tooling in dev/: the tracked pre-push hook that runs the privacy check.

The privacy check itself needs a local, git-ignored denylist, so it can't run here.
These tests run the hook against a stub check in a throwaway git repository, keep
its line endings LF (sh fails on CRLF), and make sure the README tells a contributor
how to turn the hook on.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from helpers import REPO_DIR
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR

HOOK = REPO_DIR / "dev" / "hooks" / "pre-push"
HOOKS_LINE = "git config core.hooksPath dev/hooks"


class PrePushHook(unittest.TestCase):
    def test_the_hook_runs_the_privacy_check(self):
        text = HOOK.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertIn('"$root/dev/privacy_grep.py"', text)
        self.assertIn(HOOKS_LINE, text)

    def test_the_readme_says_how_to_turn_it_on(self):
        readme = (REPO_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(HOOKS_LINE, readme)

    def test_the_hook_has_lf_line_endings(self):
        # sh stops at a CRLF line ("syntax error: unexpected end of file"), and every push
        # would then fail. On the Windows CI job this checks .gitattributes did its work.
        self.assertNotIn(b"\r", HOOK.read_bytes())

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_git_checks_the_hook_out_with_lf(self):
        r = subprocess.run(["git", "check-attr", "eol", "--", "dev/hooks/pre-push"], cwd=str(REPO_DIR),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
        if r.returncode != 0:
            self.skipTest("not a git checkout")
        self.assertEqual(r.stdout.strip(), "dev/hooks/pre-push: eol: lf")

    @unittest.skipUnless(os.name == "posix", "hooks run under sh; executable bits are POSIX only")
    def test_the_hook_is_executable(self):
        self.assertTrue(os.access(str(HOOK), os.X_OK))

    def _run_hook(self, codes, path=None):
        """Run the hook against a stub check that exits with each of ``codes``."""
        tmp = Path(tempfile.mkdtemp(prefix="indelible-hook-"))
        try:
            subprocess.run(["git", "init", "-q", str(tmp)], check=True)
            (tmp / "dev" / "hooks").mkdir(parents=True)
            shutil.copy2(str(HOOK), str(tmp / "dev" / "hooks" / "pre-push"))
            stub = tmp / "dev" / "privacy_grep.py"
            env = dict(os.environ)
            if path is not None:
                env["PATH"] = path + os.pathsep + env.get("PATH", "")
            for code in codes:
                stub.write_text("import sys\nprint('stub check')\nsys.exit(%d)\n" % code, encoding="utf-8")
                r = subprocess.run(["sh", "dev/hooks/pre-push", "origin", "https://example.invalid/repo.git"],
                                   cwd=str(tmp), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, universal_newlines=True, env=env)
                self.assertEqual(r.returncode, code, r.stderr)
                self.assertIn("stub check", r.stdout)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)

    @unittest.skipUnless(os.name == "posix" and shutil.which("git") and shutil.which("python3"),
                         "needs sh, git and python3")
    def test_the_hook_passes_the_check_exit_code_through(self):
        # A push goes ahead only on exit 0; a hit (1) or a missing denylist (2) stops it.
        self._run_hook((0, 1, 2))

    @unittest.skipUnless(os.name == "posix" and shutil.which("git"), "needs sh and git")
    def test_a_python3_that_does_not_run_falls_back_to_py(self):
        # On Windows the python3 found on PATH can be the Store stub, which only fails:
        # the hook must try it, then use the py launcher.
        bindir = Path(tempfile.mkdtemp(prefix="indelible-bin-"))
        try:
            fake = bindir / "python3"
            fake.write_text("#!/bin/sh\necho 'Python was not found' >&2\nexit 9\n", encoding="utf-8")
            launcher = bindir / "py"
            launcher.write_text('#!/bin/sh\n[ "$1" = -3 ] && shift\nexec "%s" "$@"\n' % sys.executable,
                                encoding="utf-8")
            for p in (fake, launcher):
                p.chmod(0o755)
            self._run_hook((0, 1, 2), path=str(bindir))
        finally:
            shutil.rmtree(str(bindir), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
