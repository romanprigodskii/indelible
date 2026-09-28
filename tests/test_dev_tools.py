"""The contributor tooling in dev/: the tracked pre-push hook that runs the privacy check.

The privacy check itself needs a local, git-ignored denylist, so it can't run here.
These tests run the hook against a stub check in a throwaway git repository, and
make sure the README tells a contributor how to turn the hook on.
"""

import os
import shutil
import subprocess
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

    @unittest.skipUnless(os.name == "posix", "hooks run under sh; executable bits are POSIX only")
    def test_the_hook_is_executable(self):
        self.assertTrue(os.access(str(HOOK), os.X_OK))

    @unittest.skipUnless(os.name == "posix" and shutil.which("git") and shutil.which("python3"),
                         "needs sh, git and python3")
    def test_the_hook_passes_the_check_exit_code_through(self):
        # A push goes ahead only on exit 0; a hit (1) or a missing denylist (2) stops it.
        tmp = Path(tempfile.mkdtemp(prefix="indelible-hook-"))
        try:
            subprocess.run(["git", "init", "-q", str(tmp)], check=True)
            (tmp / "dev" / "hooks").mkdir(parents=True)
            shutil.copy2(str(HOOK), str(tmp / "dev" / "hooks" / "pre-push"))
            stub = tmp / "dev" / "privacy_grep.py"
            for code in (0, 1, 2):
                stub.write_text("import sys\nprint('stub check')\nsys.exit(%d)\n" % code, encoding="utf-8")
                r = subprocess.run(["sh", "dev/hooks/pre-push", "origin", "https://example.invalid/repo.git"],
                                   cwd=str(tmp), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, universal_newlines=True)
                self.assertEqual(r.returncode, code, r.stderr)
                self.assertIn("stub check", r.stdout)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
