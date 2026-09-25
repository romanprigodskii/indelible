# Sample workspace

`sample-workspace/` is a small, complete study workspace, so you can try indelible without doing the setup interview first. Reviewers can use it to see the main parts of v0.1 at work: setup, a diagnostic, a taught skill, marking, the mistake log, the plan and the calendar file.

**Everything in it is synthetic.** The learner is persona A from [`evals/fixtures/persona-a.json`](../evals/fixtures/persona-a.json), an invented person who is not based on anyone real. The passages, her answers and her accounts of her mistakes, the marking, and the answer keys were all written for this sample. It was made with the real command-line tool, by [`build_sample.py`](build_sample.py) (see [Rebuilding it](#rebuilding-it)).

## What's in it

Persona A is preparing for IELTS Academic 7.5 (no band under 7.0) by 12 December 2026. She lives in Lisbon, studies for 60 minutes before work on Monday, Tuesday and Thursday and on Saturday mornings, and keeps Sundays free. The sample follows her first four days (Lisbon time):

| When | What happened | Where to look |
|---|---|---|
| Sunday 11 Oct, 18:00 | Setup: her settings, the IELTS subject with four topics, two weeks of planned sessions, a to-do (register for the exam by 20 Oct), a checkpoint set for 14 Nov, and a calendar file to import. | `indelible.json`, `ielts/subject.json`, `plan/blocks.jsonl`, `ledger.jsonl`, `plan/ics/` |
| Monday 12 Oct, 07:00 | Diagnostic, part A: eight unlabelled, mixed questions, answered in a typed file and marked 4.5 of 8 `[measured n=8]`. One wrong idea (about "not given"), one slip (the right letter chosen, another one copied into the box), one "I don't know" and one half answer. No topic had both of its part A questions right, so part B wasn't needed. | `ielts/sheets/2026-10/ielts-diagnostic-01.md`, `ielts/answers/`, `ielts/data/` |
| Tuesday 13 Oct, 07:00 | The first skill, matching headings: a theory sheet read and then closed, then one drill block of six questions, all right `[practice]`. The 2-day recheck is booked for Thursday 07:00, and Thursday's session now starts after it, at 07:15. | `ielts/sheets/2026-10/ielts-headings-01-theory.md`, `...-drills.md`, `plan/blocks.jsonl` |
| Thursday 15 Oct, 07:00 | The sample's "now": the 2-day recheck on matching headings is ready, the slip from the diagnostic is due, and the wrong idea needs a fix sheet before it comes back. | run the brief (below) |

The week after (19 to 24 Oct) is planned as a skeleton: three morning sessions and a longer Saturday one. Saturday 17 Oct (a wedding) and the Sundays are kept free, and `plan check` passes.

```
sample-workspace/
  indelible.json          her settings: time zone, study windows, sleep, session length, calendar
  CLAUDE.md               tells Claude this folder is a study workspace
  ledger.jsonl            a to-do and a checkpoint safeguard
  plan/blocks.jsonl       the plan; plan/ics/ holds the calendar file made at setup
  views/week.md           this week (generated)
  ielts/
    CLAUDE.md             her notes for this subject
    subject.json          goal, date, exam format, topics, kinds of mistake, materials, checkpoint
    data/                 sessions, graded questions, mistakes, sheets and mastery
    views/                generated summaries: brief, progress, mistakes, log
    sheets/2026-10/       the three sheets, as Markdown (readable here) and HTML (printable)
    answers/              her typed answers
    scans/index.jsonl     the evidence log
    notes/session.md      short session notes
    .indelible/specs/     each sheet as a spec, without answers
    .indelible/keys/      the sealed answer keys (see below)
    .indelible/tmp/       the grades files Claude wrote when marking
```

## Try it

You need Python 3.9 or later. A session writes files, so work on a copy:

```
cp -R examples/sample-workspace ~/indelible-sample
cd ~/indelible-sample
export INDELIBLE_NOW=2026-10-15T07:00+01:00
```

On Windows, in PowerShell:

```
Copy-Item -Recurse examples\sample-workspace $HOME\indelible-sample
cd $HOME\indelible-sample
$env:INDELIBLE_NOW = "2026-10-15T07:00+01:00"
```

**The clock.** The sample's clock is fixed with `INDELIBLE_NOW=2026-10-15T07:00+01:00`: Thursday 15 October 2026, 07:00 in Lisbon, the start of the planned session. Every indelible command reads that variable instead of your computer's clock, so set it in the terminal before you start Claude Code, and the commands Claude runs pick it up. Without it, the sample follows your computer's clock and the dates simply don't line up: before 11 October 2026 its history lies in the future, and after 15 October 2026 Thursday's sessions show as missed ("no record yet") and the recheck window as passed. Nothing breaks. Because the clock doesn't move, a session you run here is recorded as lasting 0 minutes.

**With Claude Code.** Install the plugin as the [main README](../README.md#install) describes, or load it from a checkout of this repository for one session with `claude --plugin-dir <path to the repository>`. Start Claude Code in the copy and try:

- **"status"** or **"where am I this week?"**: what's due, the week and the numbers. It changes nothing in the plan or the records.
- **"what's due?"**: the 2-day recheck on Tuesday's skill, one slip that is due, and one wrong idea that gets a fix sheet before it's tested again.
- **"start"**: a session that opens with the 2-day recheck. Claude builds the recheck sheet with its builder subagent, you answer it on paper or in a typed file, and it is marked before anything new begins.
- **"done"**: the close checklist, which files and marks everything and books what comes next.

Claude says once that it runs a small script that keeps the study record as files in a folder on your computer and sends nothing over the internet. The main README has the optional permission rule that stops Claude Code from asking about each call, and says what that rule allows.

**Without Claude.** The command-line tool runs on its own. In the copy, with `INDELIBLE_NOW` still set and `<repo>` standing for your checkout of this repository (on Windows, `py -3` instead of `python3`):

```
python3 <repo>/skills/indelible/scripts/indelible.py brief
python3 <repo>/skills/indelible/scripts/indelible.py plan week
python3 <repo>/skills/indelible/scripts/indelible.py stats ielts
```

The brief is the only thing Claude reads when a session opens. At the sample's clock it starts roughly like this:

```
IELTS Academic · exam · 2026-12-12 (58 days left)
NOW/NEXT: today 07:00–07:15 2-day recheck (mixed) (15 min) · today 07:15–08:00 fixing mistakes: ...
DUE: 2-day rechecks ready now: 1 · mistakes due: 1 slip · mistakes to fix before they come back: 1
MASTERY (0–5): Matching headings 2 · True, false or not given 1 · Task 1 overview 1 · Paraphrase 1
```

## How it differs from a real workspace

- **No `.gitignore`.** A real workspace comes with one that keeps answer keys, typed answers, photos and the inbox out of version control. The sample leaves it out on purpose, so that its synthetic keys and answers are part of this repository and the sample is complete.
- **The answer keys are here, in `ielts/.indelible/keys/`.** In a real workspace nobody looks in that folder: Claude is told never to open it, and the only way in is `key open`, which works only after an attempt is filed. If you'd like to try a sheet the way a learner would, don't read the keys first.
- **Typed answers, no photos.** Persona A normally sends phone photos of her paper; here her answers were typed, so the repository holds no images.
- **No backup copies and no empty folders.** The `.bak` copies the tool keeps beside the files it rewrites were left out, and git keeps no empty folders. The tool makes any folder it needs again.
- **A placeholder in `CLAUDE.md`.** In a real workspace, the top-level `CLAUDE.md` names the full path of the installed skill's script. Here it keeps the template's `<skill>` placeholder, so it points at no one's folders.
- **A calendar file, not a calendar.** Persona A's fixture uses Google Calendar; the sample uses the file option instead, so it connects to no calendar service. The file's notes say "open Claude in ~/Study" because that is where the invented learner keeps her folder. In the story she imported the file into her calendar app, and the plan records that; here it is only a file.

## Rebuilding it

[`build_sample.py`](build_sample.py) rebuilds the sample from scratch through the real command-line tool, following the timeline above:

```
python3 examples/build_sample.py --force
```

- It works in a new temporary folder and deletes it at the end. `HOME` (and `USERPROFILE`) point inside it, so your own home folder is never read or written.
- `INDELIBLE_NO_BROWSER=1` is set and every sheet is built as Markdown and HTML only, so it starts no browser and no typst. It makes no network connections.
- `INDELIBLE_NOW` is set for every step, so the record's dates don't depend on when you run it, and a rebuild with the same tool gives the same files.
- It writes directly only what Claude writes with its own tools in a real session: the builder's spec and answers files, the grades files, the calendar results file, and the learner's lines in the two `CLAUDE.md` files. It also puts the `<skill>` placeholder back in the top-level `CLAUDE.md`. Every data file is written by `indelible.py`.
- Before copying, it checks that no file holds a path from the machine it ran on.

[`tests/test_examples.py`](../tests/test_examples.py) keeps the sample from going stale: on a copy, at the sample's clock, it runs the brief, `due` and `plan check`, runs a whole 2-day recheck session, checks the files against the plugin directory's limits, and checks that a rebuild still produces the same files.
