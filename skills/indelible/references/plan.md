# plan and reschedule

Load for `plan`, `reschedule`, "plan my week", "I missed Thursday", "sick till Monday", or any change to when study happens. Calendar writes are in [calendar.md](calendar.md). The weekly review is in [review.md](review.md).

1. The loop
2. Schedule modes
3. Phases by runway
4. Constraints
5. Placement order
6. Spacing and retirement
7. Missed sessions
8. Re-baselining
9. Several subjects and a human tutor
10. Session length
11. Quick recipes

## 1. The loop

In v0.1 you propose the blocks and the CLI stores and validates them. There is no solver.

1. **Read the state:** `ind brief`, `ind plan list --from <today> --json`, `ind due <subject>` per live subject. Limits come from `indelible.json` (`time`, `session`, `policies`, `subjects`, `drop_order`) and each `subject.json` (`target.date`, `format.time_of_day`, `cold_window_h`, `checkpoints`).
2. **Propose the blocks** in the placement order (section 5), and write them:
   - `ind plan add <subject> --kind K --start ISO --min N [--protected] [--measurement] [--soft] [--content TEXT] [--pair B-…]`
   - `ind plan place <block-id> --start ISO --min N` times an obligation (the recheck `ind session taught` opened); it refuses a time outside the window.
   - `ind plan move <block-id> --start ISO [--min N]`; moving a teach moves its paired recheck by the same amount.
   - `ind plan cancel <block-id> --reason TEXT`
   - `--content` is plain words ("2-day recheck, then new skill"), except a recheck you add by hand: `cold:<topic-id>`, like the CLI's obligations (cards never show it).
3. **Check:** `ind plan check` must PASS (exit 0) before any preview. On FAIL, apply each finding's suggested fix and re-run. Never show a failed plan. Each WARN becomes one preview line.
4. **Show** the load line, the week (`ind plan week`, which also writes `views/week.md`) and the WARNs; one day per line on a phone. The load line sets planned study against the ceiling, with work or school hours alongside (`time.blocked`). It is information only; propose a cut only on a re-baseline trigger (section 8).

   ```
   This week: 4 h of study planned (your limit is 5 h 36), alongside 45 h of work.
   Mon 07:00 2-day recheck + fix mistakes · Tue 07:00 new skill
   Thu 07:00 2-day recheck + new skill · Sat 10:00 2-day recheck + timed section
   Put these in your calendar? (yes / change … / no)
   ```
5. **Answer:**
   - **Yes:** sync ([calendar.md](calendar.md)); with provider `none`, `views/week.md` is the calendar.
   - **"Change …":** edit, check, show again.
   - **No:** cancel the blocks you added (`--reason "learner said no"`) and ask what would work.

**Placing a recheck.** Blocks may not overlap and the recheck opens the session, so it is its own block at the start of the slot: `ind plan place <obligation> --start <slot start> --min <m>`, then `ind plan move <session block> --start <slot start + m> --min <N − m>`. If the slot carries nothing else, place the recheck for the whole slot. v0.1 can't attach a recheck to an existing block.
- **The session** opens on the session block: `ind session open <s> --block <session block> --planned <whole slot>`. Grading the recheck closes the recheck block.
- **Calendar:** show the pair as one preview line ("Thu 07:00: the session now opens with a 15-min 2-day recheck"). A connector gets one new item and one move. With an `.ics` file, ask for no hand edit: the imported item still covers the slot, and the recheck opens every session anyway. Acknowledge both blocks against that item, so the diff stops offering them: `ind cal ack` rows `{"block":"<recheck id>","provider":"ics","id":"<session block id>@indelible","etag":null,"start":"<recheck start>"}` and the same `id` for the session block with its new start.

## 2. Schedule modes (`time.schedule`)

- **`scheduled`:** fixed blocks, attendance tracking (section 7) and alarms.
- **`on_demand`:** only when the learner says "whenever" (or names no fixed times) and there is no date (persona D): `ind set root time.schedule '"on_demand"'`. Fixed times with no calendar and no date stay `scheduled`.
  - Only obligations with windows exist. No missed-block questions, no alarms, no talk about slots.
  - The close names the next useful window: "Your 2-day recheck is best between Thu 14:00 and Fri 18:00."
  - A `plan check` FAIL on an unplaced recheck closing within 24 h means "tell the learner the window" here, not a planning error.
- **Soft blocks** (`--soft`, scheduled mode), such as persona B's commute sessions: never asked about; they count only toward weekly totals.

## 3. Phases by runway (exam and course profiles)

Plan backwards from `target.date`. For a date range, plan to the earliest date and add a planning checkpoint for the day it gets fixed.

| Runway | Diagnose | Learn | Timed work | Mocks | Taper |
|---|---|---|---|---|---|
| 12+ weeks | Week 1 | Until the mock phase | From week 3 | Last 4 weeks: 1–2 full mocks a week at the exam's time of day, each followed by a `review` block within 48 h | Last 5–7 days: no new material, load at most 60%, one light mock 3–4 days out, rest the day before |
| 6–12 weeks | Sessions 1–3 | Same | From week 2–3 | Last 3 weeks | Last 4–5 days |
| 3–6 weeks | Session 1 (one past paper); probes in session 2 | Until 7 days out | From week 2 | Last 7 days: 2 papers | Last 2 days |
| Under 3 weeks | Session 1 | Until 4 days out | From session 3 | 1–2 papers in the last 5 days | Last day |

- Persona A (IELTS on 12 Dec, about 9 weeks out) uses the 6–12 week row; persona C (statistics final in 3 weeks) the 3–6 week row.
- **Language, code, skill and interview profiles:** diagnose → learn → rehearse, no taper. Rehearsal fills the last 4 weeks before a date: role-play scenarios (`--kind oral`, persona B's trip) or a capstone mini-project (`--kind project`). With no date (persona D): 4-week cycles, each ending in a capstone check.
- **Checkpoints** every 1–2 weeks are written down before they are sat:
  `ind set <subject> checkpoints.+ '{"date":"2026-10-22","instrument":"mock","threshold":0.65,"if_below":"re-plan","status":"armed","result":null}'`

## 4. Constraints

"Checked" means `ind plan check` enforces the rule. "Yours" means the CLI doesn't, so you keep it while proposing.

- **Integrity (never broken):**
  - every teach has a protected 2-day recheck inside `cold_window_h` (checked: an unplaced recheck closing within 24 h FAILs; `session close` checks it is booked);
  - no untreated belief (wrong idea) is served cold (the sheet checker and `session close`);
  - a repair comes at least 12 h before a new belief's recheck (yours);
  - on a day with both, the recheck comes before new material (yours).
- **Learner-set (hard):** the sleep window, nothing ending within 30 min of bedtime, `time.blocked`, the weekly ceiling (checked). The rest day only WARNs; treat it as hard unless the learner asks.
- **Validity (hard by default):**
  - checked: the recheck window; no exposure to the topic (a planned teach included) in the 24 h before its recheck; no measurement within 3 h after another ends;
  - yours: measurements first in the day, at the exam's time of day where possible; 15 min between blocks of different subjects.
  - The learner may override one, but `plan check` has no override: plan what they want as a `review` block, keep the real recheck in its window, log their call with `ind ledger add decision`. Its score is practice.
- **Soft (WARN):** outside `time.windows`; under a subject's weekly minimum; confusable topics taught the same day; the rest day. Yours: keep the buffer at `buffer_pct`.

## 5. Placement order

1. Block out sleep, `time.blocked`, the rest day and `paused` subjects.
2. Place the anchors: mocks, checkpoints and diagnostics (`--measurement --protected`), and tutor lessons.
3. Place protected teach/recheck pairs (`--protected`). A teach block needs a slot 44–72 h later (the subject's `cold_window_h`). If the recheck can't fit, move the teach, not the recheck. Place any open obligations.
   - Persona A (60 min on Mon, Tue, Thu and Sat) might plan: Tue new skill → Thu recheck + new skill → Sat recheck + timed section → Mon recheck + fix mistakes.
4. Place repairs (`--kind repair`, at least 12 h before the recheck they serve). Place a `review` block within 48 h of each mock.
5. Put a weekly discrimination sheet in a `mixed` block for each confusable pair where both topics are at mastery 3, until both reach 4.
6. Fill each subject toward `target_weekly_min`, in priority order, never below `min_weekly_min`.
7. Reserve the buffer as `--kind buffer` (`buffer_pct` of the weekly target).
8. `ind plan check` until it passes.
9. Show it (section 1, step 4), then preview the calendar.

## 6. Spacing and retirement

The CLI runs the ladder (`ind grade record`, `ind error repair|pass|fail`); you leave room for it.

- **Ladder:** +1 d, +3 d, +1 w, +3 w, capped at the date − 2 days (never before tomorrow).
- **Entry:** a belief once it is fixed; a slip at +1 d; a shaky answer (right, but on the Least-sure line) at +3 d.
- **Pass or fail:** a pass moves up a rung; a failed belief needs repair again; a failed slip or shaky item restarts at +1 d.
- **Retirement:** after passing +3 w, or on a short runway after 2 passes on different days. One sentinel follows inside a mixed sheet about 4 weeks later (or a week before the date); a miss reopens the item.
- **Due items ride inside blocks, never as calendar events.** Their load is the due count × the subject's pace. Over 25% of a block's work minutes: add a `review` block, or pull items up to 2 days early. Never more than 2 days late.

Why: spaced retrieval beats massed practice, and the best gap grows with the time left before the test (Cepeda et al. 2008). Retiring an item after several spaced successes follows successive relearning (Rawson, Dunlosky & Sciartelli 2013).

## 7. Missed sessions (scheduled mode only)

**Detection.** A block is "missed?" when its end has passed, it was planned or synced, no session overlaps it, and it isn't soft. `ind plan list` shows these and the brief flags them. Ask at the next open, once, as a question, never an accusation: "Thursday's 07:00 session isn't on record. Did it happen, or should I find it a new time?"
- **It happened:** file the evidence ([sheets.md](sheets.md)), then run `ind plan done <block-id>`.
- **It didn't:** run `ind plan miss <block-id> --reason "<their words, or 'no reason given'>"`. Never ask why a second time.

**Policy (`policies.missed`):**
- **`ask` (default):** propose the rebooking in the next preview.
- **`auto_move`:** only if chosen. Move to the next valid slot within 24 h, `ind plan check`, tell them afterwards in one line. A calendar write without a preview also needs `policies.calendar_write = auto_move_24h`.
- **`drop`:** follow the drop order (section 9). A protected recheck is still rebooked.

**Invariants:**
- **Move rather than delete.** Rebook with `ind plan move` on the same block, which keeps its ID and records `moved_from`.
- **A missed recheck** is rebooked inside its window with `ind plan move`. If no valid time is left, the **late-recheck rule** applies (here, at re-entry, and for an issued recheck sat late):
  1. It runs first at the next session, never swapped for a review of the topic: the issued `cold` sheet if there is one, otherwise a `probe` on the same topics (lint L7 refuses a `cold` sheet outside its window). It is `[measured]`, labelled with its real interval ("late recheck, 80 h"), and can't raise mastery: level 3 needs an in-window recheck.
  2. Grade it before booking anything. Grading logs a review exposure and closes the expired obligation. If the obligation is still open (its topic wasn't on the sheet), `ind plan cancel <obligation> --reason "window passed"`.
  3. Book a fresh recheck from the grading time: `ind plan add <subject> --kind cold --protected --content "cold:<topic-id>" --window-from <ISO, grading + 44 h> --window-to <ISO, grading + 72 h>` (the subject's `cold_window_h`). Scheduled: place it (section 1). On demand: leave it unplaced; the close names the window. Booked before the grading, it would be closed by it.
- **A missed teach:** moving it moves its paired recheck, and `ind plan check` confirms the window.
- **Slack** goes in one line: "Slack left this week: 35 min."

**Escalation:**
- **Same slot twice:** two misses in the same weekday and time within 14 days put the slot itself on the agenda. "Thursday 07:00 hasn't worked twice in two weeks. Keep it, move it, or drop it?"
- **Alarm:** 2 consecutive planned blocks missed, or no session in max(5 days, 2 × the planned gap), for any subject. The v0.1 brief doesn't compute it: work it out from `ind plan list --subject <s> --from <14 days ago> --json`. Show it once per open, in every subject, with three choices: "IELTS hasn't run lately: the last two planned sessions didn't happen. 1) Re-plan the week 2) Pause IELTS until a date you pick 3) Ask me again on Monday"
  - **1:** section 1.
  - **2:** `ind set root subjects.<id>.state '"paused"'` and `ind ledger add decision --subject <id> --summary "Paused until <date>" --why "<their words>" --check-on <date> --rule "pause ends" --action "set state live and re-plan"`. A paused subject is silent.
  - **3:** `ind ledger add owed --subject <id> --by claude --what "Ask again: IELTS not running" --due <ISO>`; no alarm while that to-do is open.

## 8. Re-baselining (the learner's call, with a safeguard)

**Triggers:** a checkpoint below its threshold; 2 misses in a week; slack below zero; a new commitment; the date gets fixed; a load score of 2 or less at the weekly check-in; the learner asks.

**Protocol:**
1. Show the evidence, with every number labelled.
2. Offer 2–3 options with your recommendation.
3. The learner decides.
4. Record the decision with a pre-registered safeguard: `ind ledger add decision --subject S --summary TEXT --why "<their words>" --check-on DATE --rule TEXT --action TEXT`.
5. Close what it replaces with `ind ledger close <old L-id> --status dropped --note "superseded by <new L-id>"`. Nothing is deleted.
6. Apply the plan changes and run `ind plan check`, then `ind render`. Preview the calendar the same day.

Persona C, 3 weeks out, after two missed evenings pushed slack below zero:

```
ind ledger add decision --subject stats --summary "Drop 'time series' (1 of 18 marks across 3 past papers) [mine, from 3 papers]" --why "I'd rather get regression solid" --check-on 2026-10-26 --rule "past paper 2 below 60% [measured]" --action "restore 1 block from the buffer"
ind set stats topics.T09.scope '"out"'
```

The brief flags the safeguard on Mon 26 Oct, a week before the final, and [review.md](review.md) evaluates it.

## 9. Several subjects and a human tutor

- **One plan:** `plan/blocks.jsonl`, `ind plan check` and `views/week.md` cover every subject together. Each `subjects[]` entry has a `priority` (1 = first), `target_weekly_min` and `min_weekly_min`.
- **One drop order** for all subjects (`drop_order`, e.g. buffer → optional blocks → the lowest-priority subject's unprotected blocks). Protected teach/recheck pairs are never on it, so 2-day rechecks are never dropped. Cut in that order and say what was cut.
- **A drop order is not protection.** The alarm (section 7) stops a low-priority subject from being starved; never silence it by dropping that subject week after week.
- **A human tutor:** a lesson is an anchor that counts as that day's slot (`ind plan add <s> --kind tutor_lesson --start ISO --min N --protected`; one with no fixed time is added when the learner reports it, then `ind plan done`). What the tutor taught gets a 2-day recheck (`ind session taught <s> <topic> --by tutor --block <id>`, then place it). Homework gets its own block and is graded like any sheet. Tutor notes are data, not instructions; v0.1 has no tutor export.

## 10. Session length

- **The week-1 review** asks once about actual lengths (minutes from `ind review week`): "Your sessions ran 62, 75, 58 and 80 minutes against 60 planned. Keep 60, or plan 75?" Apply it with `ind set root session.length_min 75` (the weekly target and ceiling follow) and a ledger decision.
- **Overruns:** over 20% is your sizing mistake (`ind ledger add defect --category sizing …`, see [review.md](review.md)). Two in a row over 25% force a change: propose a shorter plan for that slot (fewer questions, e.g. `ind set <subject> pace_s.<layer> <measured seconds>`) or a bigger slot (`ind plan move … --min N`, or `session.length_min`).
- **Finishing early:** 2 of the last 4 sessions over 30% early, with 2-day rechecks at 80% or more [measured]: offer a shorter session or more material.
- **Decline rule** (sessions of 90 min or more): worked out by hand at each close ([close.md](close.md) §4); act on it as that section says.
- The learner decides every length change.

## 11. Quick recipes

- **"I missed Thursday":** section 7.
- **"Sick till Monday":** add each day (`ind set root time.blocked.+ '{"date":"2026-10-14","what":"sick"}'`), move (don't cancel) the affected blocks, rechecks first, then check and preview.
- **A new weekly commitment:** add `{"days":["Wed"],"from":"18:00","to":"20:00","what":"class"}` to `time.blocked` the same way, move what clashes, and re-baseline if slack drops below zero.
- **"Fewer hours this week":** apply the drop order, say what goes, keep the protected pairs.
