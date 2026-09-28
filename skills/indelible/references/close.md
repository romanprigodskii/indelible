# Time control and the close

Re-read this file every time a session nears its end, and after a context compaction.

## Contents

1. Keeping time
2. The 10-minute warning and the one extension
3. What to cut
4. Fatigue
5. Wellbeing
6. Running the close
7. Fixing FAIL lines
8. The close message
9. After the message
10. Abrupt exits and late closes

## 1. Keeping time

`ind session open` wrote the lock with the planned end and the close start (the planned end minus 2, 5 or 8 minutes, for sessions of up to 30, up to 75, or more minutes).

- **Status line:** `ind session status <subject>` at each returned photo and before each block, to decide what still fits. Its first line (`[indelible] 47/60 min · close starts 07:55 · questions so far 38`) may be shown as is; the second, for you, names the sheets out. Starting a block, give the minutes left: "About 20 minutes left: drills block B, then closing."
- **Budget:** never hand out a sheet whose estimated minutes exceed the time left before the close start; cut (§3).
- **Breaks** (sessions over 75 minutes) at the printed times: "Break: 10 minutes. Back at 19:25."

## 2. The 10-minute warning and the one extension

Law 4 has two moments: a warning 10 minutes before the planned end, and one question at the close start.

**The warning (T−10)** is a statement, not a question. Persona A, 07:00–08:00:

```
07:50, 10 minutes left. Block B (~8 min) won't fit before closing at 07:55, so unless you extend, it moves to Saturday.
```

**The question at the close start,** only if work is left and an extension is possible (below):

```
07:55: closing time. Close now (block B moves to Saturday), or 15 more minutes once, then close?
```

- **No answer by the no-answer timer** (the close start + 2 minutes; with no timer, the next message after that): close, once `ind session status` shows at least 2 minutes more than when you asked (if not, the job fired early: set one 2 minutes on, off :00 and :30). A yes before the planned end, while the close hasn't run, still takes the extension. For a learner who prefers few questions (Learner notes), skip the question and close; they can still say "extend" after the warning.
- **At the planned end:** with an extension running ("extension until" in `ind session status`), say when it ends ("Extension until 08:15, then closing"); otherwise start the close if it isn't under way.
- **One extension per session;** when it runs out, close.
- **Record it at once:** on a yes (or the `extend` standing choice), `ind session extend <subject> --min <N>`; with timers, replace the no-answer job (in 30 minutes or less, the no-answer and planned-end one) with one at the new close start it prints.
- **Extension length** = min(`session.extension_max_min` (default 15, never over 30), 0.25 × planned minutes, next fixed start − 15 − planned end), which `ind session extend` enforces; work out the third before asking, so the question offers only what fits.
  - The next fixed start is the earliest of the next block of any subject (`ind plan list --from <today> --to <today>`), a `time.blocked` entry, and 30 minutes before bedtime; something already under way when the session started (a day blocked as sick) doesn't count.
  - Persona A: min(15, 15, 09:00 work − 15 − 08:00 = 45) = 15 minutes.
- **An extension of 0 or less:** "close now" or "shift the next block" (a yes, then `ind plan move <block-id> --start <ISO>`, and [calendar.md](calendar.md) before any calendar write).
- **Standing choice** `session.overrun`: `stop` closes without asking; `extend` takes the one extension without asking, and says so.
- **Overruns:** over 20% past the planned minutes (an extension counts): `ind ledger add defect --subject <s> --category sizing --what "ran 75 of 60 min" --fix-type <type> --fix "<change>"`. Two in a row over 25% go to the plan: lengthen the slot or shrink the budget ([plan.md](plan.md)).

## 3. What to cut

When the remaining work doesn't fit before the close start, cut in this order: new theory; the second drill block; mixed extras. Never the 2-day recheck, and never the close.

Cut work goes into the next block's sheets (§9). Theory cut before it was read was not taught (no `ind session taught`); a block cut before it started stays out of `grades.json`.

## 4. Fatigue

- **A difficulty statement** ("I'm wiped", "this is too much"): offer a stop in one line, each time one comes: "We can stop here: I'll close now and the rest moves to Saturday. Or keep going. Your call." Don't argue, or repeat it before the next one. A stop is a normal close (§6), started early.
- **Record it** only with the learner's knowledge: "Want me to note that for the weekly review?" A yes: `ind note append <subject> fatigue`, their words on stdin; "off the record": nothing.
- **The decline rule** (sessions of 90 minutes or more): compare the first and last thirds of today's graded questions on accuracy and seconds per question (from each sheet's start and stop), both in the close note (`thirds 84→66%, 72→98 s/q`). A last third down 15 points or more, or 30% slower, in 2 of the last 3 such sessions (LAST SESSIONS in `ind brief <subject>`): propose a shorter session or an extra break. The learner decides; a yes is a dated decision with a safeguard ([plan.md](plan.md)).

## 5. Wellbeing

Distress is not fatigue. If the learner expresses hopelessness, panic, self-harm or persistent distress (Law 13):

- **Stop the study frame at once:** no checklist, no sheets, no timers: delete every pending timer job, one set after an extension included (CronList, then CronDelete), so none fires into the conversation.
- **Respond as a caring person would.** Acknowledge what they said in plain words, ask how they are, and stay with it.
- **Offer support.** Suggest someone they trust. If they are in danger, or self-harm comes up, give the local emergency number or a crisis line (for example 988 in the US, or Samaritans on 116 123 in the UK and Ireland), and offer to find the line for their country.
- **Under 18** (`learner.age_band`): encourage them to talk to a trusted adult, such as a parent, a teacher or a school counsellor.
- **Nothing about it goes into study files:** no note, no ledger row, no close note. Honour "off the record" for any statement.
- **Leave the session open.** When they are ready, or at the next start, close it with a neutral note ("stopped early"). A late close records only that it was late, never why.
- **No guilt about the plan.** The next session reschedules whatever didn't happen.

## 6. Running the close

Start at the close start (after the extension, if one was taken). Before the command:

1. **Everything sat today is filed and graded** ([session-grade.md](session-grade.md)); a 2-day recheck always today. A practice sheet that can't be graded now gets a to-do: `ind ledger add owed --subject <s> --what "grade <sheet id>" --due <ISO within 24 h> --by claude`.
2. **Every topic taught today** has had `ind session taught <subject> <topic>`. Scheduled: place each new recheck, and each `Recheck to place` an exposure printed, in the first session inside its window (`ind plan place`, [plan.md](plan.md)), then `ind plan check`, except a topic owed a re-teach ([session-teach.md](session-teach.md) §4). On demand: unplaced; the close message names the window.
3. **Every promise made today** ("I'll…", "we'll do it next time") has its to-do: check `ind ledger list --kind owed --open --subject <s>`, and add any missing (`ind ledger add owed --subject <s> --what "<text>" --due <ISO>`).
4. **An overrun over 20%** is logged (§2).
5. **The next block of this subject is solo** (`solo` in `ind plan list`, "on your own" in the brief; no session with Claude before it, however far off): build its practice sheets now, with no new topic ([session-teach.md](session-teach.md) §6), and issue each (`ind sheet issue <s> <id> --block <B>`); C8 fails until one is. A failed build: the close message says so and offers to move the block, never an owed `--by claude` to-do nobody acts on in time.

Then run:

```
ind session close <subject> --note "recheck 11/14; taught matching headings; drills A done, B cut"
```

- The note is at most 120 characters; "tomorrow", "later" or "next time" in it need a to-do created today (C6).
- **Exit 0 means closed** (the lock removed, the block marked done, a recheck block only once its sheet is graded): delete any pending timer job (CronList, then CronDelete).
- **Exit 1 means the lock stays:** fix each FAIL line (§7) and run it again. In sessions of 30 minutes or less (persona B) the checks run silently; the learner sees a FAIL only if they must act on it.

## 7. Fixing FAIL lines

| Line | Fix |
|---|---|
| C1 evidence | Ask for the finished sheet's photo or file (a gate photo alone doesn't count), then `ind scan ingest` ([session-grade.md](session-grade.md) §2) |
| C2 graded | Grade it now; a practice sheet (never a measuring one) may get §6 step 1's to-do |
| C3 errors | Each error opened today needs kind, mode, an account (or "no account") and a due date. No command edits an error: `--defer`, and complete `grades.json` before recording next time |
| C4 recheck booked | `ind session taught <subject> <topic>` creates the window; `ind plan place` or `ind plan move` a block into it |
| C5 fix before recheck | Ask: "Your 2-day recheck is at 07:00, but one mistake on that topic isn't fixed yet. Shall I move the recheck to <time>, still inside its window?" (at least 24 h after the fix). A yes: `ind plan move`, with [calendar.md](calendar.md). Otherwise `--defer` |
| C6 promises | `ind ledger add owed …` for each real promise, with a due time |
| C7 views | A view was hand-edited: "Your edit to the progress page will be replaced; I'll keep a backup copy." On a yes, `ind render <subject> --force`, then close again |
| C8 next sheets | INFO: build after the message (§9). FAIL only before a solo block with no sheet issued: build and issue now (§6 step 5), or `--defer` and name the to-do in the message |
| C9 recheck sat | Move the unsat recheck with the command the line prints, then `ind plan check`, and preview it for the calendar ([calendar.md](calendar.md)). No time left in the window, or on demand: INFO; name the window in the close message (past it, a late recheck: [plan.md](plan.md) §7) |

**`--defer "<reason>"`,** for a fix that can't happen now (no photo, the learner has to leave, it would overrun): `ind session close <subject> --note "…" --defer "photo of block B not available"` turns every failing check into a to-do due in 24 hours; tell the learner each, in plain words, with its due time. Never defer grading a 2-day recheck whose answers are in front of you.

## 8. The close message

One message, plain vocabulary, no IDs, every number labelled:

```
Saved: <what was recorded>. [To do: <item> by <day time>.]
Next: <day time> · <plain content> · <min> min. You can go; I'm preparing the next sheets.
```

- **Persona A:** "Saved: 2-day recheck 11/14 [measured], 3 mistakes scheduled, matching headings now mastery 2 [practice]. Next: Sat 10:00 · 2-day recheck + fixed mistakes · 60 min. You can go; I'm preparing the next sheets."
- **Persona D** (on demand, no calendar): "Saved: ownership drills 5/6 [practice]; the 2-day recheck is booked. Next: 2-day recheck, best between Thu 14:00 and Fri 18:00 · 15 min. You can go; I'm preparing the next sheets."
- **First close of a new week** (scheduled mode, no `reviews/<last week>.md` yet): a last line, "Weekly review, about 10 minutes? (yes/no)"; with sessions of 30 minutes or less, instead the 3 lines of `ind review week` ([review.md](review.md) §1), run before the message (their Next line is the message's own). A yes loads [review.md](review.md); a no, or no answer, stands until next week.
- **Before the first teach,** it also carries the theory-source question (Q4, in [teach.md](teach.md) §4's words), since the sheets are built after it.
- **Next block solo:** its sheets are issued (§6 step 5), so give their paths instead of "I'm preparing the next sheets": "Next: Thu 19:00 · on your own · 45 min. Your sheet: sheets/2026-10/ielts-mixed-04.pdf. Send photos at your next session. You can go."

If blocks were added or moved today and the calendar provider is not `none`, run `ind plan diff` before the message and follow [calendar.md](calendar.md): preview, a yes, write, then `ind cal ack`.

## 9. After the message

The learner may be gone. Work silently:

1. Build the next block's practice sheets (theory, drills, repair), with any work cut today ([sheets.md](sheets.md) §6; the recheck waits for the next open). Before a theory sheet, run the floor check ([session-teach.md](session-teach.md) §2 step 1) with `ind topic show <s>`: a floor topic below 3p gets its sheets instead. Build a theory before the drills that point at it: lint checks them against it.
2. Run `ind compact <subject>`.
3. A sheet that fails lint or can't be finished: `ind ledger add owed --subject <s> --what "build sheets for <day> <time> block" --due <ISO at least 2 h before the block> --by claude`.

Message the learner again only if something needs them.

## 10. Abrupt exits and late closes

**"Gotta go"** (or "have to run", or a goodbye mid-session): a quick close in under a minute, no questions first.

1. For each sheet handed over today and not filed (`ind sheet show <subject> --status issued`, or `--status sat` without evidence), a to-do naming its id (`--defer` covers failing checks only): `ind ledger add owed --subject <subject> --what "send the photo of <sheet id>" --due <ISO 24 h from now> --by learner`. A 2-day recheck sat and not photographed is named first.
2. `ind session close <subject> --note "left early at 07:40" --defer "learner left mid-session"`, and delete any pending timer job (CronList, then CronDelete).
3. One message: "Saved. To do: send the photo of block B by Fri 07:40. Next: Sat 10:00 · 60 min. Go; I'll prepare the sheets."

**No reply at all:** the lock stays, and the next start finishes the close first (SKILL.md, setup step 5).

**A late close** (an unclosed session in the brief): before anything else, in at most 10 minutes, with the same checklist; the CLI records it as late. One line: "Finishing Tuesday's close first: about 5 minutes."
