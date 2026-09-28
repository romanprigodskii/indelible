# Session open

Load this whenever a session starts: the first 1–3 minutes and the 2-day recheck that opens the session. `<s>` is the subject id, `<B>` a block id.

## Contents

1. Session order
2. The materials buffer
3. The open, step by step
4. The budget
5. The cold block (the 2-day recheck)
6. Questions asked later

## 1. Session order

1. **Open** (this file): the brief, loose ends, the lock, the opener.
2. **Cold block:** the 2-day recheck, on paper, marked straight away ([session-grade.md](session-grade.md)).
3. **Work:** repair of untreated mistakes, then new material and drills, then profile blocks ([session-teach.md](session-teach.md)).
4. **Close,** inside the planned time ([close.md](close.md)). When time runs short, cut as [close.md](close.md) §3 says: never the recheck or the close.

## 2. The materials buffer

- **Practice sheets were built ahead** ([close.md](close.md) §9) and wait as `rendered` until hand-over.
- **The recheck is built now,** inside its window (the normal order, not a late build): `ind due <s> --list` knows only what is due now, and a recheck waiting in the learner's sheets folder could be looked at before it is sat (Law 3). Start the builder as soon as the lock is set (§5), after any carried-over drill marking (§4), and give the opener while it runs.
- **A window closing soon comes first:** `CLOSING` (RECHECK NOW, `ind due <s> --list`) means within 30 minutes. Build and issue that recheck first, and have the learner start before the "Start by …" time `ind sheet issue` prints (later is a late recheck: [plan.md](plan.md) §7).
- **The listings Law 6 allows at the open,** besides the brief: `ind sheet show <s> --status rendered` (the sheets waiting), `ind due <s> --list`, step 4's two reads when a session is already open, and the output of the open's commands (`ind session open`, `ind doctor`, `ind topic show <s>`). Never data files, views, notes or anything under `.indelible/`.
- **A practice sheet for today is missing:**
  1. Log it: `ind ledger add defect --subject <s> --category late_build --what "no new-material sheet ready for the <time> block" --fix-type rule --fix "builder runs right after the close message"` (refused `rule`: a structural fix, e.g. `--fix-type planner --fix "at least 2 h between a close and the next block"`).
  2. Build it while the learner works on the recheck, never making them wait.
  3. Without excuses: "Today's new sheet isn't ready yet, my mistake. Start the recheck; the new sheet will be ready before you finish."

## 3. The open, step by step

One question at a time (Law 9). The learner may answer "skip" at steps 2, 3 and 7.

### Step 1: `ind brief <s> --open`, the first read

`--open` counts a session open for step 3; every other brief runs without it and changes nothing.

- **FLAGS,** in this order:
  - An unclosed session: close it first ([close.md](close.md) §10).
  - `missed?` blocks, then a subject that "hasn't run lately" (the alarm, for this or another subject): step 2.
  - A 2-day recheck whose window has passed: the late-recheck rule ([plan.md](plan.md) §7) at this session (LATE RECHECK below the line; tier 0 of `ind due <s> --list`).
  - A sheet issued and not taken after 2 session opens: step 3.
  - Quarantined lines: one line to the learner ("A few lines in your record couldn't be read. They're kept aside and nothing is lost."); edit nothing.
  - An armed safeguard that is due: one line, then the weekly review handles it ([review.md](review.md)).
- **NOW/NEXT** is today's plan, **DUE** the recheck's size; a **TO-DO** due today or overdue gets a line in the opener.
- **LEVELS (MASTERY in plain mode), LAST SESSIONS, PACE and NOTES** are for you; follow NOTES (the learner's notes, the "do not calibrate on" list, their overrides).
- **Everything below `-- for Claude, do not read aloud --`** stays with you: the ids behind the flags (MISSED? for `plan done|move|miss`, ALARM, NOT TAKEN for `sheet void`, TO-DO IDS for `ledger close`), RECHECK NOW, LATE RECHECK, BELIEFS DUE, OTHER DUE, NEEDS REPAIR, OVERRIDES and MY RULES (your own rules after a mistake: follow them, and pass those starting "builder:" to the builder). A mistake named before the recheck is marked spoils the recheck.
- **A gap of 5 days or more** in LAST SESSIONS: run the re-entry session ([session-teach.md](session-teach.md) §6).

### Step 2: missed blocks (scheduled mode only)

All the `missed?` blocks in one message, by day (up to 3 named; beyond that, "the sessions since <day>"):

> Monday's and Tuesday's sessions have no record. Did they happen without me, get moved, or get skipped? If they differ, say which.

- **Already said** ("missed yesterday and today", "sick till Monday"): don't ask; record their words.
- **"What got in the way?"** At most once per open, in the next message, only after a skip with no reason given: "What got in the way: tired, busy, forgot, didn't feel like it, or something else?" One answer covers every skip.
- A question about the plan, not an accusation: never "again", "you missed" or a count. Take the answer as given.
- **Re-entry** (a gap of 5 days or more): don't list or count the blocks. Only when the missed? line shows a block "on your own", ask "Did you do any of the sessions on your own since <the last session's day>?" Those happened; every other block is skipped, no reason asked.
- **Record each block:**
  - Happened without you: `ind plan done <B>`, and ask for photos of any sheets done then, marked after today's recheck (drills on a topic whose 2-day recheck is still ahead: in the open, before it is built, §4).
  - Moved: `ind plan move <B> --start <ISO>`, if a new time was given.
  - Skipped: `ind plan miss <B> --reason "<their words, or 'no reason given'>"`; its content is placed again at the close or in [plan.md](plan.md), and a missed recheck is never replaced by a warm review.
- **Never ask** about soft blocks, or anything in on-demand mode.
- **An alarm** ("<subject> hasn't run lately"): [plan.md](plan.md) §7's three choices, in its words (never the flag's count), once per open, in their own message; record the choice as it says. For this subject, only once the answers above confirm two skips in a row (not sessions held without you or moved), and never at re-entry, which re-plans the week instead ([session-teach.md](session-teach.md) §6 step 5); for another, after this step's answers.

### Step 3: a sheet issued and not taken after two session opens

> Tuesday's paraphrase drills haven't been done yet. Sit them now, or drop that sheet?

- **A recheck's topics are never named:** "Tuesday's 2-day recheck hasn't been done yet."
- **"Now":** a recheck first, any other sheet after today's recheck. One whose window has passed is a late recheck ([plan.md](plan.md) §7): say in one line that it can't raise mastery.
- **"Drop":** `ind sheet void <s> <id> --reason "<their words>"`.

### Step 4: the lock

`ind session open <s> --planned <MIN> --block <B> --kind <the block's kind>`

- **MIN** is the block's length, or the learner's time: "I have 15 minutes" is `--planned 15` with no block.
- **A slot split into a recheck block and a session block** ([plan.md](plan.md) §1): `--block` is the session block, `--planned` the whole slot, and every sheet, the recheck included, is issued against the session block.
- **Exit 1, this subject locked and not stale:** a session is running, probably in another chat. Build and issue nothing before reading `ind session status <s>` and `ind ledger list --kind owed --open --subject <s>`. Then: "A session that started at 07:00 is still open, probably in another chat. I'll carry it on here, so send photos of any sheet here from now on. Did you already send photos of a sheet there?" If so, ask for them again: the other chat may not have filed them.
- **Another subject is locked:** "Close <other subject> first, or park it?" To park, re-run with `--park-other` and delete the parked session's timer jobs (CronList, then CronDelete). Never switch subjects silently.
- **Read the printed budget** (§4).

### Step 5: the opener

Plain words, no IDs, no rule codes, at most 4 lines. Persona A, Thursday 07:00, 60 minutes:

```
IELTS · Thu 07:00–08:00 (closing starts 07:55)
Since last time: Tuesday ran (58 min). Monday didn't happen (busy); it's moved to Saturday.
Today: 2-day recheck with 2 fixed mistakes mixed in (~12 min, ready in about 2) → new: matching headings. Read the sheet and do its pencil questions, then drills (~25 min).
Say "go", or change anything.
```

Persona B, 20 minutes on the train:

```
Spanish · 20 min (closing starts 07:58)
Today: 2-day recheck (~5 min) → 5 questions on ordering food.
Say "go".
```

Never say what is on the recheck, or which mistakes come back; name only the new topic. "Since last time" comes from LAST SESSIONS and step 2, left out when empty. A to-do due today adds a line: "To do today: register for the 12 December test."

### Step 6: overrides

The learner may change any part of the call (skip the recheck or the theory, check in their head, swap topics, call something easy).

1. **Accept it,** unless it breaks an integrity rule (answers before the attempt, keys, consent, honesty, wellbeing): say why in one line.
   - **"Skip the recheck"** moves it, never drops it, with no prediction or `ind session override` (Law 9). Scheduled: `ind plan move <recheck block> --start <ISO>` to the next slot inside its window, then `ind plan check`. On demand: "Its window closes <time>; after that it becomes a late check that can't raise mastery."
   - **"I'll check in my head"** holds for one sheet: the next sheet has its lines again, and marking records those checks as `head` ([session-grade.md](session-grade.md) §7).
2. **A validity rule can be overridden, never on the recheck itself:**
   - **The 24-hour rule or the cold window** ("recheck me on it today anyway"): L7 holds, and the booked recheck stays. Offer a `mixed` practice sheet, all `origin: new` (only `new:<topic>` lines in SERVE), whose result is "[practice] not counted (seen too recently)". Grading it logs a drill exposure, which moves a 2-day recheck's window: run `ind plan check`, and move a recheck now within 24 h of the sitting or outside its window ([plan.md](plan.md) §7 once it has passed).
   - **The gap between measurements:** run the sitting, and state the confound beside the result ([measure.md](measure.md) §4).
3. **Ask for a one-line prediction about specific questions,** never a total: "Fine by me. Which questions in the first block will you get right? For example '1 to 6' or '1 to 4'."
4. **Log it:** `ind session override <s> "<their words>" --predict "<their line>"`, scored at marking.

### Step 7: energy check (optional)

For planned sessions of 120 minutes or more, learners under 18 in a late window, and anyone who opted in: "Energy right now, from 1 (empty) to 5 (sharp)?" At 2 or less: "Want to swap today's new topic for practice on things you already know, and move any test to another day? Your call." The recheck still runs. Record the score only with their agreement (`ind note append <s> session`).

### Step 8: timers

You act only when a message or a timer arrives, so Law 4's moments need timers, or clock times the learner watches.

- **Claude Code's one-shot timers** (ToolSearch `select:CronCreate,CronDelete,CronList`): one job per moment, `recurring: false`, minute, hour, day and month pinned, in the computer's local time (convert if `ind doctor` says its offset differs from the workspace's):
  - T−10, T being the planned end: the warning;
  - the close start `session open` printed: the question;
  - the close start + 2 minutes, "no-answer": close if the question got no answer (a minute later if it falls on :00 or :30, which can fire up to 90 seconds early);
  - T, the planned end (in sessions of 30 minutes or less, one job, "no-answer and planned end", covers both);
  - in sessions over 75 minutes, each break's start and end.

  Each job's prompt: "indelible timer: <moment> for <s>. Run `ind session status <s>` first. If no session is open, or the study frame is stopped (Law 13), say nothing." CronList finds them after a compaction; [close.md](close.md) handles each moment, and replaces or deletes jobs.
- **No timer tool:** give the clock times at the first hand-over: "Warning at 07:50, closing at 07:55. At 07:55, stop and send your photo even if I haven't written." Then check `ind session status <s>` at each photo and before each block.
- **Breaks** come at the printed times; nothing on a sealed sheet is discussed during one.

## 4. The budget

`ind session open` prints the budget. Use its numbers; never recompute them:

- **Work minutes:** today's total sheet time (recheck, repair, theory, drills). The builder gets the remaining minutes (`ind sheet lint <s> <id> --budget-min <remaining>`), and `ind sheet issue` refuses a sheet over them, less the sheets already issued on the session's block (Law 4). **Minutes win:** fit sheets by their estimated minutes.
- **Question budget:** a rough guide to today's questions, the recheck included, at the main layer's pace; mixed layers may fit more.
- **Close start** (the close begins then, not at the planned end), and **break times** in sessions over 75 minutes.
- **Short sessions (30 minutes or less):**
  - A teach and its recheck may span sessions: the theory card one day, drills the next, and the recheck 44–72 h after the last warm exposure.
  - Drills on a topic whose 2-day recheck is still ahead are marked the session they are sat: cut drill questions, not the marking. Marking that still carries over comes in the open, before the recheck is built (§2): the verdicts, then each miss's account and standard (Laws 10 and 11), each question named by gist and answer ([session-grade.md](session-grade.md) §3); then, per topic with a miss, `ind session expose <s> <T> --kind review` and `ind plan check` (its window restarts 44–72 h from this marking). A recheck is always marked the same day.
- **A quick session** (scheduled mode only): no block and under half of `session.length_min`, like a 120-minute learner's daily 15-minute catch-up ([teach.md](teach.md) Q6). It serves the 2-day recheck if its window is open (never cut), then the rest of `ind due <s> --list` in tier order; no new topic unless the learner overrides (step 6: then sized to the minutes left, its recheck placed at the close); no diagnostic, mock or checkpoint. On-demand sessions are never quick: any may teach ([measure.md](measure.md) §11).
- **Measurement sittings** (diagnostic, mock, checkpoint) are sized by the exam clock ([measure.md](measure.md)).

## 5. The cold block (the 2-day recheck)

The recheck takes at most a quarter of the planned minutes in sessions of 30 minutes or less (5 of 20), and 10–15 minutes otherwise, out of the question budget. It opens the session so that the day's teaching can't contaminate it (why it counts: [method.md](method.md) §1, principle 3).

1. **Choose the content with `ind due <s> --list`,** which lists what is due by tier. A tier 0 (late rechecks, window passed) comes first, as [plan.md](plan.md) §7 says: the issued `cold` sheet if there is one, otherwise a `probe` on those topics (L7 refuses a `cold` sheet outside its window). Then fill the share in tier order: 1, 2-day rechecks inside their window (a topic's first, or "again" after one that left it below 3); 2, fixed mistakes due; 3, shaky answers; 4, the oldest due; 5, last checks on retired mistakes (`sentinel:<E-id>`); 6, level-4 and 7, upkeep rechecks, both `cold:<topic>`, which wait when the share is full (they have no window). Tier 8, untreated mistakes, goes to repair, never on the sheet ([session-teach.md](session-teach.md) §1). Within a tier, earlier wrong answers the learner had not named as least sure come first. Every question is new: fresh numbers or sentences, never the item that was missed.

   **At least 2 questions on each recheck topic** (tiers 1, 6 and 7; a cold pass needs 2 counted): every tier 1 topic gets 2 before any later tier goes on, and a tier 6 or 7 topic goes on with 2 or not at all (L7 refuses fewer). If the share can't hold 2 for each tier 1 topic, drop the one whose window stays open longest, to a later session inside its window (none left: [plan.md](plan.md) §7). Never one question per topic; a quick session serves a recheck only when 2 per topic fit.
2. **Excluded:** any topic with an untreated mistake, or a warm exposure (teach, repair, chat, drill or review) in the last 24 hours (L7 refuses both; nothing works around it), and a topic with an open re-teach to-do ([session-teach.md](session-teach.md) §4) until the re-teach has run. A learner who insists gets a practice sheet (§3 step 6).
3. **The sheet** is a `cold` one, unlabelled and mixed, from the builder ([sheets.md](sheets.md) §6).
4. **The sitting:**
   - **Hand it over** and issue it against the session block (`ind sheet issue <s> <id> --block <B>` prints its sheet code): "Here's your 2-day recheck, sheet <code>: <path>. On paper, book closed. Write the start time on the first line and a check beside every answer. At the end, write the stop time and fill in the Least-sure line: item numbers, or 'none'. Writing 'I don't know' is always fine. When you're done, send the photos (<the route from the welcome card>) and say 'sent'." No printer: a notebook, as [sheets.md](sheets.md) §8 says.
   - **Typed answers** (`format.answer_form` "typed"), in place of the paper lines: "Book closed. Type your answers in one message when you stop, numbered as on the sheet, with a check after each, then the start and stop times and the Least-sure line: item numbers, or 'none'." **Code** ("code"): "in your editor, then save the test output" ([profiles.md](profiles.md) §7).
   - **Sealed until marked** (Law 2): "Write 'I don't know' for now. We'll go through it right after marking." Note the number: "I don't understand what it asks" is an "unclear" account at marking ([session-grade.md](session-grade.md) §9).
   - **Meanwhile,** build any missing practice sheet (§2).
5. **Neither the calendar nor the chat names its topics** before marking: the calendar card reads "2-day recheck (mixed)" (`ind plan diff` writes it so).
6. **Mark it at once** ([session-grade.md](session-grade.md)), with the looked-since question first (§10 there), before any new material.

## 6. Questions asked later

Questions skipped at `teach` (express, or "skip"), and follow-ups nobody needed on day one, are asked one at a time, alone, when their trigger fires, in the words of [teach.md](teach.md) §10: the first overrun (P5), the first missed session (P6: step 2), the first tutor mention (P7), the first phone photo (P8), a change the learner wants to test (P9), a late-session decline (P1), the first session that can't be placed (P11: Q7); on express, Q3 before the diagnostic results, Q4 in the close message before the first teach, Q5 before the first marked miss, Q8 at the first clash. The week-1 and week-2 reviews ask P1, P3 and P10 ([review.md](review.md) §8).
