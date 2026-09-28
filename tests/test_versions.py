"""The version is written in four places, and a release bumps them together.

They are `.claude-plugin/plugin.json` ("version"), the SKILL.md frontmatter
(metadata.version), `lib.VERSION` (printed by `indelible.py --version` and in
every .ics PRODID) and the newest released heading in CHANGELOG.md. Release
0.1.1 fixed a --version and a PRODID that still said 0.1.0, so all four are
checked here, where every test run sees them, and not only in CI.
"""

import json
import re
import unittest

try:
    from helpers import REPO_DIR, SKILL_DIR, run
except ImportError:  # run as part of the tests package
    from tests.helpers import REPO_DIR, SKILL_DIR, run

from lib import VERSION

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
SKILL_VERSION_RE = re.compile(r'^\s*version:\s*"?([^"\s]+)"?\s*$', re.M)
# The first numbered heading: an "## [Unreleased]" section above it is skipped.
RELEASE_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)


def plugin_version():
    return json.loads((REPO_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def skill_version():
    m = FRONTMATTER_RE.match((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    v = SKILL_VERSION_RE.search(m.group(1)) if m else None
    return v.group(1) if v else None


def changelog_version():
    m = RELEASE_RE.search((REPO_DIR / "CHANGELOG.md").read_text(encoding="utf-8"))
    return m.group(1) if m else None


class Versions(unittest.TestCase):
    def test_the_four_places_agree(self):
        found = {
            "plugin.json": plugin_version(),
            "SKILL.md metadata.version": skill_version(),
            "lib.VERSION": VERSION,
            "CHANGELOG.md newest release": changelog_version(),
        }
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", VERSION), VERSION)
        self.assertEqual(set(found.values()), {VERSION},
                         "the version differs between: %s" % ", ".join("%s %s" % kv for kv in found.items()))

    def test_the_cli_prints_it(self):
        r = run(["--version"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "indelible " + VERSION)


if __name__ == "__main__":
    unittest.main()
