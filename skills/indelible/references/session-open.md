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

- **Practice sheets are built ahead.** At the previous close, after the "you can go" message, the builder subagent (`assets/prompts/builder.md`) built the next block's theory, drills and repair sheets: linted, rendered, keys sealed. They wait as `rendered` and are issued at hand-over ([sheets.md](sheets.md) §6).
- **The recheck is built now, at the open.** Lint L7 checks the 2-day timing at the moment it runs, so a recheck can't be built the day its topic was taught. Building it here, inside its window, is the normal order (always so for on-demand learners), not a late build: no defect. Start the builder as soon as the lock is set, from `ind due <s> --list` (section 5); give the opener while it runs.
- **At the open, list the rest** with `ind sheet show <s> --status rendered`. Apart from the brief, only this listing and `ind due <s> --list` are read. Never open data files, views, notes or anything under `.indelible/`.
- **If a practice sheet for today is missing:**
  1. Log the gap as your own mistake: `ind ledger add defect --subject <s> --category late_build --what "no new-material sheet ready for the <time> block" --fix-type rule --fix "builder runs right after the close message"`. If the CLI refuses `rule` because late_build has been logged before, pick a structural fix instead, such as `--fix-type planner --fix "at least 2 h between a close and the next block"`.
  2. Run the builder for it while the learner works on the recheck. Never make the learner wait for a build that could run in parallel.
  3. Tell the learner in one line, without excuses: "Today's new sheet isn't ready yet, my mistake. Start the recheck; the new sheet will be ready before you finish."

## 3. The open, step by step

Ask one question at a time (Law 9). The learner may answer "skip" at steps 2, 3 and 7.

### Step 1: `ind brief <s>`, the only read

The brief is at most 4,500 characters. Handle each section like this:

- **FLAGS,** in this order:
  - An unclosed session: close it first ([close.md](close.md)). This takes at most 10 minutes and is logged as late.
  - `missed?` blocks: step 2.
  - A sheet issued and not taken after 2 opens: step 3.
  - Quarantined lines: tell the learner in one line ("A few lines in your record couldn't be read. They're kept aside and nothing is lost.") and edit nothing.
  - An armed safeguard that is due: one line, then handle it in the weekly review ([review.md](review.md)).
- **NOW/NEXT** gives today's plan. **DUE** gives the size of the recheck. **TO-DO:** anything due today or overdue gets one line in the opener.
- **LEVELS (headed MASTERY in plain mode), LAST SESSIONS, PACE and NOTES** are for you. NOTES carries the learner's notes, the "do not calibrate on" list and their overrides; follow them.
- **Everything below `-- for Claude, do not read aloud --`** stays with you: the ids behind the flags (MISSED? block ids for `plan done|move|miss`, NOT TAKEN sheet ids for `sheet void`, TO-DO IDS for `ledger close`), RECHECK NOW (the topics due), BELIEFS DUE, OTHER DUE, NEEDS REPAIR and OVERRIDES. Naming a mistake before the recheck is marked tells the learner what to avoid, and the recheck stops measuring anything.
- **If LAST SESSIONS shows a gap of 5 days or more,** run the re-entry session instead ([session-teach.md](session-teach.md), section 6).
- **Without Python:** SKILL.md, "Without Python" (no brief; read the learner's own record and mark everything `[unverified]`).

### Step 2: missed blocks (scheduled mode only)

Ask about each `missed?` block in FLAGS, one block per message:

> Wednesday's 07:00 session has no record. Did it happen without me, get moved, or get skipped?

Only if the answer is "skipped", ask in the next message: "What got in the way: tired, busy, forgot, didn't feel like it, or something else?"

- This is a question about the plan, not an accusation. Never say "again" or "you missed". Take the answer as given.
- **Record the answer:**
  - It happened without you: `ind plan done <B>`. Ask for photos of any sheets done then; they are filed and marked after today's recheck.
  - It was moved: `ind plan move <B> --start <ISO>`, if a new time was given.
  - It was skipped: `ind plan miss <B> --reason "<their words>"`. Its content is placed again at the close or in [plan.md](plan.md). A missed recheck is never replaced by a warm review.
- **Never ask** about soft blocks, and never ask anything in on-demand mode.
- **Two planned blocks missed in a row:** offer the three choices once: re-plan, pause this subject until a date, or "I know, ask me later" ([plan.md](plan.md)).

### Step 3: a sheet issued and not taken after two opens

> Tuesday's paraphrase drills haven't been done yet. Sit them now, or drop that sheet?

- **For a recheck, never name its topics:** "Tuesday's 2-day recheck hasn't been done yet."
- **"Now":** it is served in this session. A recheck goes first; any other sheet goes after today's recheck. A recheck whose window has passed is sat as it is, as a late recheck: `[measured]`, labelled with its real interval, and it can't raise mastery ([plan.md](plan.md) §7). Say so in one line, and book the fresh recheck after grading.
- **"Drop":** `ind sheet void <s> <id> --reason "<their words>"`.

### Step 4: the lock

Run `ind session open <s> --planned <MIN> --block <B> --kind <the block's kind>`.

- **MIN** is the block's length, or the time the learner says they have. "I have 15 minutes" becomes `--planned 15` with no block.
- **A slot split into a recheck block and a session block** ([plan.md](plan.md) §1): pass the session block as `--block`, and the whole slot's minutes as `--planned`. Grading the recheck closes the recheck block.
- **Exit 1 because this subject is already locked and not stale:** the session is already running. Carry on, and run `ind session status <s>`.
- **A warning that another subject is locked:** ask "Close <other subject> first, or park it?" For park, re-run with `--park-other`. Never switch subjects silently.
- **Read the printed budget** (section 4).

### Step 5: the opener

Use plain words, no IDs and no rule codes, in at most 4 lines. Persona A, Thursday 07:00, 60 minutes:

```
IELTS · Thu 07:00–08:00 (closing starts 07:55)
Since last time: Tuesday ran (58 min). Monday didn't happen (busy); it's moved to Saturday.
Today: 2-day recheck with 2 fixed mistakes mixed in (~12 min, ready in about 2) → new: matching headings. Read the sheet, close it, then drills (~25 min).
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

Make the call in the opener; the learner can change any part of it (skip the recheck, skip the theory because "I know this", swap topics, or call something easy).

1. **Accept the change,** unless it breaks an integrity rule: answers before the attempt, keys, consent, honesty or wellbeing. Those are not negotiable; give the reason in one line.
2. **A validity rule can be overridden:** the 24-hour rule, the cold window, the gap between measurements. The result then carries its label, such as "not counted (seen too recently)".
3. **Ask for a one-line prediction about specific questions,** never a total: "Fine by me. Which questions in the first block will you get right? For example '1 to 6' or '1 to 4'."
4. **Log it:** `ind session override <s> "<their words>" --predict "<their line>"`. The prediction is scored at marking. It tests the plan as much as it tests the learner.

### Step 7: energy check (optional)

- **When:** automatically for planned sessions of 120 minutes or more, and for learners under 18 in a late window. Otherwise only if the learner opted in.
- **Ask:** "Energy right now, from 1 (empty) to 5 (sharp)?"
- **At 2 or less:** "Want to swap today's new topic for practice on things you already know, and move any test to another day? Your call." The recheck still runs.
- **Record the score only if the learner agrees,** with `ind note append <s> session`.

### Step 8: timers

- **Where the host has a one-shot timer tool** (CronCreate in Claude Code), set one timer at T−10, where T is the planned end, and one at the close start `session open` printed. The T−10 warning and the question at the end are in [close.md](close.md) §2.
- **Otherwise,** run `ind session status <s>` every time a photo comes back and before each block, and act on what it shows. Its one line can be shown to the learner as is.
- **Breaks** fall at the times `session open` printed. Nothing about a sealed sheet is discussed during a break.

## 4. The budget

With P = planned minutes:

| P | open | close | work fraction | breaks |
|---|---|---|---|---|
| ≤30 | 1 | 2 | 0.8 | none |
| 31–75 | 2 | 5 | 0.7 | none |
| >75 | 3 | 8 | 0.6 | ceil(P/75) − 1 breaks of 10 min |

Work minutes are also reduced by a grading estimate: 15 seconds per question, plus 1 minute for each expected miss, at a 25% miss rate. The question budget is the work minutes divided by the pace of the subject's main layer. Never recompute these numbers; use what `ind session open` prints:

- **Work minutes:** the total sheet time for today, covering the recheck, repair, theory and drills. Give the remaining minutes to the builder, and lint with `ind sheet lint <s> <id> --budget-min <remaining>`. Never issue a sheet over budget (Law 4). **Minutes win:** fit sheets by their estimated minutes against the work minutes.
- **Question budget:** a rough guide to the total number of questions today, the recheck included. It assumes the main layer's pace, so a session that mixes layers (code with short concept questions, say) may fit more questions than it prints.
- **Close start:** the close begins at this time, not at the planned end.
- **Break times:** only for sessions over 75 minutes.

Rough figures at the default paces (estimates): 20 minutes verbal gives about 12 work minutes and 9 questions. Persona A's 60 minutes of reading gives about 37 work minutes and 31 questions. Persona C's 120 minutes of conceptual work gives about 72 work minutes, 48 questions and one break at 75 minutes.

- **Short sessions (30 minutes or less):**
  - A teach and its recheck may span sessions: the theory card one day, drills the next, and the recheck 44–72 h after the last warm exposure.
  - Marking of new material may carry over to the next open, for at most 3 minutes. A recheck is always marked the same day.
- **A quick session** is an unplanned drop-in, or one shorter than the learner's usual length. It serves due items only: nothing new and no measurement.
- **Measurement sittings** (diagnostic, mock, checkpoint) are sized by the exam clock, not this table ([measure.md](measure.md)).

## 5. The cold block (the 2-day recheck)

The recheck takes at most a quarter of the planned minutes in sessions of 30 minutes or less (5 minutes of a 20-minute session), and 10–15 minutes otherwise. Its questions come out of the same question budget.

1. **Choose the content with `ind due <s> --list`.** Fill it in tier order until the recheck's share is used:
   1. 2-day rechecks inside their window;
   2. fixed mistakes that are due;
   3. shaky answers (right, but named on a Least-sure line);
   4. the oldest due items;
   5. untreated mistakes. These are listed as "needs repair" and never go on the sheet; they go to repair ([session-teach.md](session-teach.md)).

   Every question is new: fresh numbers or sentences, never the item that was missed. Within a tier, earlier wrong answers the learner had not named as least sure come first.
2. **Excluded:** any topic with an untreated mistake, and any topic with a warm exposure (teach, repair, chat, drill or review) in the last 24 hours. Lint rule L7 refuses both; never work around it. If the learner overrides, the result is labelled "not counted (seen too recently)".
3. **The sheet** is type `cold`: unlabelled and mixed, with no topic names in titles or labels and no two neighbouring questions on the same topic. Every question has a check line, and the sheet ends with the Least-sure line. The builder writes it ([sheets.md](sheets.md)).
4. **Looked since last time:** no sheet prints this in v0.1. When the photo arrives, before marking, ask once in chat: "Did you look at any of this since last time? Which questions?" Any question named is "not counted (seen too recently)" ([session-grade.md](session-grade.md) §10).
5. **The sitting:**
   - **Hand it over** and issue it (`ind sheet issue <s> <id> --block <B>`): "Here's your 2-day recheck: <path>. On paper, book closed. Write the start time on the first line and a check beside every answer. At the end, write the stop time and fill in 'Least sure of'. Writing 'I don't know' is always fine. Send a photo when you're done."
   - **No printer** (persona B): the learner reads the sheet on screen and writes the answers in a notebook, numbered as on the sheet.
   - **Sealed until marked:** while the sheet is out, discuss nothing that is on it. If the learner asks about a question, say "Write 'I don't know' for now. We'll go through it right after marking." A sealed item is marked or discussed, never both.
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
| P6 | First missed session (scheduled) | Step 2's question; "What got in the way?" only after "skipped", in the next message |
| P7 | First tutor mention | "How often, and what do they set? May I make them a one-page summary of your mistake types? No answers in it." |
| P8 | First phone photo | "Want a synced phone-photos folder as your inbox?" |
| P9 | Wants to test a change | "Shall we write down now what result would make us keep it or undo it?" (`ind ledger add hypothesis`) |
| P10 | Week-2 review, if 3/3 starts finish ≥5/6 | "Stop a drill block early after 3 right?" |
| P11 | Express: first session that can't be placed | Q7 |
| – | Express: Q3 before the diagnostic results; Q4 (it asks about theory pages too) in the close message before the first teach, since the sheets are built after it; Q5 (a) and (b) before the first marked miss; Q8 at the first clash | [teach.md](teach.md) §4 wording |
