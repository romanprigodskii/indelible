# review: the weekly review

Load for `review`, "weekly review" and "how am I doing". Run it in the main conversation, never in a subagent. Any change it leads to goes through [plan.md](plan.md), and any calendar change through [calendar.md](calendar.md).

1. When
2. Run it
3. Check-in
4. Safeguards
5. Overrides
6. Hygiene and liveness
7. My own mistakes
8. Proposals

## 1. When

- **Scheduled mode:** once a week, about 10 minutes. Offer it in one line at the close of the first session of a new week if `reviews/<last week>.md` doesn't exist yet, and run it whenever the learner asks. Review the week just ended: pass `--week YYYY-Www` when the default isn't that week.
- **On-demand mode** (persona D): at the first open after 7 days or more away, show 3 lines and ask nothing that needs an answer:

  ```
  Since last time: 3 sessions · 2-day rechecks 4/5 [measured] · 2 mistakes fixed
  Due now: one 2-day recheck and 3 reviews
  Anything you'd like to change? (skipping is fine)
  ```

## 2. Run it

1. **Report.** `ind review week all` or `ind review week <subject>` (with `--week YYYY-Www` as above). It prints at most 15 lines and writes `reviews/YYYY-Www.md`. Show those lines in plain vocabulary, with the labels the CLI prints. Add no number that isn't in the output. Never join two instruments into one trend.
2. **Check-in** (section 3).
3. **Safeguards** (section 4) and **overrides** (section 5).
4. **Hygiene**, liveness and your own mistakes (sections 6 and 7).
5. **Maintenance.** Run `ind compact <subject>` for each live subject. It keeps `.bak` copies and refuses if the mistake IDs don't match up; report a refusal and don't work around it.
6. **Proposals:** 1–3 of them (section 8).

Persona A, week 42:

```
Week 42 · IELTS 4/4 sessions (238/240 min) · all closed the same day
2-day recheck 83% (10/12) [measured] · 2 of 9 wrong answers weren't on your Least-sure line
Checks written beside 94% of answers, all sheets; they caught 3 slips
Mistakes: 6 new, 4 fixed, 1 overdue · To do: register for the 12 Dec sitting (due Tue)
Proposal: move Saturday's timed section to 09:00, the exam's start time? (yes/no)
```

## 3. Check-in

Ask these one at a time. Each can be skipped.

1. "How manageable was this week, from 1 (too much) to 5 (fine)?"
2. "How has your sleep been, from 1 (poor) to 5 (good)?"
3. "Anything in the next two weeks that changes your study time?"

Then add one line, not a question, that gives back the learner's own reason from `subject.json` `target.why`: "You're doing this for the master's offer."

- **Record** the answers with `ind note append <subject> review` (the text goes in on stdin). Nothing about distress goes in: Law 13 comes first, and "off the record" keeps a statement out of the files.
- **A load of 2 or less, or a new commitment,** is a re-baseline trigger ([plan.md](plan.md), section 8).
- **A sleep score of 2 or less** leads to one proposal that protects sleep, for example moving the latest block earlier.

## 4. Safeguards

The review lists every safeguard whose `check_on` date has passed; the brief flags one on its day. For each:

1. **Evaluate the rule** against the evidence it names, labelled. Only the named instrument settles it; a practice score never settles a rule about a measured one.
2. **If it fired,** carry out the action (the plan through [plan.md](plan.md), the calendar through a preview). Then record it: `ind ledger close <L-id> --status scored --note "fired: past paper 2 52% [measured]; 1 block restored from the buffer"`.
3. **If it held:** `ind ledger close <L-id> --status scored --note "held: past paper 2 71% [measured]"`.
4. **If the evidence is missing** (the paper wasn't sat), don't guess. Book the sitting, then re-register the check:
   - `ind ledger add decision … --check-on <new date> --rule … --action …`
   - `ind ledger close <old L-id> --status dropped --note "superseded by <new L-id>"`

Tell the learner in one line: "Dropping time series held up: past paper 2 came in at 71% [measured]."

## 5. Overrides

Take the open overrides from `ind ledger list --kind override --open`. For each one whose items are now graded:

- **Compare** the learner's item prediction with the result. Score it symmetrically: your default against the learner's call.
- **Record:** `ind ledger close <L-id> --status scored --note "learner's call held: items 2 and 5 right"`.
- **Report it as what we learned about the plan.** "Your call to start with the timed section paid off: items 2 and 5 were right. I'll give that more weight." When the learner's call didn't hold, say so just as plainly, with no blame.

## 6. Hygiene and liveness

From the review output:

- **Overdue to-dos:** do it now, re-date it (add the new row, then close the old one with `--status dropped --note "re-dated"`), or drop it after a yes.
- **Sheets issued but not sat:** ask "sit it now, or drop this sheet?" A drop is `ind sheet void <subject> <id> --reason TEXT`.
- **Repeated "my mistake" categories:** see section 7.
- **Hypotheses older than 14 days** (`ind ledger list --kind hypothesis --open`): score them or drop them.
- **Liveness:** a rule or a recurring block that nothing has used for 14 days gets one question: run it, reschedule it, or delete it.
  - A **recurring block** is a weekday-and-time slot with no session done in 14 days (check `ind plan list --from <14 days ago> --json`).
    - Run it: keep it.
    - Reschedule it: move its future blocks ([plan.md](plan.md)).
    - Delete it: `ind plan cancel` each future block in that slot. The calendar items are marked cancelled, not deleted.
  - A **rule** is a subject override or an open ledger decision that nothing has exercised in 14 days.
    - Delete it: `ind ledger close <L-id> --status dropped --note "unused for 14 days"`.
    - Or remove the override with `ind set <subject> overrides …` after a yes.
  - Ask at most 2 liveness questions per review; the rest wait a week.

## 7. My own mistakes

Log a mistake the moment you notice it, in any command, not only here: `ind ledger add defect --subject S --category C --what TEXT --fix-type T --fix TEXT`.

- **Categories:** `sizing`, `floor`, `undefined_term`, `late_build`, `content_error`, `promise_broken`, `contamination`, `late_close`, `scheduling`, `misclassification`, `wrong_inference`. `session close` logs `late_close` and `promise_broken` itself.
- **The first time,** a `rule` fix is allowed: a stated rule you follow from now on.
- **A second mistake in the same category** needs a structural fix: `template`, `lint`, `script` or `planner`. The CLI refuses `rule` a second time. Fixes you can make inside the workspace:

| Category | Fix type | How |
|---|---|---|
| `undefined_term` | lint | Add the word to the subject's sense list: `ind set <s> sense_list.+ '"gist"'`. The sheet checker then demands a definition |
| `sizing` | script | Record the measured pace so budgets shrink: `ind set <s> pace_s.verbal 95` |
| `scheduling` | planner | Encode the missing constraint: `ind set root time.blocked.+ '{…}'`, or `time.windows` |
| `contamination` | planner | Mark confusable topics (`ind set <s> topics.T04.confusable_with '["T07"]'`) so the plan checker warns about same-day teaching |
| Anything needing a change to the skill | template or script | Write the exact change in `--fix`, and offer the learner the text to send to the project if they want to |

- **Tell the learner once, in plain words:** "My mistake: I used 'gist' on a sheet without defining it. Fixed: the sheet checker now flags that word."
- **In the review,** name each repeated category and the structural fix it got.

## 8. Proposals

Make one to three proposals, each a yes/no question, asked one at a time. They come from what the review found: re-baseline triggers, overruns and session length ([plan.md](plan.md), section 10), liveness, sleep and safeguards that fired.

- **Week 1** always includes the question about actual session lengths ([plan.md](plan.md), section 10).
- **Make the call:** state your recommendation, then the question.

**Carry out a yes the same day, in this order:**
1. `ind ledger add decision --subject S --summary TEXT --why "<their words>"`, with `--check-on --rule --action` whenever it changes the plan;
2. the plan changes ([plan.md](plan.md)), then `ind plan check`;
3. `ind render`, so the brief and views show the change;
4. a calendar preview ([calendar.md](calendar.md)).

**A no needs nothing written.** Don't propose the same thing again for 2 weeks unless new evidence arrives.
