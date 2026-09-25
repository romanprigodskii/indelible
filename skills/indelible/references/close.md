# Time control and the close

Re-read this file every time a session nears its end, and again after a context compaction. It covers keeping time during the session, the 10-minute warning, cuts, fatigue, wellbeing, the close checklist, and what happens after the learner leaves.

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

`ind session open` wrote the lock with the planned end and the close start (planned end minus 2, 5 or 8 minutes, for sessions of up to 30, up to 75, or more minutes).

- **Status line.** Run `ind session status <subject>` at each returned photo and before each block. It prints one line, for example `[indelible] 47/60 min · close starts 07:55 · questions so far 38`. Use it to decide what still fits. Tell the learner the minutes left when you start a block: "About 20 minutes left: drills block B, then closing."
- **Budget.** Never hand out a sheet whose estimated minutes exceed the time left before the close starts. Cut instead (§3).
- **Breaks.** In sessions over 75 minutes, call each break at the time `session open` printed: "Break: 10 minutes. Back at 19:25."

## 2. The 10-minute warning and the one extension

Law 4 has two moments: a warning 10 minutes before the planned end, and one question at the end of the work time (the close start from the lock).

**The warning (T−10)** is a statement, not a question. Persona A, 07:00–08:00:

```
07:50, 10 minutes left. Block B (~8 min) won't fit before closing at 07:55, so unless you extend, it moves to Saturday.
```

**The question at the close start**, only if work is left and an extension is possible (below):

```
07:55: closing time. Close now (block B moves to Saturday), or 15 more minutes once, then close?
```

- No answer within about a minute: close. For a learner who prefers few questions (Learner notes), skip the question and close; they can still say "extend" after the warning.
- **At the planned end** (a timer may fire): if an extension is running, say when it ends ("Extension until 08:15, then closing"). Otherwise the close should already be under way; if it isn't, start it now.
- **One extension per session, at most.** When it runs out, close; never offer a second one.
- **Extension length** = min(`session.extension_max_min` from `indelible.json` (default 15, never over 30), 0.25 × planned minutes, next fixed start − 15 − planned end).
  - The next fixed start is the earliest of: the next block of any subject (`ind plan list --from <today> --to <today>`); a `time.blocked` entry; 30 minutes before bedtime.
  - Persona A: min(15, 15, 09:00 work − 15 − 08:00 = 45) = 15 minutes.
- **If the extension comes to 0 or less,** the options are "close now" or "shift the next block". Shifting needs a yes: then `ind plan move <block-id> --start <ISO>`. If that block is in the learner's calendar, follow [calendar.md](calendar.md) before writing anything there.
- **Standing choice.** `session.overrun` `stop`: close without asking. `extend`: take the one extension without asking, and say so.
- **Overruns.**
  - A session that runs more than 20% over its planned minutes (an extension counts) logs `ind ledger add defect --subject <s> --category sizing --what "ran 75 of 60 min" --fix-type <type> --fix "<change>"`.
  - Two overruns in a row of more than 25% go to the plan: lengthen the slot or shrink the budget ([plan.md](plan.md)).

## 3. What to cut

When the remaining work doesn't fit before the close start, cut in this order:

1. new theory;
2. the second drill block;
3. mixed extras.

Never cut the 2-day recheck, and never the close.

- Cut work is not lost. It goes into the next block's sheets, which you build after the close message (§9).
- Theory cut before it was read means the topic was not taught today, so don't run `ind session taught` for it.
- A block cut before it started was never presented. Leave its questions out of `grades.json` ([session-grade.md](session-grade.md)).

## 4. Fatigue

- **A difficulty statement** ("I'm wiped", "this is too much", "my head's done"): offer a stop in one line, **each time** one recurs. "We can stop here: I'll close now and the rest moves to Saturday. Or keep going. Your call."
  - Don't argue, and don't repeat the offer until the next statement.
  - A stop is a normal close (§6), started early.
- **Recording a difficulty statement.** Record it only with the learner's knowledge: "Want me to note that for the weekly review?" On a yes, run `ind note append <subject> fatigue` with their words on stdin. If they say "off the record", nothing is written.
- **The decline rule,** for sessions of 90 minutes or more:
  1. Compare the first third of today's graded questions with the last third, on accuracy and on seconds per question (from each sheet's start and stop).
  2. Put both in the close note, e.g. `thirds 84→66%, 72→98 s/q`.
  3. If the last third drops by 15 points or more, or slows by 30% or more, in 2 of the last 3 such sessions (the LAST SESSIONS lines in `ind brief <subject>`), propose a shorter session or an extra break.
  4. The learner decides. A yes is a dated decision with a safeguard ([plan.md](plan.md)).

## 5. Wellbeing

Distress is not fatigue. If the learner expresses hopelessness, panic, self-harm or persistent distress (law 13):

- **Stop the study frame at once:** no timer, no checklist, no sheets.
- **Respond as a caring person would.** Acknowledge what they said in plain words, ask how they are, and stay with it.
- **Offer support.** Suggest someone they trust. If they are in danger, or self-harm comes up, give the local emergency number or a crisis line (for example 988 in the US, or Samaritans on 116 123 in the UK and Ireland), and offer to find the line for their country.
- **Under 18** (`learner.age_band`): encourage them to talk to a trusted adult, such as a parent, a teacher or a school counsellor.
- **Nothing about it goes into study files:** no note, no ledger row, no close note. Honour "off the record" for any statement.
- **Leave the session open.** When they are ready, or at the next start, close it with a neutral note ("stopped early"). A late close records only that it was late, never why.
- **No guilt about the plan.** The next session reschedules whatever didn't happen.

## 6. Running the close

Start at the close start from the lock (after the extension, if one was taken). Before you run the command:

1. **Everything sat today is filed and graded** ([session-grade.md](session-grade.md)). A 2-day recheck is always graded today. A practice sheet that can't be graded now needs a to-do: `ind ledger add owed --subject <s> --what "grade <sheet id>" --due <ISO within 24 h> --by claude`.
2. **Every topic taught today** has had `ind session taught <subject> <topic>`.
   - For a scheduled learner, place each new recheck in the first session inside its window, as [plan.md](plan.md) describes (`ind plan place`), then run `ind plan check`.
   - For an on-demand learner, leave it unplaced; the close message names the window.
3. **Every promise made today** ("I'll…", "we'll do it next time") has `ind ledger add owed --subject <s> --what "<text>" --due <ISO>`.
4. **An overrun over 20%** is logged (§2).

Then run:

```
ind session close <subject> --note "recheck 11/14; taught matching headings; drills A done, B cut"
```

- The note is at most 120 characters. The words "tomorrow", "later" or "next time" in it need a to-do created today (check C6).
- The command prints one `PASS`, `FAIL` or `INFO` line per check.
- **Exit 0 means closed:** the session row is saved, the lock is removed, the block is marked done, and it prints `Saved: …` with the next block.
- **Exit 1 means the lock stays.** Fix each FAIL (§7) and run it again.
- **Sessions of 30 minutes or less** (persona B): the checks run silently. The learner sees a FAIL only if they must act on it.

## 7. Fixing FAIL lines

| Line | Fix |
|---|---|
| C1 evidence | Ask for the photo or file, then `ind scan ingest` ([session-grade.md](session-grade.md)) |
| C2 graded | Grade it now. A practice sheet may instead get the `owed` row from §6 step 1. A measuring sheet has no such option |
| C3 errors | Each error opened today needs kind, mode, an account (or "no account") and a due date. No command edits an error, so use `--defer`, and complete `grades.json` before recording next time |
| C4 recheck booked | `ind session taught <subject> <topic>` creates the recheck window. For a block outside its window, `ind plan place` or `ind plan move` it inside |
| C5 fix before recheck | A recheck within 12 h includes a topic with an unfixed mistake. Ask: "Your 2-day recheck is at 07:00, but one mistake on that topic isn't fixed yet. Shall I move the recheck to <time>, still inside its window?" On a yes, `ind plan move`, with [calendar.md](calendar.md) for the calendar. Otherwise `--defer` |
| C6 promises | `ind ledger add owed …` for each real promise, with a due time |
| C7 views | A view was hand-edited. Say: "Your edit to the progress page will be replaced; I'll keep a backup copy." On a yes, `ind render <subject> --force`, then close again |
| C8 next sheets | INFO only. Build after the message (§9) |

**`--defer "<reason>"`** is for a fix that can't happen now: the photo isn't available, the learner has to leave, or the fix would overrun.
- Run `ind session close <subject> --note "…" --defer "photo of block B not available"`.
- Every failing check becomes a to-do due in 24 hours, and the session closes "with to-dos".
- Tell the learner each to-do in plain words, with its due time.
- Never defer the grading of a 2-day recheck whose answers are already in front of you.

## 8. The close message

Send one message. It uses plain vocabulary, has no IDs, and every number carries its label:

```
Saved: <what was recorded>. [To do: <item> by <day time>.]
Next: <day time> · <plain content> · <min> min. You can go; I'm preparing the next sheets.
```

- **Persona A:** "Saved: 2-day recheck 11/14 [measured], 3 mistakes scheduled, matching headings now mastery 2 [practice]. Next: Sat 10:00 · 2-day recheck + fixed mistakes · 60 min. You can go; I'm preparing the next sheets."
- **Persona B:** "Saved: 6 of 8 words right [measured]; the other 2 are scheduled to come back. Next: Fri 07:40 · words + ordering food · 20 min. You can go; I'm preparing the next sheets."
- **Persona D** (on demand, no calendar): "Saved: ownership drills 5/6 [practice]; the 2-day recheck is booked. Next: 2-day recheck, best between Thu 14:00 and Fri 18:00 · 15 min. You can go; I'm preparing the next sheets."
- **Before the first teach**, the close message also carries the theory-source question ([session-open.md](session-open.md) §6), since the sheets are built after it.

If blocks were added or moved today and the learner's calendar provider is not `none`, run `ind plan diff` before the message and follow [calendar.md](calendar.md): preview, a yes, write, then `ind cal ack`.

## 9. After the message

The learner may already be gone. Work silently:

1. Build the next block's practice sheets (theory, drills, repair) with the builder subagent, as [sheets.md](sheets.md) §6 describes: built, linted and rendered. They are issued at hand-over, in that block. Include any work cut today. The recheck is not built now: it is built at the next open, inside its window ([session-open.md](session-open.md) §2).
2. Run `ind compact <subject>`.
3. If a sheet fails lint or can't be finished, add `ind ledger add owed --subject <s> --what "build sheets for <day> <time> block" --due <ISO at least 2 h before the block> --by claude`.

Message the learner again only if something needs them.

## 10. Abrupt exits and late closes

**"Gotta go"** (or "have to run", or a goodbye mid-session): quick close in under a minute, with no questions first.

1. For each sheet handed over today and not yet filed (`ind sheet show <subject> --status issued`, or `--status sat` without evidence), add a to-do that names its id: `ind ledger add owed --subject <subject> --what "send the photo of <sheet id>" --due <ISO 24 h from now> --by learner`. `--defer` only turns failing checks into to-dos, and a sheet that was started but not filed fails none.
2. Run `ind session close <subject> --note "left early at 07:40" --defer "learner left mid-session"`.
3. Send one message: "Saved. To do: send the photo of block B by Fri 07:40. Next: Sat 10:00 · 60 min. Go; I'll prepare the sheets."
4. If a 2-day recheck was sat and not photographed, that photo is the to-do to name first.

**No reply at all:** the lock stays. The next start finishes the close first (see SKILL.md, setup step 4).

**A late close** (the brief shows an unclosed session): do it before anything else, in at most 10 minutes, using the same checklist. The CLI records it as late and logs its own mistake. Say one line: "Finishing Tuesday's close first: about 5 minutes."
