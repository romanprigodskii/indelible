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

**One permission rule.** A session runs many small script calls. So that Claude Code doesn't ask about each one, allow this rule once with `/permissions`:

```
Bash(python3 *indelible.py *)
```

On Windows, the launcher is `py -3`, so the rule is `Bash(py -3 *indelible.py *)`. The script only reads and writes files in your study folder.

## Commands

You don't need to learn these: say what you want in plain words. You can also type `/indelible` followed by a command (`/indelible:indelible` when installed as a plugin).

| Command | Say something like | What it does |
|---|---|---|
| `teach` | "set me up for…", "add chemistry" | A short interview: your goal, date, level, materials, session length, days and times, and calendar. A second subject gets a shorter re-run. |
| `session` (the default) | "start", "let's go", "what's due", "I have 15 minutes" | A full study session: the 2-day recheck first, then mistakes that are due, then new material and drills, then marking. |
| `close` | "done", "gotta go", "wrap up" | The close checklist: your work filed and marked, mistakes logged, rechecks booked and files updated before you leave. |
| `status` | "where am I", "this week", "what do you keep?" | A look at what's due, your week and your numbers. It changes nothing in your plan or records. |
| `diagnose` · `mock` | "test me properly", "full mock" | A measurement with no teaching: unlabelled, timed and scored. |
| `plan` · `reschedule` | "plan my week", "I missed Thursday", "sick till Monday" | Builds or repairs your plan, checks it against your sleep and commitments, shows it to you, then saves it. |
| `review` | "weekly review", "how am I doing" | The weekly review, ending in one to three decisions. |
| `sync` | "put it in my calendar", "fix my calendar" | Shows the calendar changes, makes them only after your yes, then reads them back. |
| `migrate` | "use my existing notes" | Imports a study system you've been running by hand, without losing anything. |

A `forget` command, which shows exactly what would be deleted and deletes it only after your yes, comes in v0.2.

## How a week looks

An example with a made-up learner: preparing for IELTS Academic 7.5 by 12 December, Portuguese first language, 60-minute sessions before work on Monday, Tuesday and Thursday, and on Saturday mornings.

- **Setup, about 8 minutes.** She says "set me up for IELTS". Claude asks up to eight short questions, one at a time, each with a default she can take by saying "skip". Then it shows a two-week plan and asks whether the blocks should go in her calendar. Nothing is written until she says yes to a one-screen summary.
- **Week 1: the diagnostic.** No teaching yet. On Monday and Tuesday, a mixed, unlabelled test on paper, in two parts; on Thursday, results that open with what she already knows. Every number carries a label, such as *measured* or *practice*.

A typical week after that:

- **Tuesday: a new skill.** A theory sheet she reads and then closes. Drills on paper, in blocks of one question type, with a written check beside every answer and *Least sure of: ___* at the end. She sends phone photos; they are filed before anything is marked. For each miss she gives her account first, and the miss goes into the error log with a date to come back.
- **Thursday: the 2-day recheck opens the session.** Fresh questions on Tuesday's skill, cold, with nothing reviewed in the 24 hours before. Then the next skill.
- **Every session ends with the close,** inside the session. Anything she can't finish becomes a dated to-do rather than a vague "later".
- **Calendar.** Blocks appear in her calendar only after she has seen the changes and said yes. When she writes "I missed Thursday", the plan is repaired, and the 2-day recheck is always rebooked.
- **Sunday is her rest day.** At the end of the week, a short review ends in one to three decisions.

## Your data

- **Plain files in a folder you choose.** Everything is kept as JSON, JSONL and Markdown files that you can open. Nothing is stored inside the skill's own folder.
- **Nothing leaves your machine except what you approve for your calendar.** The scripts make no network calls; calendar events are written only after you've seen them and said yes. (Your conversation with Claude is handled like any other Claude Code conversation.)
- **Answer keys stay hidden until you've attempted a sheet.** Keys are sealed in a separate folder when a sheet is built, and they open only after your attempt (a photo or your typed answers) is filed.
- **Deleting.** Your record is plain files in one folder: delete a subject's folder, or the whole folder, whenever you like. The scripts never delete your data on their own, and a `forget` command that previews what it removes comes in v0.2.
- **Optional local history.** You can keep the folder under git; the `.gitignore` it comes with keeps answer keys, your answers, photos of your work and the inbox out of it.

## Honest limits

- **A skill can't physically stop the model** from breaking one of its own rules. So the rules that matter most don't rely on instructions alone. Three structural safeguards do the work:
  1. The only route to a printable sheet runs the sheet checker, which refuses sheets that break the method.
  2. The only route to an answer key requires your attempt to be filed first.
  3. The next session start detects anything the previous session skipped, and does it first.
- **v0.1 is for Claude Code only** (terminal or desktop). A claude.ai and mobile mode, hooks, and two-way calendar sync come in v0.2. Until then, if you move a block in your calendar app, tell Claude so the plan can be updated.
- **Claude writes most practice items, and it can get one wrong.** If you think a mark is wrong, say so: the record (your photo and the key) is checked before the mark is kept or changed.
- **The principles come from well-studied effects:** retrieval practice (Roediger & Karpicke, 2006), spacing (Cepeda et al., 2006) and interleaving (Rohrer & Taylor, 2007); see also Dunlosky et al. (2013). The specific numbers, such as the 48-hour recheck and six questions per block, are defaults that were field-tested, not results of a controlled study. You can change them.

## Contributing

- **Tests:** `python3 -m unittest discover -s tests` (Python 3.9+, standard library only). CI runs them on macOS, Linux and Windows.
- **Privacy rule:** every example, fixture, test and issue uses only the synthetic learners A–D in `evals/fixtures/`. Never add real learner data, even your own. Before a push, run `python3 dev/privacy_grep.py` (it needs a local, git-ignored denylist; it also checks commit author names and emails).
- **Build contract:** file formats, commands and checker rules are defined in `dev/CONTRACT.md`. Where code and the contract disagree, open an issue.
- **Trigger evals:** `evals/trigger.json` lists prompts that should and shouldn't start the skill.

## License

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.

Designed and field-tested by [@romanprigodskii](https://github.com/romanprigodskii). Written with Claude.
