# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Only the session-open brief counts an open.** Every `ind brief <s>` used to count one for the "not taken after 2 opens" rule and write `data/sheets.jsonl`, so two status looks a few hours apart could bring "Sit them now, or drop that sheet?". `ind brief` now writes nothing; `ind brief <s> --open`, run in session-open step 1, counts. The flag reads "not taken after 2 sessions". Status really changes nothing, as the README says.
- **`topics.json` no longer stores `cold_passes`.** The list was filled by any sitting at 75% or more, including one-question, out-of-window and practice sittings that the level rules reject, and nothing read it. Cold passes are found in `attempts.jsonl` by the level rules, and `level_basis` names the one that counts. An older workspace's list is left as it is and ignored. The sample workspace was rebuilt.

### Added

- **`ind session extend <s> --min N` records the one extension.** Nothing recorded an extension, so during one `session status` printed "closing time" at every check, a second extension could be offered, and after a context compaction the extension was forgotten. The command writes it to the lock, moves the close start, and refuses a second one or one over min(`session.extension_max_min`, a quarter of the planned minutes). `session status` shows "extension until HH:MM", and the overrun still counts the extension. `close.md` §2 runs it on a yes.
- **Session facts are written when they happen.** A new `SKILL.md` file-contract line: a promise goes to `ledger add owed` as it is made, an extension to `session extend`, a chat explanation to `session expose`, and a discussed sealed question to its contamination defect, at once. After a compaction, Claude rebuilds the state from `session status` and the open to-dos. The close checks the promises' to-dos rather than writing them from memory.

### Fixed

- **Sheets on one block are sized together.** L5 and `sheet issue` measured each sheet alone against 0.8 × its block, so two 35-minute sheets were issued into one 60-minute block. Now the est_min of every other sheet on the block that is not void (graded ones too) is taken off, and the basis names them ("less 35 min on ielts-x-01"). When the open session runs on that block and its planned minutes (with the extension) are longer, they count instead, since a slot split into a recheck block and a session block is one session. A recheck linted against the session's remaining minutes could be refused at issue against its own 15-minute block: `session-open.md`, `plan.md` and `sheets.md` now issue every sheet of a session, the recheck included, against the session block (grading still finds the recheck block by topic and window), and `builder.md` no longer says BLOCK is "for the budget only".
- **A measuring sheet keeps to its own minutes.** L5 passed every diagnostic, mock and checkpoint ("sized by the exam clock") and ignored even an explicit `--budget-min`, and `sheet issue` skipped them too, so a 90-minute diagnostic could be issued into a 60-minute block, turning unreached questions into apparent gaps. Both now hold a measurement to `--budget-min`, else its block's minutes less the 10 kept for recording (`measure.md` §4), else, for a mock or checkpoint, the exam's own minutes. Over budget, the message says to split a part into sittings or book a longer block, never to cut questions; the builder returns FAILED rather than cutting. The pace floor applies to measurements too.
- **Lint no longer takes the sheet's estimate on trust.** L5 compared `est_min` with the budget, but `est_min` is written by the builder whose sizing the rule exists to check, so a sheet of 6 reading questions marked "1 min" passed a 2-minute budget. L5 now works out the builder's own formula again (each question's `pace_s[layer]`, over 60, plus 1 minute, from the subject's pace) and fails a lower estimate, even when no budget is known. Triage sheets are exempt. `builder.md` says so, and adds that a question needing several written results gives each its own box, so the estimate counts the work, not the items.
- **"Sick till Monday" no longer dead-ends on a recheck.** When sick days covered a recheck's whole window, `plan check` said to move it to another day, `plan move` refused (outside its window), and the recipe said not to cancel. For a recheck, `plan check` now says "move it inside its window (…)", or, when no time is left in it, to cancel it, add a to-do and apply the late-recheck rule at the first session back. `plan.md` §11 gives those steps, a to-do that names the block but never its topic, the preview line, and the re-baseline when slack drops below zero.
- **A 2-day recheck that lapses is no longer lost.** A recheck skipped in a session (an allowed override), or an on-demand learner's recheck whose window passed before the next session, vanished: the brief, `due --list` and the close said nothing, so the late-recheck rule never ran and the topic stalled below mastery 3. The brief now flags it without naming its topic ("a 2-day recheck's window has passed"; LATE RECHECK below the line names it), `due --list` lists it as tier 0, and `plan check` calls the late recheck `[measured]`, as `plan.md` does, not `[practice]`. A new close check, C9, fails when a recheck booked in the session's time was not sat while its window is still open, and prints the `plan move` that fixes it; the close no longer marks a recheck block done, since only grading closes one. `session-open.md` moves a skipped recheck inside its window, and `plan.md` §7 logs the feedback given at marking as a review exposure (a measuring sheet logs none).
- **Drills on a later day move the 2-day recheck window.** The window counts from the last warm exposure (the contract, lint L7, `ind due` and the level rules all say so), but the window `session taught` stored kept counting from the teach. With drills a day later, `plan check` asked for a time that `plan place` and `plan move` refused. `session expose` now moves the open recheck of a topic still waiting for its first recheck to 44–72 h after the exposure, prints the new window, and names a placed recheck left outside it. `session-teach.md` says so, in place of "24 hours clear of the drills".
- **A recheck sent the next morning keeps its real sitting time.** With the Start and Stop lines blank, or the photo filed on a later day without `--date`, the filing day and the marking time stood in for the sitting, so a recheck sat inside its window could be recorded outside it, lose its level 3 and still use up the first recheck. Without `--date`, `scan ingest` and `sheet sat` now refuse a recheck, or a sheet with mistakes re-served, that was issued on an earlier day (any other sheet keeps today, with a note). `grade record` no longer guesses the time of such a sheet unless it was issued today and is marked within max(3 h, 3 × its minutes); it asks for `date` and `start`. The warning from `sheet sat` uses the same fallback as grading.
- **A recheck near the end of its window says so.** RECHECK NOW rounded 71.5 h up to "72 h" and gave no closing time, so a recheck built at the open and started half an hour later could fall outside its window: the pass then counted for nothing, silently, and still used up the first recheck. RECHECK NOW and `due --list` now cut the hours (71.5 h reads 71 h) and give the time the window closes, with `CLOSING` inside 30 minutes (`closes_at` in `due --json`). `sheet issue` prints "Start by <time>" for each topic of a recheck, and `grade record` prints "Not counted toward level 3 … treat it as a late recheck" when a first recheck was started outside its window. `session-open.md` builds a closing recheck first.
- **Practice no longer uses up a 2-day recheck.** A `cold:<topic>` item on a mixed or other practice sheet closed the topic's recheck at marking and set it as served cold, so the real recheck was never offered again. Now only a measuring sheet (a `cold` sheet, or a `words` recheck) closes a booking; on practice, a note says the recheck stays open.
- **A mistake re-served on a warm topic makes no ladder move on any sheet.** On a mixed or measuring sheet, a mistake whose topic was seen in the 24 hours before the sitting now gets the "not counted" note, as on a cold sheet. The rows still count as practice or measurement toward levels.
- **Lint L7 checks mixed sheets too.** Their `error:` and `sentinel:` items must be due (for `error:`) and not seen in the last 24 hours, and a `cold:` item on a mixed sheet fails: the 2-day recheck is a `cold` sheet.
- **A repair says when the mistake can come back.** `error repair` promised a recheck "at least 12 h after the fix", but the repair is logged as an exposure, so the 24-hour rule holds it back for a day. It now names the earliest time. The brief's BELIEFS DUE and OTHER DUE lines add "not now: <reason>" to a mistake that can't be served yet, as `due --list` does, and `session-teach.md` says 24 hours.
- **With technical vocabulary, the brief no longer names the recheck topics above the line.** DUE gave the topic ids of the 2-day rechecks ready now, and NOW/NEXT the topics of a recheck to book, in the part that may be read aloud. Both now give a count or a time only, as in plain words; the topics stay in RECHECK NOW below the line.
- **A failure-gate photo opens only its own questions.** The photo of items 1–3 sent at a drills block's failure gate was filed like the finished sheet: it marked the sheet taken, and `key open` then printed the whole key into the conversation, answers to the questions still being worked included. `scan ingest --asks 1a,2a,3a` now files a gate photo: the sheet stays issued, `key open` prints only those questions (and says so) until the finished sheet is filed, and `grade record` waits for the whole sheet. Each line of `.indelible/keys/opened.jsonl` now names the questions it printed. `session-teach.md`, `session-grade.md` and `sheets.md` say so, and the sample workspace was rebuilt.
- **A second typed file no longer replaces the first.** `scan ingest --typed` always wrote `answers/<id>.txt`, so the finished sheet's file overwrote the gate photo's, and both evidence entries pointed at the same file. Each typed filing now gets its own file (`answers/<id>-2.txt`, and so on).
- **A second chat no longer walks into a running session blind.** A learner who opened a new conversation mid-session got only "Carry on": the new chat didn't know which sheets were out, and could issue a second recheck on a topic already out. `session status` now adds a "sheets out" line (issued or taken, not graded yet: id, type and issue time, never a recheck's topics). `sheet issue` refuses a cold or mixed sheet that serves a recheck or mistake another such sheet, not graded yet, already serves, and names that sheet. In `session-open.md` step 4, Claude reads the status and the open to-dos before building anything, and asks the learner to send photos to this chat from now on.
- **`cal ics` writes only `plan/ics/<name>.ics`.** Before, any path inside the workspace was accepted, so a wrong path could overwrite `data/attempts.jsonl` or a sealed key with no backup. Any other place, or a name without `.ics`, is now refused (exit 2) and nothing is written, as the README says.

## [0.1.5] - 2026-09-28

The learner is never sent to find their own mistake.

### Changed

- **Marking points to the error, and the learner makes the fix.** The account asked for each miss is now how the learner got their answer (`1) I did it this way: ___  2) a word stopped me  3) I guessed  4) I can see my slip: ___`), not "what happened?". On a topic met that day, "what happened?" asked them to find an error they couldn't see. Claude then names the question and the step, and asks once for the corrected line. A slip whose fix doesn't come is treated as a wrong idea, and a wrong idea gets its fix sheet. Law 11 and a new ban in `SKILL.md` say so, and "one of these is wrong: find it" is gone for good. Method rule R42 and `method.md` §5 give the reasons (Große & Renkl, 2007; Baars et al., 2014).
- **Careless needs more than a named rule.** Naming the right method counts as a slip account only when the learner writes the corrected line unaided once the step is pointed to. The same operation must also be done right, unaided, elsewhere (never the worked items 1–2 of a first drill). A guess not forced by time becomes the wrong idea "no method yet for …", and its fix sheet gives a second worked case in place of the contrast.
- **A failed check is a flag, not a hunt.** The rules box on sheets with check lines now says: "If a check fails and you can't see why within a minute, keep your answer, put its number on the Least-sure line and go on: I'll show you where at marking."
- **Checks on a new topic are ones the learner can run.** A theory or fix sheet's worked case now ends with its check, worked as a step. So does item 1 of a first drill block, which covers textbook pages. The drills' check hints name that check. "Another way" and "the weakest step" wait until a topic reaches mastery 3, because a new learner has one method and no sense yet of where they are weak. Rechecks give only the form of a check, never a topic's own method, so the check doesn't label the question.
- **"Which line is the first wrong one?" and "find the error" items** appear only on topics the learner owns, or where finding errors is the exam's own question form. Below that, the wrong working sits beside the right one. A mock's miss-review asks why the learner chose their answer, and asks for the answer now only after Claude has pointed to the line or step.
- The sample workspace was rebuilt: the new rules-box line, and the `.ics` PRODID now carries the current version.

### Added

- **Sheet checker rules.** L10 (fails): a check hint that asks for a search ("find your mistake", "check your work for mistakes"), a re-solve ("redo", "double-check") or a confidence rating, or says only "check your answer". Subject words such as "the standard error", "error bars" or "the error message" pass. W3 (warns): on a topic below mastery 3, a check line with no hint, or one that needs a second method or the weakest step. W4 (warns): a theory or repair sheet whose worked case has no "Check:" step.

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
