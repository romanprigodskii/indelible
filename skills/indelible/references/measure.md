# Measure: diagnostics, probes, mocks and checkpoints

For `diagnose`, `mock`, checkpoints and week 1 of a new subject. Diagnose before teaching: levels come from measurement, never from self-report or earlier work. Sheet mechanics (builder, check-line forms, lint, evidence): [sheets.md](sheets.md). General grading: [session-grade.md](session-grade.md). Miss classification: [taxonomies.md](taxonomies.md).

Contents: 1 Instrument · 2 Scope map · 3 Two-stage diagnostic · 4 Sitting · 5 Scoring · 6 Results card · 7 Probes · 8 Levels · 9 Hours and feasibility · 10 Topic order · 11 Week 1 · 12 Mocks, rationing, checkpoints

## 1. Choose the instrument

| Situation | Instrument | Labels |
|---|---|---|
| Exam, an unseen official test left over once the checkpoints and final mock have theirs (§12) | That test at the exam's time of day, plus a 10-minute vocabulary and floor `probe` | `[published]` test, `[measured n=…]` result |
| Exam, no official test to spare (A: two unopened, kept for a checkpoint and the final mock) | Two-stage Claude-built `diagnostic` (§3) | `[mine]`, `[measured n=…]` |
| Course final with an unseen past paper (C) | That paper in session 1; probes ride in session 2 | `[published]`, `[measured n=…]` |
| "Never studied it" | 10–15-minute floor `probe`; teaching starts in session 2 | `[mine]` |
| Language (B) | Placement `probe`: 40 high-frequency words, each in a sentence; 5 can-do prompts (typed or voice); 1 listening item if the learner has audio | `[mine]` |
| Code (D) | 15-minute capstone in the learner's editor (compiler allowed; no AI, no docs) as a one-item `diagnostic`, plus a 6-item concept `probe` | `[mine]` |
| Interview | A `diagnostic` of 3–4 timed explanations; the required points stay in the key | `[mine]` |
| Skill or interest | 10-minute placement `probe` | `[mine]` |

- Before any official or past paper, ask: "Have you seen any of this paper before, even part of it?" A seen paper is practice, never a measurement.
- Official items are registered by pointer (`origin: official:<source>`, text like "Test 2, questions 1–13"), with the official answers sealed as the key. Never copy official item text into a record.
- Code: the learner types every line. File the source and the saved compiler or test output with `ind scan ingest`.

## 2. Scope map

1. The official syllabus or course outline is the boundary: in scope, out of scope. With neither, draft the map from the learner's materials (contents pages, past papers) and label it `[mine]`.
2. Weights: published if they exist; else counted across the learner's past papers and labelled `[mine, from n papers]`; else equal.
3. One topic = one teach block plus a 10–15-minute recheck. Most subjects have 6–20.
4. Show the map without asking a question: at `teach` it is one readback row ("What's tested: …; say if any is missing"); elsewhere at most 8 lines ending "Say if anything here isn't on your exam, or is missing." Go on without waiting; a later correction becomes `ind topic add` or `ind set <subject> topics.<T>.scope '"out"'`.
5. Record each in-scope topic with `ind topic add <subject> T01 --name "…" --layer procedural --weight 0.15 --floor T00 --confusable T05`, and the out-of-scope list plus the weight source with `ind note append <subject> scope`.

## 3. The two-stage diagnostic

Brief the builder subagent with a blueprint only (topics, part, counts, formats, minutes, tools); items and answers never enter the main conversation.

- **Part A:** for every in-scope topic, one floor item (what it stands on) and one core item.
- **Part B:** exam-level items, only for topics with both Part A items right, enough for at least 4 questions per topic across both parts (the minimum for 3p). Build it after Part A is graded. This is the adaptive stop: nobody sits a long paper they mostly fail.
- **Sittings:** each part splits into ceil(part minutes ÷ the session's work minutes) sheets, all taken within 72 hours of the first. The parts are one measurement: one block when they fit, otherwise consecutive days.
- **Re-diagnosis** uses a parallel form (new items, same blueprint). A sealed sheet is never edited or re-issued.

Item rules (lint L2, L3 and L9 enforce the first three):
- Unlabelled and interleaved: no topic name in titles or labels, no two adjacent items on one topic. Per-topic counts are uneven and never stated.
- One labelled blank per question, each with a check line. For a definition: "write the definition you used and test it against the question's words".
- Item 0 records the start time; the last line records the stop time and "Least sure of: ___". No per-answer confidence marks.
- The rules box says "I don't know" is always an accepted answer.
- Mixed formats: compute, find the error, reverse the question, which rule applies, a one-line "why", and the exam's own answer form. Form, tools and accommodations match `subject.json.format`.
- Two questions per topic hinge on a key term (the Part A core item and one Part B item). Every other item says what it means in plain words, so a word failure shows apart from a concept failure. Topics that stop after Part A get the second from the vocabulary probe (§7).
- Multiple choice: the CLI applies no chance correction, so each topic needs at least 4 constructed-response questions (answer written before any options are seen).

## 4. The sitting

- **When:** the learner's clear window, first block of the day, the exam's time of day where possible, never within 3 hours after another measurement. Book it with `ind plan add <subject> --kind diagnostic --start ISO --min N --protected --measurement` (or `--kind mock`, `--kind checkpoint`); `ind plan check` fails a 3-hour clash.
- **How:** paper, closed book, no notes, only the exam's tools. Accommodations apply; extra time scales the clock.
- **Size:** the exam clock (or the part's minutes) plus 10–15 minutes to record. Exempt from the question budget; no breaks the exam doesn't have.
- **Open:** `ind session open <subject> --planned N --block <B> --kind diagnostic`, then hand the sheet over and issue it: `ind sheet issue <subject> <id> --block <B>`. No teaching, and no hints before evidence is filed.
- **Say once:** "This is triage, not a verdict. A few questions per topic give a rough picture, and we'll measure again. 'I don't know' is always an accepted answer." To a question mid-sitting: "Write your best try or 'I don't know'; we'll look after marking."
- **Overrides** (late, tired, soon after another test): `ind session override <subject> "<their words>" --predict "<items>"`, and state the confound beside the result ("taken 1 h after another test").

## 5. Scoring

1. **Evidence first:** `ind sheet sat <subject> <id> --start HH:MM --stop HH:MM`, then `ind scan ingest <subject> <id> <photos>` (or `--typed FILE`, or `--transcript -` for a chat photo you transcribed). Only then `ind key open <subject> <id>`.
2. **Between Part A and Part B,** give verdicts only; explain nothing on a topic going into Part B.
3. **Per question:** verdict `right`, `half`, `wrong`, `dont_know` (wrote "I don't know") or `skip` (blank); check `filled`, `missing` or `caught`; `least_sure` from the closing line.
4. **Accounts before classifying,** one miss at a time, unnamed wrong answers first (wrong and not on the Least-sure line): "Question 7: what happened? 1) slip 2) didn't know a word 3) no idea 4) write one line". Any language is fine. Cap at about 5 minutes per paper; the rest get "no account", never counted as blanks.
5. **Classify** with the subject taxonomy. Give `kind` only for a specific wrong idea (`belief`) or a slip. "No idea" or "I don't know" on an untaught topic gets no `kind`: teaching covers it.
6. **Record:** write the grades file (`ind schema grades`), then `ind grade record <subject> <id> --from grades.json`. No `--shaky` on a diagnostic; use it on mocks and checkpoints.
7. **Claude-built keys can be wrong.** Say "that doesn't match my answer", check the scan and key, and if the answer is defensible, mark it right and log a `content_error` defect (`ind ledger add defect`).
8. **Compute:** `ind topic show <subject>` (levels with basis) and `ind stats <subject>` (careless per 10, unnamed-wrong %, check coverage, pace). Count per-topic fractions from the grades file against the item topics in `<subject>/.indelible/specs/<id>.json`. Then `ind render <subject>`.

## 6. Results card

At most 12 lines, plain words, no IDs. Open with what the learner owns; label every number.

```
Diagnostic, parts A and B [mine · measured n=38]
Already yours: probability rules 4/4 · z-scores 4/5
Next: confidence intervals 1/4 · hypothesis tests 1/4 · regression 2/4
Not tried yet: chi-square (both blank); a short check next session
4 of 9 wrong answers weren't on your Least-sure line: those come back first
Checks beside 34 of 38 answers; 2 answers changed after a check failed
Time 96 of 110 min · 2 "I don't know" (both accepted answers)
Needs about 48 h at your pace [mine]; you have about 38 h. Three options below.
```

No praise beyond the evidence. End with the next step.

## 7. Probes (sessions 2–3)

- **A skipped topic is not an unknown topic.** Blanks often come from labels, time or nerves. Each topic whose evidence is mostly blanks gets 2–3 unlabelled items in one mixed 10–15-minute `probe`, taken within 48 hours of the results. A pass sends the topic to the back of the teach queue; a miss confirms it.
- **Vocabulary probes.** For each "a word stopped me" miss, and each term-hinged miss whose plain-worded twin was right, one line, cold: "In question 6, what does 'unbiased' mean here?" At most 10 per `probe`. Fix the word (the words box of the next theory sheet, a `words` sheet, or the subject `lexicon` via `ind set`) before the topic is re-taught.

## 8. Levels

Computed by the CLI (`ind grade record`, `ind topic recompute`), never typed. The learner sees "mastery 0–5".

| Level | Evidence |
|---|---|
| 0 | None, or the latest measurement under 25% |
| 1 | Latest measurement 25–74% |
| 2 | 75%+ on practice on some day |
| 3p | 75%+ on diagnostic, mock or checkpoint questions, at least 4 of them; becomes 3 after a cold pass within 14 days |
| 3 | 75%+ on a 2-day recheck inside the window, no exposure in the prior 24 h |
| 4 | A second cold pass of 75%+, at least 7 days after the first |
| 5 | 75%+ on the topic in a mock or checkpoint after reaching 4 |

- Least-sure questions never count toward a level, even when right. A cold fail under 50% drops the topic to 2.
- To confirm a never-taught 3p topic: a short mixed practice set, logged with `ind session expose <subject> <topic> --kind review`, then its 2-day recheck inside the window.

## 9. Hours needed and feasibility

- **Base:** Σ over in-scope topics of (target level − current level) × step hours. Target 4 by default (5 comes from mocks); 3p counts as 3. Step hours: 1.5 h procedural, 2.5 h any other layer.
- **Language:** start from published guided-learning hours per CEFR level (Cambridge English's guideline: about 180–200 hours from zero to A2) `[published]`, then the learner's own pace.
- **Add** each mock (exam minutes plus 60 minutes of review) and the buffer (`time.buffer_pct`).
- **Recalibrate** once two topics have a cold pass: step hours become the learner's own time from first teach to first cold pass, per level step.
- **Available:** planned study minutes from today to the date, minus blocked dates. Every hours figure is `[mine]`.
- **When:** a rough fit at `teach`, with every topic at mastery 0 (one preview line; it overstates the need), then the real verdict on the results card.
- **Verdict:** comfortable (needs 80% of available or less), tight (80–100%), or plainly "needs 48 h, you have 38 h". The 80% line is mine too.
- **If it doesn't fit,** one numbered question with three cuts: 1) drop the lowest-weight topics; 2) add hours up to the weekly ceiling (the only time the ceiling is re-asked); 3) move the date or the target. Log the choice: `ind ledger add decision --subject <s> --summary "…" --why "<their words>" --check-on DATE --rule "…" --action "…"`.
- **Adding hours** (cut 2): `ind set root session.days_per_week <n>` or `session.length_min`; the weekly target follows. Run it with `--dry-run` first: a ceiling that was never set explicitly is re-derived and can rise past what the learner agreed, so set `time.weekly_ceiling_min` to the agreed ceiling in the same step. With one subject, also `ind set root subjects.<id>.target_weekly_min <new weekly target>`, or the week view keeps the old target.
- **No date (D):** no verdict; say what fits in the next 4-week cycle.

## 10. Topic order

Rank by gap × weight × the chance of a cold pass within a week (high when every floor topic is owned). Then:
- floor topics before what stands on them;
- skip-probe topics wait for their probe; a V miss gets its word fixed first;
- never-taught topics before polishing owned ones;
- confusable topics not on the same day while being learned; once both reach 3, a weekly mixed "which applies?" sheet until both reach 4 ([plan.md](plan.md));
- the first topic should give an early cold pass.

Log the order and its reason as a ledger decision whose `--check-on` is the first checkpoint.

## 11. Week 1 by session length

| Day | 30 min or less (B) | 45–75 min (A) | 120 min or more (C) |
|---|---|---|---|
| 1 | Placement probe (10 min) and results | Diagnostic part A | Part A; break while Part B is built; Part B; results |
| 2 | Theory card for topic 1 (read, then closed) | Part B, results, probes | Probes, then first teach (theory closed, drills) |
| 3 | Drills for topic 1 | First teach | Second teach |
| 4 | — | — | 2-day recheck for day 2, then third teach |
| 5 | 2-day recheck on topic 1 (44–72 h after drills); theory card for topic 2 | 2-day recheck for day 3, then second teach | 2-day recheck for day 3, then a timed set |
| 7 | 3-line check-in | Week-1 review (15 min) | Week-1 review |

Code, and on-demand learners (D), whatever they come for: session 1 is the capstone `diagnostic` plus the concept `probe`, with results; session 2 the first teach (code has no Part B); from then on each session opens with any recheck whose window is open. Each recheck is an obligation with a window, never a slot.

## 12. Mocks, rationing and checkpoints

**Mocks** (exam profile; how many and when, by runway: [plan.md](plan.md)):
- Exam conditions (clock, time of day, tools, accommodations), first in the day, in a block of exam length plus 15 minutes. No recheck before it: that day's rechecks go 3+ hours later, or the next day inside their window.
- If no window fits the whole exam, sit one section at a time; section scores are their own series.
- One trend line per instrument family (official, Claude-built, section). Never join mock numbers to diagnostic or recheck numbers.
- Within 48 hours, a `review` block per miss: account, repair, one fresh item, labelled practice. On official items the learner writes a why-line and a "now" answer before any reveal (`miss-review` sheet). A mock miss's recheck comes at least 12 hours after its repair.

**Rationing official material** (entry shape: [sheets.md](sheets.md) §11):
- Each unseen official unit gets one job and a date: the checkpoints and the final mock first, a diagnostic only from what is left. Persona A: `ind set ielts materials.ration.+ '{"unit":"official test 1","job":"checkpoint","date":"2026-11-14","status":"assigned"}'`, then official test 2 as the `final mock` on 2026-11-21.
- A unit already seen is never a measurement: practice, labelled `[practice]`.
- Don't use an unseen official test for anything a question bank could cover (drills, topic practice, words).
- Using a unit reserved for a later job needs the learner's override, logged with an item prediction.

**Checkpoints** (every 1–2 weeks with a date; end of each 4-week cycle without one):
- Pre-register before the sitting, never after (at `teach`, in the subject draft): `ind set <subject> checkpoints.+ '{"date":"2026-11-14","instrument":"official test 1, reading","threshold":"30 of 40","if_below":"two review blocks replace new material for 2 weeks","status":"armed","result":null}'`.
- Mirror it as a safeguard so the brief flags it: `ind ledger add decision --subject ielts --summary "Checkpoint: official test 1, reading" --why "<their words>" --check-on 2026-11-14 --rule "below 30 of 40" --action "as if_below"`.
- After grading: set `status` and `result` (`ind set <subject> checkpoints.<index>.status '"passed"'`), close the row (`ind ledger close <L-id> --status scored --note "…"`), and carry out `if_below` as written. A threshold changes only by a new decision made before the next sitting.
