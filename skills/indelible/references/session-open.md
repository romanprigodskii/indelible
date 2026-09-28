# Session open

Load this whenever a session starts. It covers the first 1–3 minutes and the 2-day recheck that opens the session. Then load [session-grade.md](session-grade.md) to mark the recheck, and [session-teach.md](session-teach.md) for the rest of the work. `<s>` below is the subject id and `<B>` a block id.

## Contents

1. Session order
2. The materials buffer
3. The open, step by step
4. The budget
5. The cold block (the 2-day recheck)
6. Questions asked later

## 1. Session order

1. **Open** (this file): the brief, any loose ends, the lock, and the opener.
2. **Cold block:** the 2-day recheck, done on paper, then marked straight away ([session-grade.md](session-grade.md)).
3. **Work:** repair of untreated mistakes, then new material and drills, then profile blocks ([session-teach.md](session-teach.md)).
4. **Close,** inside the planned time ([close.md](close.md)).

When time runs short, cut in this order: new theory, then the second drill block, then extras. Never cut the recheck or the close.

## 2. The materials buffer

- **Practice sheets are built ahead.** At the previous close, after the "you can go" message (before it when the next block is solo: [close.md](close.md) §6), the builder subagent (`assets/prompts/builder.md`) built the next block's theory, drills and repair sheets: linted, rendered, keys sealed. They wait as `rendered` and are issued at hand-over ([sheets.md](sheets.md) §6).
- **The recheck is built now, at the open,** for two reasons. `ind due <s> --list` can only work out what is due now, so the mistakes due on the recheck day aren't known at the previous close. And a rendered recheck would wait in the learner's sheets folder until it is sat, where a look at it is an exposure no check can see (Law 3). Building it here, inside its window, is the normal order (always so for on-demand learners), not a late build: no defect. Start the builder as soon as the lock is set, from `ind due <s> --list` (section 5); give the opener while it runs.
- **A window that closes soon comes first.** RECHECK NOW and `ind due <s> --list` give each window's closing time; `CLOSING` means within 30 minutes. Build and issue that recheck before anything else, and have the learner start before the time `ind sheet issue` prints ("Start by …"). The level rules judge a recheck by its start time: a later start is a late recheck ([plan.md](plan.md) §7).
- **At the open, list the rest** with `ind sheet show <s> --status rendered`. Apart from the brief, read this listing, `ind due <s> --list`, the two reads of step 4 when a session is already open, and the output of the commands the open runs (`ind session open`, `ind doctor` at step 8, `ind topic show <s>` for the builder's mastery). Law 6 allows CLI output only at the open: never open data files, views, notes or anything under `.indelible/`.
- **If a practice sheet for today is missing:**
  1. Log the gap as your own mistake: `ind ledger add defect --subject <s> --category late_build --what "no new-material sheet ready for the <time> block" --fix-type rule --fix "builder runs right after the close message"`. If the CLI refuses `rule` because late_build has been logged before, pick a structural fix instead, such as `--fix-type planner --fix "at least 2 h between a close and the next block"`.
  2. Run the builder for it while the learner works on the recheck. Never make the learner wait for a build that could run in parallel.
  3. Tell the learner in one line, without excuses: "Today's new sheet isn't ready yet, my mistake. Start the recheck; the new sheet will be ready before you finish."

## 3. The open, step by step

Ask one question at a time (Law 9). The learner may answer "skip" at steps 2, 3 and 7.

### Step 1: `ind brief <s> --open`, the first read

`--open` counts this as a session open for step 3. Every other brief (status, planning, a review) runs without it and changes nothing. The brief is at most 4,500 characters. Handle each section like this:

- **FLAGS,** in this order:
  - An unclosed session: close it first ([close.md](close.md)). This takes at most 10 minutes and is logged as late.
  - `missed?` blocks: step 2.
  - A subject that "hasn't run lately" (the alarm, for this or another subject): step 2, after the missed blocks.
  - A 2-day recheck whose window has passed ("late recheck" in technical words): the late-recheck rule ([plan.md](plan.md) §7) at this session. LATE RECHECK below the line names the block and topics; tier 0 of `ind due <s> --list` lists them for the builder.
  - A sheet issued and not taken after 2 session opens: step 3.
  - Quarantined lines: tell the learner in one line ("A few lines in your record couldn't be read. They're kept aside and nothing is lost.") and edit nothing.
  - An armed safeguard that is due: one line, then handle it in the weekly review ([review.md](review.md)).
- **NOW/NEXT** gives today's plan. **DUE** gives the size of the recheck. **TO-DO:** anything due today or overdue gets one line in the opener.
- **LEVELS (headed MASTERY in plain mode), LAST SESSIONS, PACE and NOTES** are for you. NOTES carries the learner's notes, the "do not calibrate on" list and their overrides; follow them.
- **Everything below `-- for Claude, do not read aloud --`** stays with you: the ids behind the flags (MISSED? block ids for `plan done|move|miss`, ALARM for the alarm's blocks and its choices, NOT TAKEN sheet ids for `sheet void`, TO-DO IDS for `ledger close`), RECHECK NOW (the topics due), LATE RECHECK (a recheck whose window passed), BELIEFS DUE, OTHER DUE, NEEDS REPAIR, OVERRIDES and MY RULES (the rules you set yourself after a mistake: follow them, and give the builder those that start "builder:" in NOTES). Naming a mistake before the recheck is marked tells the learner what to avoid, and the recheck stops measuring anything.
- **If LAST SESSIONS shows a gap of 5 days or more,** run the re-entry session instead ([session-teach.md](session-teach.md), section 6). On demand, after 7 days or more, its opener carries the three lines of [review.md](review.md) §1; they appear nowhere else.
- **Without Python:** SKILL.md, "Without Python" (no brief; read the learner's own record and mark everything `[unverified]`).

### Step 2: missed blocks (scheduled mode only)

Ask about all the `missed?` blocks in FLAGS in one message, by day (name up to 3; beyond that, "the sessions since <day>"):

> Monday's and Tuesday's sessions have no record. Did they happen without me, get moved, or get skipped? If they differ, say which.

- **If the learner already said what happened** ("missed yesterday and today", "sick till Monday", "work ran over"), don't ask: record it with their words.
- **"What got in the way?"** At most once per open, in the next message, only after a skip and only if they gave no reason: "What got in the way: tired, busy, forgot, didn't feel like it, or something else?" One answer covers every block skipped.
- This is a question about the plan, not an accusation. Never say "again" or "you missed", and never count the blocks. Take the answer as given.
- **Re-entry** (a gap of 5 days or more, step 1): don't list or count the blocks. Ask one question only when the missed? line shows a block done on the learner's own ("on your own"): "Did you do any of the sessions on your own since <the last session's day>?" Record those as happened, and every other block as skipped with no reason asked.
- **Record the answer, block by block** (the ids are under MISSED? below the line):
  - It happened without you: `ind plan done <B>`. Ask for photos of any sheets done then; they are filed and marked after today's recheck, except drills on a topic whose first 2-day recheck is still ahead: those are marked in the open, before the recheck is built, as carried-over marking is (§4).
  - It was moved: `ind plan move <B> --start <ISO>`, if a new time was given.
  - It was skipped: `ind plan miss <B> --reason "<their words, or 'no reason given'>"`. Never ask why a second time. Its content is placed again at the close or in [plan.md](plan.md). A missed recheck is never replaced by a warm review.
- **Never ask** about soft blocks, and never ask anything in on-demand mode.
- **An alarm in FLAGS** ("<subject> hasn't run lately"): offer the three choices once per open, in their own message, in [plan.md](plan.md) §7's words: "1) Re-plan the week 2) Pause IELTS until a date you pick 3) Ask me again on <day>". For the subject being opened, only once the answer above confirms two skips in a row: never when those sessions happened without you or were moved. For another subject, whose blocks this step doesn't ask about, after this step's answers. Record the choice as that section says; choice 3 is a to-do that keeps the alarm quiet until it is closed.

### Step 3: a sheet issued and not taken after two session opens

> Tuesday's paraphrase drills haven't been done yet. Sit them now, or drop that sheet?

- **For a recheck, never name its topics:** "Tuesday's 2-day recheck hasn't been done yet."
- **"Now":** it is served in this session. A recheck goes first; any other sheet goes after today's recheck. A recheck whose window has passed is sat as it is, as a late recheck: `[measured]`, labelled with its real interval, and it can't raise mastery ([plan.md](plan.md) §7). Say so in one line, and book the fresh recheck after grading.
- **"Drop":** `ind sheet void <s> <id> --reason "<their words>"`.

### Step 4: the lock

Run `ind session open <s> --planned <MIN> --block <B> --kind <the block's kind>`.

- **MIN** is the block's length, or the time the learner says they have. "I have 15 minutes" becomes `--planned 15` with no block.
- **A slot split into a recheck block and a session block** ([plan.md](plan.md) §1): pass the session block as `--block`, and the whole slot's minutes as `--planned`. Issue every sheet of the session against the session block, the recheck included: `ind sheet issue` then sizes them together against the session's minutes, and grading the recheck still finds and closes the recheck block by its topics and window.
- **Exit 1 because this subject is already locked and not stale:** a session is already running, probably in another chat, and this conversation has no record of what was said or handed out there. Build and issue nothing until you have read `ind session status <s>` (the time, and the sheets out) and `ind ledger list --kind owed --open --subject <s>` (the to-dos). Then tell the learner in one line: "A session that started at 07:00 is still open, probably in another chat. I'll carry it on here, so send photos of any sheet here from now on. Did you already send photos of a sheet there?" If they did, ask for those photos again: a photo the other chat didn't file isn't on record. `ind sheet issue` refuses a second recheck on a topic already out.
- **A warning that another subject is locked:** ask "Close <other subject> first, or park it?" For park, re-run with `--park-other`, then delete any timer job this conversation set for the parked session (CronList, then CronDelete). Never switch subjects silently.
- **Read the printed budget** (section 4).

### Step 5: the opener

Use plain words, no IDs and no rule codes, in at most 4 lines. Persona A, Thursday 07:00, 60 minutes:

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

- **Never say what is on the recheck,** or which mistakes come back. Name only the new topic.
- **"Since last time"** comes from LAST SESSIONS and the step 2 answers. Leave the line out when there is nothing to report.
- **A to-do due today** adds one line: "To do today: register for the 12 December test."

### Step 6: overrides

Make the call in the opener; the learner can change any part of it (skip the recheck, skip the theory because "I know this", skip the check lines and check in their head, swap topics, or call something easy).

1. **Accept the change,** unless it breaks an integrity rule: answers before the attempt, keys, consent, honesty or wellbeing. Those are not negotiable; give the reason in one line.
   - **"Skip the recheck"** moves it, never drops it. Scheduled: `ind plan move <recheck block> --start <ISO>` to the next slot inside its window, then `ind plan check`. On demand: say in one line "Its window closes <time>; after that it becomes a late check that can't raise mastery." It gets no prediction and no `ind session override` (steps 3 and 4): nothing is sat now, and the learner hasn't seen its questions, so there is nothing to predict. Check C9 at the close catches a recheck left where it was.
   - **"I'll check in my head"** holds for one sheet. The written check is a core rule (R41), so the next sheet has its lines again; marking records those checks as `head` ([session-grade.md](session-grade.md) §7).
2. **A validity rule can be overridden, but never on the recheck itself:**
   - **The 24-hour rule or the cold window** ("recheck me on it today anyway"). Lint L7 checks both on the recheck, and nothing overrides it. Leave the booked recheck as it is; don't build or issue it now. Offer the questions they asked for as a `mixed` practice sheet whose items all have `origin: new` (only `new:<topic>` lines in the builder's SERVE). Never a `cold:` or `error:` item on it: those belong to the recheck and the mistake ladder. Its result is "[practice] not counted (seen too recently)". Grading it logs a drill exposure, which moves a first recheck's window; then run `ind plan check`, and move a recheck that now falls within 24 h of the sitting or outside its window ([plan.md](plan.md); once its window has passed, plan.md §7's late-recheck rule).
   - **The gap between measurements:** run the sitting, and state the confound beside the result ([measure.md](measure.md) §4).
3. **Ask for a one-line prediction about specific questions,** never a total: "Fine by me. Which questions in the first block will you get right? For example '1 to 6' or '1 to 4'."
4. **Log it:** `ind session override <s> "<their words>" --predict "<their line>"`. The prediction is scored at marking. It tests the plan as much as it tests the learner.

### Step 7: energy check (optional)

- **When:** automatically for planned sessions of 120 minutes or more, and for learners under 18 in a late window. Otherwise only if the learner opted in.
- **Ask:** "Energy right now, from 1 (empty) to 5 (sharp)?"
- **At 2 or less:** "Want to swap today's new topic for practice on things you already know, and move any test to another day? Your call." The recheck still runs.
- **Record the score only if the learner agrees,** with `ind note append <s> session`.

### Step 8: timers

You act only when a message or a timer arrives, so the moments of Law 4 need timers, or clock times the learner can watch.

- **Claude Code has one-shot timers.** Load them with ToolSearch (`select:CronCreate,CronDelete,CronList`). Create one job for each moment below, with `recurring: false` and the minute, hour, day and month pinned. Timers run on the computer's local time: if `ind doctor` says its offset differs from the workspace's time zone, convert first.
  - T−10, where T is the planned end: the warning;
  - the close start `session open` printed: the question;
  - the close start + 2 minutes, "no-answer": close if the question got no answer;
  - T, the planned end (in sessions of 30 minutes or less, the no-answer moment: set one job, "no-answer and planned end", for both);
  - in sessions over 75 minutes, each break's start and end.

  The question gets 2 full minutes. A one-shot job on minute :00 or :30 can fire up to 90 seconds early, so when the no-answer moment falls on one of them, set its job a minute later.

  Each job's prompt: "indelible timer: <moment> for <s>. Run `ind session status <s>` first. If no session is open, or the study frame is stopped (Law 13), say nothing." Keep the job ids (after a context compaction, CronList finds them). [close.md](close.md) handles each moment (§2), replaces the no-answer job after an extension (§2), and deletes every job still pending (CronList, then CronDelete) at the close (§6), at an abrupt exit (§10) and when distress stops the study frame (§5). Parking a session for another subject deletes its jobs too (step 4).
- **With no timer tool,** give the clock times at the first hand-over, in one line: "Warning at 07:50, closing at 07:55. At 07:55, stop and send your photo even if I haven't written." Then run `ind session status <s>` every time a photo comes back and before each block, and act on what it shows.
- **The status line:** the first line of `ind session status` can be shown to the learner as is; the "sheets out" line is for you.
- **Breaks** fall at the times `session open` printed. Nothing about a sealed sheet is discussed during a break.

## 4. The budget

With P = planned minutes:

| P | open | close | work fraction | breaks |
|---|---|---|---|---|
| ≤30 | 1 | 2 | 0.8 | none |
| 31–75 | 2 | 5 | 0.7 | none |
| >75 | 3 | 8 | 0.6 | ceil(P/75) − 1 breaks of 10 min |

Work minutes are also reduced by a grading estimate: 15 seconds per question, plus 1 minute for each expected miss, at a 25% miss rate. The question budget is the work minutes divided by the pace of the subject's main layer. Never recompute these numbers; use what `ind session open` prints:

- **Work minutes:** the total sheet time for today, covering the recheck, repair, theory and drills. Give the remaining minutes to the builder, and lint with `ind sheet lint <s> <id> --budget-min <remaining>`. Never issue a sheet over budget (Law 4): `ind sheet issue` refuses one over these work minutes, less the sheets already issued on the session's block. **Minutes win:** fit sheets by their estimated minutes against the work minutes.
- **Question budget:** a rough guide to the total number of questions today, the recheck included. It assumes the main layer's pace, so a session that mixes layers (code with short concept questions, say) may fit more questions than it prints.
- **Close start:** the close begins at this time, not at the planned end.
- **Break times:** only for sessions over 75 minutes.

Rough figures at the default paces (estimates): 20 minutes verbal gives about 12 work minutes and 9 questions. Persona A's 60 minutes of reading gives about 37 work minutes and 31 questions. Persona C's 120 minutes of conceptual work gives about 72 work minutes, 48 questions and one break at 75 minutes.

- **Short sessions (30 minutes or less):**
  - A teach and its recheck may span sessions: the theory card one day, drills the next, and the recheck 44–72 h after the last warm exposure.
  - Drills on a topic whose first recheck is still ahead are marked in the session they are sat: when drills and their marking don't both fit, cut drill questions, not the marking. If marking still carries over, do it in the open, before the recheck is built: the verdicts and the standard for each miss, naming each question by its gist and the learner's answer, not its number alone ([session-grade.md](session-grade.md) §3). For each topic with a miss, run `ind session expose <s> <T> --kind review`, then `ind plan check`: lint L7 then keeps that topic off today's recheck, and its window restarts 44–72 h from this marking. A recheck is always marked the same day.
- **A quick session** (scheduled mode only) is one opened with no block and fewer planned minutes than half of `session.length_min`. It serves, in order: the 2-day recheck if its window is open (Law 3; it is never cut), then the rest of `ind due <s> --list` in section 5's tier order. No new topic unless the learner overrides (step 6, `ind session override`); then the new-material block is sized to the minutes left, and its recheck is placed at the close. No diagnostic, mock or checkpoint. A drop-in of half the usual length or more is an ordinary session. On-demand sessions are never quick sessions: any of them may teach ([measure.md](measure.md) §11).
- **Measurement sittings** (diagnostic, mock, checkpoint) are sized by the exam clock, not this table ([measure.md](measure.md)).

## 5. The cold block (the 2-day recheck)

The recheck takes at most a quarter of the planned minutes in sessions of 30 minutes or less (5 minutes of a 20-minute session), and 10–15 minutes otherwise. Its questions come out of the same question budget.

1. **Choose the content with `ind due <s> --list`.** A tier 0 (late rechecks, window passed) comes first, as [plan.md](plan.md) §7 says: the issued `cold` sheet if there is one, otherwise a `probe` on those topics (lint L7 refuses a `cold` sheet outside its window). Then fill the recheck in tier order until its share is used:
   1. 2-day rechecks inside their window: a topic's first, or one again after a recheck that left it below 3 (marked "again");
   2. fixed mistakes that are due;
   3. shaky answers (right, but named on a Least-sure line);
   4. the oldest due items;
   5. last checks on retired mistakes (`sentinel:<E-id>`), about 4 weeks after they retired;
   6. level-4 rechecks: a topic at mastery 3 whose first pass is 7 days old or more (`cold:<topic>`);
   7. upkeep rechecks: a topic at mastery 4 or 5, 3 weeks after its last pass, until the date (`cold:<topic>`);
   8. untreated mistakes. These are listed as "needs repair" and never go on the sheet; they go to repair ([session-teach.md](session-teach.md)).

   Tiers 6 and 7 wait whenever the share is full: a later session serves them, since they have no window. Every question is new: fresh numbers or sentences, never the item that was missed. Within a tier, earlier wrong answers the learner had not named as least sure come first.

   **At least 2 questions on each recheck topic** (tiers 1, 6 and 7). A cold pass counts toward mastery only with 2 counted questions on the topic, so give every tier 1 topic 2 before any later tier goes on, and a tier 6 or 7 topic goes on with 2 or not at all (lint L7 refuses a topic with fewer). If the share can't hold 2 for each tier 1 topic, drop the one whose window stays open longest: it goes to a later session inside its window, or, with none left, to the late-recheck rule ([plan.md](plan.md) §7). Never cut a recheck topic to one question. A quick session serves a recheck only when 2 questions per topic fit.
2. **Excluded:** any topic with an untreated mistake, and any topic with a warm exposure (teach, repair, chat, drill or review) in the last 24 hours. Lint rule L7 refuses both; never work around it. Also any topic with an open re-teach to-do (TO-DO in the brief: a new topic that didn't land, [session-teach.md](session-teach.md) §4) until that re-teach has run: its recheck comes 44–72 h after it. If the learner insists, the recheck stays booked and they get a practice sheet instead (§3 step 6).
3. **The sheet** is type `cold`: unlabelled and mixed, with no topic names in titles or labels and no two neighbouring questions on the same topic. Every question has a check line, and the sheet ends with the Least-sure line. The builder writes it ([sheets.md](sheets.md)).
4. **Looked since last time:** no sheet prints this in v0.1. When the photo arrives, before marking, ask once in chat: "Did you look at any of this since last time? Which questions? Topics in your own words are fine." Any question named is "not counted (seen too recently)" ([session-grade.md](session-grade.md) §10).
5. **The sitting:**
   - **Hand it over** and issue it against the session block from step 4 (`ind sheet issue <s> <id> --block <B>`, which prints its sheet code): "Here's your 2-day recheck, sheet <code>: <path>. On paper, book closed. Write the start time on the first line and a check beside every answer. At the end, write the stop time and fill in the Least-sure line: item numbers, or 'none'. Writing 'I don't know' is always fine. When you're done, send the photos (<the route from the welcome card>) and say 'sent'."
   - **No printer** (persona B): the learner reads the sheet on screen and writes the answers in a notebook: first line the sheet code from the header ("Sheet SPANISH-12") and the start time, then the answers numbered as on the sheet.
   - **Sealed until marked:** while the sheet is out, discuss nothing that is on it. If the learner asks about a question, say "Write 'I don't know' for now. We'll go through it right after marking." Note its number: if they said they don't understand what it asks, that is an "unclear" account at marking ([session-grade.md](session-grade.md) §9). A sealed item is marked or discussed, never both.
   - **Meanwhile,** build any missing practice sheet (section 2).
6. **Neither the calendar nor the chat names the topics.** The calendar card reads "2-day recheck (mixed)" (`ind plan diff` writes it that way), and nothing said before marking reveals which topics or mistakes are on the sheet.
7. **Mark it at once** with [session-grade.md](session-grade.md). The recheck is always marked in the same session, before any new material.

Why the recheck opens the session: performance during learning is an unreliable sign of learning (Soderstrom & Bjork, 2015), while retrieval practice and spacing both improve long-term retention (Roediger & Karpicke, 2006; Cepeda et al., 2006). Going first also keeps the day's teaching from contaminating the recheck. More in [method.md](method.md).

## 6. Questions asked later

Questions skipped at `teach` (express, or "skip") and follow-ups nobody needed on day one. Ask each alone, only when its trigger fires, never two in one message.

| # | Trigger | Question |
|---|---|---|
| P1 | Week-1 review or late-session decline | "Your 60-minute sessions ran 58, 95 and 72. Keep 60 with a firmer stop, or plan 75?" |
| P3 | Week-1 review | "Want a quick energy check at the start of shorter sessions too?" |
| P5 | First overrun | "Next time we run long: close on time, extend once, or ask?" (`session.overrun`) |
| P6 | First missed session (scheduled) | Step 2's one question for all the missed blocks; "What got in the way?" at most once, only after a skip with no reason given, in the next message |
| P7 | First tutor mention | "How often, and what do they set? May I make them a one-page summary of your mistake types? No answers in it." |
| P8 | First phone photo | "Want me to pick photos up from a folder your phone syncs to? Make it a folder just for study photos, not your whole camera roll. I copy them into your study folder, which itself stays unsynced." On a yes, record the folder's full path under "About the learner" in the root `CLAUDE.md` (a device setting, shared by every subject) |
| P9 | Wants to test a change | "Shall we write down now what result would make us keep it or undo it?" (`ind ledger add hypothesis`) |
| P10 | Week-2 review, if 3/3 starts finish ≥5/6 | "Stop a drill block early after 3 right?" |
| P11 | Express: first session that can't be placed | Q7 |
| – | Express: Q3 before the diagnostic results (for code, its code line rides the express Q1 card); Q4 (it asks about theory pages too) in the close message before the first teach, since the sheets are built after it; Q5 (a) and (b) before the first marked miss; Q8 at the first clash | [teach.md](teach.md) §4 wording |
