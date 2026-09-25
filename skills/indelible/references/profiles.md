# Profiles: what changes per subject type

`subject.json.profile` is set in [teach.md](teach.md) from Q1: `exam`, `course`, `interview`, `language`, `code` or `skill`. `intensity: light` can go with any of them. The laws never change by profile. What changes: the first measurement, the session blocks, the check line, what counts as progress, and the capstone.

**Contents:** 1 At a glance · 2 Check lines · 3 exam · 4 course · 5 interview · 6 language · 7 code · 8 skill and light · 9 Values to set · 10 Defaults

## 1. At a glance

| Profile | First measurement ([measure.md](measure.md) §1) | Extra blocks | Answers | Progress means | Capstone |
|---|---|---|---|---|---|
| exam | one unseen official test at the exam's time of day, if one is left after the checkpoints and final mock have theirs; else a two-part diagnostic Claude builds | timed sections, mocks, checkpoints | paper, phone photos | mastery per topic; 5 = 75%+ in a timed mock or checkpoint | final mocks, then a taper |
| course | an unseen past paper in session 1; probes in session 2 | timed past papers | paper, phone photos | as exam, on past papers | the last past papers |
| interview | 3–4 timed explanations; the required points stay in the key | explanations, timed 3-minute answers, mock panels | typed or dictated | required points covered, cold and timed | a full mock interview |
| language | 10-minute placement: 40 common words in sentences, 5 can-do prompts, 1 listening item if there is audio | words cards, speaking, chat practice corrected afterwards | typed or spoken | words owned, can-do scenarios passed | scenario role-plays |
| code | 15-minute starter task in the editor (compiler yes; docs and AI no), plus 6 concept questions | editor exercises, code reading, Parsons problems | the learner's editor | a fresh task passes hidden tests | a small project |
| skill | 10-minute placement probe | as for its main layer | as fits | a transfer task passed | a project check every 4 weeks |

Levels are computed by the CLI the same way for every profile ([measure.md](measure.md) §8). Mastery 5 needs 75%+ on a `mock` or `checkpoint` sheet, so build every capstone, scenario and transfer task as a `checkpoint` sheet, registered in `checkpoints` before it is taken. Label every result: `[measured]` on measuring sheets, `[practice]` otherwise.

## 2. Check lines by layer

Every question on `drills`, `cold`, `mixed`, `diagnostic`, `mock`, `checkpoint` and `review` sheets has a written backwards check beside the answer (lint L2). When a key word decides the answer, the check also tests the definition used against the question's words. Each sheet ends with one line: "Least sure of (question numbers): ___". There are no per-answer confidence marks. No check line on `theory`, `external`, `example`, `probe`, `triage`, `words`, `explain` or `miss-review`. Hint rules: [sheets.md](sheets.md) §3.

| Layer or form | The learner writes | Example hint |
|---|---|---|
| procedural | the answer substituted back, or the total rebuilt another way | "Put your answer back into the equation" |
| conceptual | the definition used, tested against the question's words | "Which meaning of 'range' did you use?" |
| verbal, reading | the sentence read again with the answer in it | "Read the sentence again with your word in it" |
| production | a back-translation into the instruction language | "Translate it back: is that what you meant?" |
| code | an assert or test that runs the other way | "Parse what you printed: do you get the input back?" |
| explanation | the weakest point named, then said again | "Which part would you be pushed on?" |

## 3. exam

- **Match the exam** (`format.*`): answer form, tools, reference sheet, accommodations. Extra time scales timed work and the per-question pace. Formulas appear on drill and recheck sheets only if the exam provides them.
- **Ration official material.** Each unseen official test gets one job (checkpoint and final mock first, then diagnostic if one is spare) in `materials.ration` ([sheets.md](sheets.md) §11). A test the learner has seen is never a measurement. Don't use an unseen official test for anything a question bank could cover.
- **Measurements** go at the exam's time of day where possible, first in the day, never within 3 h after another, and are sized by the exam clock, not the session budget.
- **Phases scale with the runway** ([plan.md](plan.md)): timed work from week 2–3, mocks in the last 3–4 weeks, a taper of 2–7 days (no new material, load at most 60%, rest the day before). Under 3 weeks: timed from session 3, 1–2 papers in the last 5 days, taper the last day.
- **Checkpoints** every 1–2 weeks, registered before they are taken: instrument, threshold, what happens if missed.
- **Second-language test-takers** (persona A: Portuguese first language, IELTS in English): first-language glosses on first use (`learner.gloss`); "why" answers may be drafted in the first language; content and wording are marked separately. This is not the language profile.

## 4. course

As exam, except:
- **No registration or retake questions.** Record the course's AI rule in `format.ai_policy`. Never write anything that will be handed in for a grade (Law 12); teach on parallel questions instead.
- **Weights from past papers** when there are any: topic counts across the papers, labelled `[mine, from n papers]`.
- **Theory from the learner's own textbook or notes:** an `external` sheet ("Textbook §4.2, pp. 181–188: read, then close"), then 3–5 pencil questions. It is still read and then closed.
- **Past-paper solutions** are recorded by path only. The builder copies what a key needs when it builds the sheet; the main conversation opens nothing before evidence is filed.
- **Short runway** (persona C: a statistics final in 3 weeks, 120 minutes a day): one past paper in session 1, probes in session 2, new material until 7 days out, timed papers from week 2, a 2-day taper. Long sessions get breaks and an automatic energy check.

## 5. interview

For interviews, vivas and oral exams.
- **Explanation blocks** (`explain` sheets). The prompt lists the required points (for "Why this method?": the problem, the options, the reason, the cost). Often a timed 3-minute answer, spoken through dictation or typed.
- **Capture the answer word for word** with `ind note append <s> explanations` before any comment.
- **Critique point by point:** each required point is present, partial or missing, quoting the learner's words that carried it; then one next step. Second-language wording is marked apart from content; drafting in the first language is allowed.
- **The model answer comes only after the unscaffolded attempt,** never in the same message as the prompt.
- **Recording:** each required point is one question: `right` (present and correct), `half` (partial), `wrong` (missing or wrong). `explain` sheets are practice. The measured version is a `cold` sheet with a fresh prompt of the same kind 44–72 h later; its check line: "Name the part you'd be pushed on, and say it again".
- **Mastery above 3** also needs an explanation attempt on file for the topic. The CLI doesn't track this: check `ind topic show <s>` against the dates in `notes/explanations.md` at the weekly review, and say "not yet explained" where one is missing.
- **Mock panels** in the last 2–4 weeks: `ind plan add <s> --kind mock --start ISO --min N --measurement`, timed answers only.
- **Authorship.** When the interview is about the learner's own work, help them describe their role accurately: never bigger, never smaller. Raise it once, when a claim is being drafted.

## 6. language

- **Two languages.** The target language is the one being learned (named in the subject title and goal). The instruction language (`learner.instruction_lang`, asked in Q5) carries explanations, glosses and everyday chat. Never teach a beginner through the target language alone.
- **Grammar** goes on a theory card that is read and then closed, never explained in chat above its own questions.
- **Chat conversation is a production drill with delayed correction.** Don't correct during the exchange. Afterwards give at most 5 corrections, most important first: their sentence, the fixed sentence, a one-line reason. Log it with `ind session expose <s> <topic> --kind chat`. A repeated mistake becomes an error row.
- **Speaking** through voice mode or dictation: save the transcript word for word (`ind note append <s> speaking`) and critique task done, accuracy and range. **Listening:** the learner picks the audio; comprehension questions follow on a sheet. Pronunciation is not scored; say so once.
- **Words:**
  - at most 12 new words on a sheet, each inside a sentence, never a bare list;
  - ladder: 48 h, then +3 days, +1 week, +3 weeks;
  - triage new words as use / seen / no ("If you hesitate, it isn't 'use'"); only "seen" and "no" words go on a card;
  - words that stopped the learner in real material come before any word list;
  - split long words into parts, with a check that the parts fit the meaning.
- **Words in v0.1:** each batch is one topic (layer `verbal`). Teach it on a card with every word in a sentence and a gloss, then `ind session taught <s> <topic>` books the 48-hour window. Rechecks are `words` sheets: the words blanked out of new sentences, items with origin `cold:<topic>` so marking closes the booking. Lint doesn't check a `words` sheet's timing, so confirm the window with `ind due <s> --list` first. Missed words become errors on the mistake ladder, and right words on the Least-sure line too (`ind grade record … --shaky`). For words that passed, place the later rungs by hand: `ind plan add <s> --kind words --start ISO --min N` at +3 days, +1 week and +3 weeks.
- **Sheet checker:** put grammar terms the learner must own ("preterite", "subjunctive") in `sense_list` so lint L4 checks each is defined; keep target-language vocabulary out of it. The builder uses only words the learner has met, plus that sheet's new words.
- **Progress:** words owned (right on a words recheck 3 weeks or more after first meeting them, `[measured]`) and can-do scenarios passed (order a meal, ask directions, 3 minutes of small talk). Hours start from published guided-hour ranges, `[published]`, then switch to the learner's own pace, `[mine]`.
- **Phases:** diagnose, learn, then scenario role-plays (`--kind oral`) in the last 4 weeks before a date. No taper.
- **Persona B** (phone, no printer, 20 minutes a day): HTML or Markdown sheets read on the phone; answers typed.

## 7. code

- **The learner types every line of their own solutions.** Never write the learner's solution code or edit their exercise files (Law 12). Asked "why won't this compile?": ask what the message says, point to the line and the idea, give the smallest hint. Never paste a fix.
- **Scaffolds at levels 0–1,** open to every learner (worked examples help novices, Kalyuga, 2007; Parsons problems gave similar learning in less time, Ericson, Margulieux & Rick, 2017):
  - worked code on an `example` sheet: a similar case, read and then closed, never the current task;
  - code reading and trace tables, one row per line and per loop pass;
  - Parsons problems: put given lines in order;
  - fading: full example, then completion, then writing alone.
  Someone who has never written and run a program (Q3) starts with a first-program on-ramp before any debugging question.
- **"No scaffolds" is a LOCKED override,** recorded only when the learner asks for it, in their own words: `{"rule":"R40","value":"no scaffolds","why":"<their words>","date":"YYYY-MM-DD","locked":true}` in the teach draft, or later with `ind set <s> overrides '<the full list>'`. Once locked, neither Claude nor a mid-session request turns scaffolds back on; only a weekly review changes it.
- **Exercises** are `drills` or `cold` sheets with layer `code`. Each item gives the task, the function signature and one or two public examples; the learner creates the files and types everything in their own editor. The builder puts the reference solution and the hidden tests in the key (the answers file's `solution` field); neither is shown before evidence is filed.
- **Evidence:** the learner's source and their compiler or test output: `ind scan ingest <s> <sheet> <files>`, or one text file with `--typed <file>`.
- **Marking:** after `ind key open`, copy the learner's files to a temporary folder outside their project, add the hidden tests, run them with a time limit, then read the code. Record a verdict per question. The learner's files are never changed. A time limit that works everywhere (macOS has no `timeout`; on Windows use `py -3`), run in the copy's folder:
  ```
  python3 -c "import subprocess, sys; sys.exit(subprocess.run(sys.argv[1:], timeout=60).returncode)" cargo test
  ```
  A run that hits the limit ends with `TimeoutExpired`: record it as a failed test, never as a pass.
- **Rechecks:** a fresh variant of the task; compiler allowed, docs and AI not (`"tools": "compiler"` in the sheet spec).
- **Capstone:** a small project at the end of each 4-week cycle (persona D: a command-line tool that reads a CSV file, with tests). Block time with `ind plan add <s> --kind project --start ISO --min N` (on demand: agree the time when the learner comes); mark it as a `checkpoint` sheet with hidden tests.
- **Pace:** 300 seconds per question (`pace_s.code`).

## 8. skill and light

- **skill:** a practical skill with no exam. A 10-minute placement probe; blocks follow its main layer; 4-week cycles, each ending in a transfer task (the skill used in a new situation, marked as a `checkpoint` sheet).
- **`intensity: light`** (interest only; persona D is `code` and light, on demand): no mastery numbers unless asked; checkpoints optional; 2-day rechecks stay but are short (about 5 questions); the weekly review is 3 skippable lines.
- Light never switches off a law: answers stay sealed, rechecks stay cold, and practice is never shown as measurement.

## 9. Values to set

At `teach`, put these in the draft for `ind subject add --from` ([teach.md](teach.md) §7). Later, change one value at a time with `ind set <s> <path> <json>`; a change to the method is a weekly-review decision ([review.md](review.md)).

| Profile | Values |
|---|---|
| exam | `format.*` from Q2 (A: `minutes` 165, `answer_form` "short", `tools` "none", `time_of_day` "09:00"); `materials.sources` and `.ration`; `checkpoints` from the phase plan; `taxonomy` from the verbal, quantitative or essay tables that fit (A: verbal plus essay, [taxonomies.md](taxonomies.md) §1); `cold_window_h` stays `[44,72]` unless the runway is very short or long (range 20–96) |
| course | as exam, plus `format.ai_policy`; `reference_sheet` true when the course gives one; weights from past papers; `taxonomy` quantitative for persona C |
| interview | topics mostly layer `verbal` or `production`; `taxonomy` from the essay and interview table |
| language | `format.answer_form` "typed"; one topic per grammar point and per words batch; `sense_list` holds grammar terms only; `taxonomy` from the language table |
| code | `format.answer_form` "code", `format.tools` "compiler"; topics layer `code`; `taxonomy` from the code table (S O A R B V C), never the generic default; any locked `overrides` |
| skill | `intensity` "light" when it is for interest only; `taxonomy` from the table of its main layer |

Every profile sets `taxonomy` in the draft: the subject file's default (V M R F C T) is only a placeholder.

## 10. Defaults (a readback row only when it applies)

These stand for every skipped question ([teach.md](teach.md)), shown as visible defaults.

- **Week:** 60 min on 4 days, longest 90; ceiling 1.4 × weekly. **Windows:** weekdays 17:00–21:00, weekends 10:00–18:00; the day's first block is the clearest. **Sleep:** 23:00–07:00; no late cutoff unless named.
- **Rest day:** one, the learner's pick, may be none. **Spare time:** 15% of blocks. **Commitments:** none; asked again at weekly reviews.
- **Missed session:** ask at the next open (on demand: never). **Running long:** a warning 10 min before the end, the extend-or-close question at the end, one extension up to 15 min ([close.md](close.md) §2). **Breaks:** 10 min every 75, in sessions over 75.
- **Calendar:** none; writes only after a preview and a yes; reminder 15 min before.
- **Recheck:** aim 48 h, window 44–72 h. **Drill blocks:** 3–8 questions of one kind, default 6.
- **Answers:** exam, course: paper plus phone photos; language: typed or spoken; code: the editor. No printer. Typed answers go in a file, never chat. **Photos:** outside macOS, JPEG (iPhone camera "Most Compatible").
- **Sheets:** the renderer `doctor` verified; access layout on request ([sheets.md](sheets.md) §13).
- **Feedback:** tone B; plain words, no codes or IDs; first-language glosses on first use. **Age:** 18+.
- **History:** local git, never uploaded. **Energy check:** automatic for 120+ minute sessions and under-18s late in the day.
