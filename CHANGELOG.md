# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.4] - 2026-09-26

### Changed

- Every environment variable is read by its literal name. The workspace lookup no longer keeps a reference to the whole environment, and the Windows browser search names `PROGRAMFILES`, `PROGRAMFILES(X86)` and `LOCALAPPDATA` one by one.

## [0.1.3] - 2026-09-26

Changes from the second directory validation.

### Changed

- Child processes started by `examples/build_sample.py` and the tests get only a short, explicit list of environment variables (such as `PATH`, and `SYSTEMROOT` on Windows), never a copy of the whole environment.
- A new plugin icon: a check mark written in ink, with an ink dot.

## [0.1.2] - 2026-09-26

Changes from the first directory validation.

### Changed

- The skill no longer declares `allowed-tools`, so it pre-approves no commands. Claude Code asks before each script call until the learner adds the permission rule the README describes.

### Added

- A plugin icon (`.claude-plugin/icon.svg`).

## [0.1.1] - 2026-09-25

Documentation and packaging for the plugin directory, and the fixes found while preparing it.

### Added

- **Docs for the directory submission.** The README now covers what the plugin runs, writes and sends; example prompts; a synthetic sample workspace to try (`examples/sample-workspace/`, with its fixed clock); where it works; troubleshooting; and support and security.
- **`PRIVACY.md`,** a privacy policy: what data exists, where it lives, what is sent where, how long it is kept, how to delete it, and the protective defaults that apply if a learner says they are under 18.
- **`SECURITY.md`,** how to report a vulnerability privately, what counts, supported versions and what to expect.
- **A guard for claude.ai chat and the mobile app** in `SKILL.md`. Before any script runs, the skill checks for a folder that lasts between conversations. Without one, it says that v0.1 can't keep the record there and offers a limited manual mode. Cowork with a shared folder is described as untested.
- `displayName` in `plugin.json`, and a listing description that says v0.1 is built for Claude Code.
- **Tests** (`tests/test_examples.py`) for the sample workspace, for the browser's offline flags, and for the scripts staying inside the workspace.

### Changed

- **A headless browser that prints a PDF is kept off the network.** Chrome, Chromium and Edge used to contact their makers' services in the background as soon as they started (updates, safe-browsing lists, DNS over HTTPS), even though the page printed is a local file. Both launches, the sheet printer and `doctor`'s test print, now switch that traffic off and send anything left to a proxy address that doesn't exist, with no host name resolving. `doctor`'s fallback test print also runs without extensions.
- **The scripts write and delete only inside the workspace.** `cal ics` refuses an output path outside the workspace. `sheet new` deletes the builder's answers file only when it is inside the subject's `.indelible/tmp/`; anywhere else, it leaves the file and says so.
- `allowed-tools` no longer lists `Bash(python *indelible.py *)`, which the skill never uses. The README and `SECURITY.md` now say plainly that the remaining patterns are text patterns, broader than the one script, and give a stricter rule.
- The one-time notice before the first script call now says the script keeps the record as files on the learner's computer and sends nothing over the internet.
- The onboarding asks "Are you 18 or over?"; indelible is intended for adults, and the under-18 defaults are a safety net.
- The README describes the `CLAUDE.md` files the workspace holds, the commands Claude runs for programming subjects and for `migrate`, and what deleting one subject leaves behind in v0.1.
- For programming subjects, Claude deletes its temporary test copy of the learner's code once the marks are recorded, and says once that the learner's build tool may download declared dependencies.
- The README labels every v0.2 item as planned and not yet available.

### Fixed

- The skill and the command-line tool report version 0.1.1, matching `plugin.json` (`indelible.py --version` and the `.ics` PRODID said 0.1.0, and CI's version check failed). The sample workspace was rebuilt to match.
- Tests skip the clock-change cases when there is no time zone database (Windows without `tzdata`) instead of failing. CI installs `tzdata` on one Windows job, so those cases still run there.

## [0.1.0] - 2026-09-25

The first release. Built for Claude Code (terminal or desktop).

### Added

- **The skill.** `SKILL.md` with 14 laws, the absolute bans, a router, a command table (`teach`, `session`, `close`, `status`, `diagnose` / `mock`, `plan` / `reschedule`, `review`, `sync` and `migrate`) and a manual mode for machines without Python. Each command has a reference file, except `status`, which changes nothing in the plan or records.
- **The method, as structure.** Written backwards checks beside every answer and one closing *Least sure of: ___* line per sheet, in place of per-answer confidence flags. A 2-day recheck (44–72 hours) booked for everything taught. Mistakes on a 1-day, 3-day, 1-week and 3-week ladder, with wrong ideas fixed before they are re-tested cold. Mastery levels 0–5 computed from the record: same-day practice reaches at most level 2, and anything higher needs a cold recheck or a measurement.
- **`indelible.py`, a command-line tool** (Python 3.9+, standard library only) that is the only writer of the learner's data:
  - setup: `doctor`, `init`, `subject add`, `set`, `schema`;
  - session start: `brief` (at most 4,500 characters) and `due`;
  - the session lock, its time budget and the close checklist: `session open|status|expose|taught|override|close`;
  - sheets: specs, the sheet checker (`sheet lint`), rendering to PDF, HTML or Markdown, issuing, and evidence filing (`scan ingest`);
  - answer keys sealed apart, opened only by `key open` once an attempt is filed;
  - grading records (`grade record`), mistakes (`error ...`) and topics (`topic ...`);
  - plan blocks and their checks (`plan add|place|move|cancel|done|miss|list|week|check`);
  - calendar operations (`plan diff`, `cal ack`) and `.ics` export (`cal ics`);
  - the ledger of to-dos, decisions and Claude's own mistakes, `note append`, `stats`, `review week` and `compact`.
- **Sheet building by a builder subagent**, so answers never enter the main conversation.
- **A learner-owned workspace** of plain JSON, JSONL and Markdown files, with generated views and a `.gitignore` that keeps keys, typed answers, photos and the inbox out of version control.
- **Tests** (unittest) on macOS, Linux and Windows with Python 3.9 and 3.13, and CI.
- **Evals:** four synthetic learners (`evals/fixtures/persona-a…d.json`) and a trigger set (`evals/trigger.json`).
- **Maintainer tooling:** `dev/CONTRACT.md` (the build contract) and `dev/privacy_grep.py` (a pre-push privacy check: a local denylist, the handle allowlist, commit and tag identities, and optional text fingerprints).

### Deferred to 0.2

- Hooks declared in the skill's frontmatter.
- A claude.ai and mobile-app mode (a state file carried between chats).
- Two-way calendar sync. In 0.1, Claude proposes blocks, `plan check` validates them, and calendar changes go one way after a preview and a yes.
- A scheduling solver.
- Scheduled tasks, plugin wrapper skills, and pin/unpin.
- LaTeX sheet templates and KaTeX, a dashboard, and migration tooling in the command-line tool.
- `forget`: a command that previews exactly what it would delete and deletes only after a yes. In 0.1 the learner deletes a subject folder or the workspace themselves.
