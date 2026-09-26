# indelible

**Learning that survives the cold test.**

`indelible` is a skill for Claude that runs your self-study like a strict, organised tutor. It interviews you once, plans backwards from your deadline, puts sessions in your calendar, teaches from sheets you read and then close, drills you on paper, re-tests everything cold two days later, and keeps an honest record of what you actually know.

> **Status: v0.1 (early; built for Claude Code).** Expect rough edges, and please report them.

## The method

1. **Read it, then close it.** Theory comes on a sheet you read and put away before the drills. An explanation left in view turns a test into a lookup.
2. **One thing at a time, then all mixed up.** Teaching drills come in blocks of one question type. Anything that measures is unlabelled and interleaved, like the real exam.
3. **Nothing counts until it survives 48 hours.** Every new skill comes back cold two days later, on fresh problems. Same-day scores don't count.
4. **Check backwards, in writing.** Beside every answer, write one check that runs the other way: put the answer back into the question, rebuild the total, or test the definition you used against what the question actually says. Re-solving in your head replays the same slip; a written check catches it. Each sheet ends with a single line, *Least sure of: ___*. There is no confidence flag on every answer: people stop filling it in, and doubt tends to fire on arithmetic while the costly mistakes are confident misreadings of a definition.
5. **Every miss goes in the error log** and returns after 1 day, 3 days, 1 week and 3 weeks.
6. **You do the work.** You get the smallest hint that unblocks you and never an answer you could reach yourself. Explaining a concept back is the real test.

## Where it works

| Where | In v0.1 |
|---|---|
| **Claude Code** (terminal, desktop app, IDE extensions) | Supported. v0.1 is built for Claude Code. |
| **Cowork** | Should work when a folder on your computer is shared with it (your study folder goes inside that folder), but untested in v0.1. |
| **claude.ai chat and the Claude mobile app** | Not supported in v0.1, because files don't persist between chats there. The skill says so and offers a limited manual mode: sheets and a record that you save yourself and paste back next time, with every number marked *unverified*. Full support is planned for v0.2 and isn't available yet. |

The full mode needs Python 3.9 or later on the computer where Claude runs its commands (see Requirements below).

## Install

In Claude Code, add the plugin:

```
claude plugin marketplace add romanprigodskii/indelible
claude plugin install indelible@indelible
```

Or copy the `skills/indelible` folder from this repository into `~/.claude/skills/` (on Windows, `%USERPROFILE%\.claude\skills\`), so that you end up with `~/.claude/skills/indelible/SKILL.md`.

**Requirements**

- Python 3.9 or later. The scripts use the standard library only, so there is nothing to `pip install`.
- Optional, for PDF sheets: [typst](https://typst.app), or Chrome, Chromium or Edge. Without either, sheets come as HTML or Markdown. The skill checks what you have during setup.

**One permission rule (optional).** A session runs many small script calls. So that Claude Code doesn't ask about each one, you can allow this rule once with `/permissions`:

```
Bash(python3 *indelible.py*)
```

On Windows, the launcher is `py -3`, so the rule is `Bash(py -3 *indelible.py*)`.

- **What the rule allows.** It is a text pattern, not a check on which file runs: it allows any `python3` command that mentions `indelible.py`, including one that runs other code first. The skill itself pre-approves nothing: until you add a rule, Claude Code asks before each script call.
- **A stricter rule,** if you prefer one: in place of `python3 *indelible.py`, write the start of the command exactly as Claude Code's permission prompt shows it, with the script's full path (and quotes, if the prompt has them), for example `Bash(python3 /full/path/to/skills/indelible/scripts/indelible.py*)`. If prompts still appear, compare the rule with the prompt. A plugin install keeps the script in a folder that can change when the plugin updates, so you may need to update the rule then.
- **You stay in charge.** The skill only suggests the rule: you add it yourself, and nothing changes your settings for you. What the script reads and writes is listed under [What it runs, writes and sends](#what-it-runs-writes-and-sends).

## Example prompts

Say what you want in plain words. These examples come from the made-up learners in `evals/fixtures/`.

| You say | What happens |
|---|---|
| "I need a 7.5 in IELTS Academic by December for my master's offer. Can you set me up and keep me honest?" | **Setup.** Up to eight short questions, a two-week plan to check and a one-screen summary. Nothing is written until you say yes. Week 1 opens with a diagnostic: nothing is taught until it's marked. |
| "teach me rust I guess. please don't ask me a million questions" | **Express setup.** Three questions, then a plan; everything else takes a default you can change later. |
| "start ielts" or "What's due today?" | **A session.** The 2-day recheck first, then mistakes that are due, then new material and drills, then marking and the close. |
| "Here are the photos of this morning's drill sheet." | **Marking.** The photos are filed first, and only then is the answer key opened. For each miss you give your account, and it goes in the error log with a date to come back. |
| "I missed Thursday's session." | **Reschedule.** The plan is repaired and checked, the 2-day recheck is always rebooked, and you see the changes before anything goes to your calendar. If you say no, the sessions it added are cancelled and it asks what would work instead. |
| "Put my study blocks in my calendar." | **Sync.** A preview of what will be added, moved or cancelled, written only after your yes, then read back. Without a calendar connector you get an `.ics` file. |
| "Weekly review" | **Review.** The week's numbers, each labelled (such as *measured* or *practice*), ending in one to three decisions. |
| "Where am I?" | **Status.** What's due, your week and your numbers. It changes nothing. |

## Try it with sample data

[`examples/sample-workspace/`](examples/sample-workspace/) is a study folder for a made-up learner, ready to use: a graded diagnostic, open mistakes and a planned week. Everything in it is synthetic, the answer keys included.

1. Install the plugin (above). The sample isn't part of the installed plugin, so also clone or download this repository.
2. Copy `examples/sample-workspace` somewhere else, because a session writes to the folder.
3. The sample has a fixed clock, Thursday 15 October 2026, 07:00 in Lisbon. In the terminal where you'll start Claude Code, set it first: `export INDELIBLE_NOW=2026-10-15T07:00+01:00` (in PowerShell: `$env:INDELIBLE_NOW = "2026-10-15T07:00+01:00"`). Without it, the dates follow your computer's clock and don't line up with the sample's story.
4. Open Claude Code in the copy.
5. Say "status" for a look that changes nothing, or "what's due?" to start a session.

[`examples/README.md`](examples/README.md#try-it) has the exact commands, what the sample holds and what to expect.

## Commands

You don't need to learn these: say what you want in plain words. You can also type `/indelible` followed by a command (`/indelible:indelible` when installed as a plugin).

| Command | Say something like | What it does |
|---|---|---|
| `teach` | "set me up for…", "add chemistry" | A short interview: your goal, date, level, materials, session length, days and times, and calendar. A second subject gets a shorter re-run. |
| `session` (the default) | "start", "let's go", "what's due", "I have 15 minutes" | A full study session: the 2-day recheck first, then mistakes that are due, then new material and drills, then marking. |
| `close` | "done", "gotta go", "wrap up" | The close checklist: your work filed and marked, mistakes logged, rechecks booked and files updated before you leave. |
| `status` | "where am I", "this week", "what do you keep?" | A look at what's due, your week and your numbers. It changes nothing in your plan or records. |
| `diagnose` · `mock` | "test me properly", "full mock" | A measurement with no teaching: unlabelled, timed and scored. |
| `plan` · `reschedule` | "plan my week", "I missed Thursday", "sick till Monday" | Builds or repairs your plan and checks it against your sleep and commitments, then shows it to you. Nothing goes to your calendar before your yes; if you say no, the sessions it added are cancelled. |
| `review` | "weekly review", "how am I doing" | The weekly review, ending in one to three decisions. |
| `sync` | "put it in my calendar", "fix my calendar" | Shows the calendar changes, makes them only after your yes, then reads them back. |
| `migrate` | "use my existing notes" | Imports a study system you've been running by hand, without losing anything. In v0.1 this is a guided procedure rather than a script command (see [What it runs](#what-it-runs-writes-and-sends)). |

A `forget` command, which would show exactly what it deletes and delete it only after your yes, is planned for v0.2 and isn't available yet.

## How a week looks

An example with a made-up learner: preparing for IELTS Academic 7.5 by 12 December, Portuguese first language, 60-minute sessions before work on Monday, Tuesday and Thursday, and on Saturday mornings.

- **Setup, about 8 minutes.** She says "set me up for IELTS". Claude asks up to eight short questions, one at a time, each with a default she can take by saying "skip". Then it shows a two-week plan and asks whether the blocks should go in her calendar. Nothing is written until she says yes to a one-screen summary.
- **Week 1 opens with the diagnostic: nothing is taught until it's marked.** On Monday, part A: a mixed, unlabelled test on paper. A part B follows only for the topics where part A went well, and the results open with what she already knows. Every number carries a label, such as *measured* or *practice*. Teaching starts once the diagnostic is marked: with no part B needed, as in the [sample](examples/README.md), her first new skill comes on Tuesday; with a part B, later in the week.

A typical week from then on:

- **Tuesday: a new skill.** A theory sheet she reads and then closes. Drills on paper, in blocks of one question type, with a written check beside every answer and *Least sure of: ___* at the end. She sends phone photos; they are filed before anything is marked. For each miss she gives her account first, and the miss goes into the error log with a date to come back.
- **Thursday: the 2-day recheck opens the session.** Fresh questions on Tuesday's skill, cold, with nothing reviewed in the 24 hours before. Then the next skill.
- **Every session ends with the close,** inside the session. Anything she can't finish becomes a dated to-do rather than a vague "later".
- **Calendar.** Blocks appear in her calendar only after she has seen the changes and said yes. When she writes "I missed Thursday", the plan is repaired, and the 2-day recheck is always rebooked.
- **Sunday is her rest day.** At the end of the week, a short review ends in one to three decisions.

## Your data

- **Plain files in a folder you choose.** Everything is kept as JSON, JSONL and Markdown files that you can open. Nothing is stored inside the skill's own folder.
- **Nothing leaves your machine except what you approve for your calendar.** The scripts make no network calls, and a browser they start to print PDF sheets runs with its network access blocked. Calendar events are written only after you've seen them and said yes, unless you chose to let Claude move a missed session within 24 hours. For programming subjects, your own build tool may download your project's declared dependencies when Claude runs your tests. (Your conversation with Claude is handled like any other Claude Code conversation.) Details: [PRIVACY.md](PRIVACY.md).
- **Answer keys stay hidden until you've attempted a sheet.** Keys are sealed in a separate folder when a sheet is built, and they open only after your attempt (a photo or your typed answers) is filed.
- **Deleting.** Your record is plain files in one folder, and deleting that folder removes it all. Deleting just one subject's folder removes most of that subject, but in v0.1 some traces stay in shared files; [PRIVACY.md](PRIVACY.md#deleting-your-data) explains. The scripts never delete your data on their own. A `forget` command that previews what it removes is planned for v0.2 and isn't available yet.
- **Optional local history.** You can keep the folder under git; the `.gitignore` it comes with keeps answer keys, your answers, photos of your work and the inbox out of it.

## What it runs, writes and sends

Everything the plugin's scripts do is readable source in this repository, and the plugin downloads and installs nothing while it runs. Beyond the scripts, Claude runs a few commands that the skill's instructions spell out; they are listed below too. In Claude Code's default permission mode, you are asked before any command that no permission rule allows.

**What it runs**

- **Its own Python scripts:** `skills/indelible/scripts/indelible.py` and the `lib/` folder beside it, standard library only.
- **Optional programs, only if they are already on your computer:**
  - `typst`, to make PDF sheets.
  - Otherwise, an installed Chrome, Chromium or Edge in headless mode, to print a sheet to PDF. It runs with a throwaway profile that is deleted afterwards and a mock keychain, so it never touches your saved passwords or your system keychain. Its network access is blocked: its background services (updates, sync, safe-browsing lists) are switched off, all its traffic goes to a proxy address that doesn't exist, and no host name resolves. The page it prints is a local file with no external fonts, scripts or images. (When run as root on Linux, as in a container, it adds the `--no-sandbox` flag that Chromium needs there.)
  - `sips` (built into macOS) or `heif-convert` (elsewhere, if installed), to turn iPhone HEIC photos into JPEG.
  - When `doctor` checks your setup, it makes a one-page test PDF with typst and with the browser, if it finds them, in a temporary folder that it then deletes.
- **Inside Claude:** a helper agent (a subagent) writes each practice sheet and its answer key to files, so the answers never pass through your chat. If you choose local history at setup, Claude runs `git init` in your study folder and never adds a remote.
- **Programming subjects only:** to mark your code, Claude copies your files to a temporary folder, adds the hidden tests and runs them with your own compiler or test tool (for example `cargo test`) under a 60-second limit. When the helper agent builds a programming sheet, it runs its own reference solution and tests the same way, in a temporary folder of its own, to check the answer key. Your project is never changed. Your tool may download the dependencies your project declares, as it would if you ran it yourself.
- **`migrate` (importing a study folder you've been running by hand):** v0.1 has no script command for it. Claude runs two short Python programs written out in [`references/migrate.md`](skills/indelible/references/migrate.md): one copies the files you name into your study folder and records a SHA-256 hash of each, and one checks the copies against those hashes. To read a mistakes file that also holds the right answers, Claude writes a few lines of Python that print it with the answers replaced by `[hidden]`. Your original folder is only read, never changed.

**What it writes**

- **Your study folder.** Your record lives here, and the scripts refuse to put it inside the skill's own folder. They write files only inside it (the exceptions are listed below): for example, a calendar `.ics` file goes in its `plan/ics/` folder, and the scripts refuse any other place.
- **`CLAUDE.md` files,** one at the top of your study folder and one in each subject's folder. Claude Code reads a `CLAUDE.md` automatically, as instructions, whenever it is opened in that folder.
  - They tell Claude that the folder is a study folder, to use the indelible skill and start with its brief, and to keep out of the sealed answer keys. They also hold your own notes, which Claude adds from what you tell it.
  - The scripts create one only where none exists. After that, they change only the part between the `indelible:begin` and `indelible:end` markers, each time the summaries are refreshed. If your study folder already had a `CLAUDE.md`, your text stays as it is and that marked part is added at the end.
  - The brief reads your notes back from each subject's `CLAUDE.md`. The scripts read no other `CLAUDE.md`: nothing in `~/.claude`, and nothing in your other projects. (When you ask to import a study folder you've been running by hand, Claude reads that folder's own `CLAUDE.md` as part of the import.)
  - The top-level one names the full path of the script, so a Claude session without the skill can still run the brief. That path can go out of date when the plugin updates; the skill itself doesn't depend on it.
- **A one-line pointer file, `~/.indelible/workspace`,** holding your study folder's path, so Claude can find it from any folder. Setup writes it (`indelible.py init --pointer`) after you say yes to the setup summary. You can delete it; Claude then finds your study folder when you open Claude in it.
- **Temporary files** in your computer's temp folder:
  - the browser's throwaway profile while it prints a sheet, and `doctor`'s test PDFs, both deleted straight away by the scripts;
  - for programming subjects, the copy of your code that Claude tests, which Claude deletes once the marks are recorded, and the helper agent's own test folder, which holds its reference solution (part of the answer key) and none of your data. v0.1's instructions don't yet tell it to delete that folder.
- **Python's usual compiled-code cache** (`__pycache__`) beside the scripts. It holds none of your data.
- **Files you hand over** (photos, PDFs, typed answers, or a project folder for programming practice) are read where they are and copied into your study folder. The originals are never changed or deleted.

**What it sends**

- **Nothing, from the scripts.** They make no network requests: there is no `urllib`, `http`, `requests` or similar in them. The only use of Python's `socket` module is reading your computer's name for the study folder's write lock. A browser they start to print a PDF has its network access blocked (see [What it runs](#what-it-runs-writes-and-sends)). There are no analytics, no telemetry and no update checks, and nothing is sent to the author.
- **Your calendar,** only through a calendar connector you have added to Claude yourself, and only if you choose it at setup. Claude shows you the changes and writes them only after your yes (or, if you choose that option, moves a missed session within 24 hours and tells you afterwards), then reads back what it wrote. With your yes, it may also read your busy times for the next 14 days to find free slots. Without a connector, you get a local `.ics` file to import yourself.
- **Your conversation** with Claude is processed as usual, under your agreement with Anthropic.

**What it never does**

- It never edits Claude's settings or permissions, and it pre-approves no commands (it declares no `allowed-tools`). If Claude Code asks before each script call, the skill suggests the permission rule under [Install](#install), for you to add yourself.

## Honest limits

- **A skill can't physically stop the model** from breaking one of its own rules. So the rules that matter most don't rely on instructions alone. Three structural safeguards do the work:
  1. The only route to a printable sheet runs the sheet checker, which refuses sheets that break the method.
  2. The only route to an answer key requires your attempt to be filed first.
  3. The next session start detects anything the previous session skipped, and does it first.
- **v0.1 is built for Claude Code** (see [Where it works](#where-it-works)). Full claude.ai and mobile support, hooks and two-way calendar sync are planned for v0.2 and aren't available yet. Until then, if you move a block in your calendar app, tell Claude so the plan can be updated.
- **Claude writes most practice items, and it can get one wrong.** If you think a mark is wrong, say so: the record (your photo and the key) is checked before the mark is kept or changed.
- **The principles come from well-studied effects:** retrieval practice (Roediger & Karpicke, 2006), spacing (Cepeda et al., 2006) and interleaving (Rohrer & Taylor, 2007); see also Dunlosky et al. (2013). The specific numbers, such as the 48-hour recheck and six questions per block, are defaults that were field-tested, not results of a controlled study. You can change them.

## Troubleshooting

- **"Python not found" or "too old".** The scripts need Python 3.9 or later. Install it from [python.org](https://www.python.org/downloads/) or your package manager, then ask Claude to check your setup again. On Windows, use the Python launcher, `py -3`, which the python.org installer adds; if `python3` opens the Microsoft Store or isn't found, that's expected, and the skill uses `py -3`. Without Python, the skill offers a manual mode, but nothing then enforces its rules.
- **A permission prompt before every script call.** Allow the rule under [Install](#install) with `/permissions`: `Bash(python3 *indelible.py*)`, or `Bash(py -3 *indelible.py*)` on Windows. Read what it allows first; [Install](#install) also gives a stricter version.
- **No PDFs.** `doctor` lists each PDF tool it found and whether its test page worked. Without a working one, sheets come as HTML (read it on screen, or print it from a browser) or Markdown, and everything else works the same. For PDFs, install [typst](https://typst.app) (or Chrome, Chromium or Edge), then ask Claude to check your setup again.
- **Windows: `doctor` warns that your time zone can't be loaded.** Windows has no built-in time zone database, so times follow the computer's own zone instead of the one set for your study. Install the database with `py -3 -m pip install tzdata` (you run this yourself; it downloads the `tzdata` package from PyPI).
- **Your calendar isn't detected.** Claude only looks at the connectors you have added. Connect your calendar in Claude's settings (under Connectors), then say "sync my calendar". Or choose the `.ics` file and import it into your calendar app.
- **A session was left open.** Nothing is lost. The next session start closes it first (in 10 minutes at most), logs the close as late, then carries on.
- **"No indelible workspace found."** Open Claude in your study folder (for example `~/Study`) and try again.
- **Anything else:** open an issue in this repository's [Issues tab][issues] with what you said, what happened, your operating system and Python version, and `doctor`'s output if it's relevant. The repository is public, so leave out your study files and personal details.

## Support and security

- **Help and bug reports:** the [Issues tab][issues] of this repository on GitHub.
- **Security problems:** please report them privately, as described in [SECURITY.md](SECURITY.md).
- **Privacy:** [PRIVACY.md](PRIVACY.md) explains what data exists, where it lives and how to delete it.

indelible is an independent open-source project. It is not made, endorsed or supported by Anthropic.

[issues]: ../../issues

## Contributing

- **Tests:** `python3 -m unittest discover -s tests` (Python 3.9+, standard library only). CI runs them on macOS, Linux and Windows.
- **Privacy rule:** every example, fixture, test and issue uses only the synthetic learners A–D in `evals/fixtures/`. Never add real learner data, even your own. Before a push, run `python3 dev/privacy_grep.py` (it needs a local, git-ignored denylist; it also checks commit author names and emails).
- **Build contract:** file formats, commands and checker rules are defined in `dev/CONTRACT.md`. Where code and the contract disagree, open an issue.
- **Trigger evals:** `evals/trigger.json` lists prompts that should and shouldn't start the skill.

## License

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.

Designed and field-tested by [@romanprigodskii](https://github.com/romanprigodskii). Written with Claude.
