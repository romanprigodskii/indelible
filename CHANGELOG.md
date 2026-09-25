# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

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
