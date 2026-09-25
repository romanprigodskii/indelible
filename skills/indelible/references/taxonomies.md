# Taxonomies: failure modes and their treatments

Load this when classifying a miss (after the learner's account; [session-grade.md](session-grade.md)), when setting a subject's taxonomy at `teach`, and at the weekly review. The mode decides the treatment. A subject's codes live in `subject.json` `taxonomy[]`; examples below come from personas A–D.

Contents: 1 Rules for every subject · 2 Quantitative · 3 Verbal · 4 Language · 5 Code · 6 Essay and interview · 7 Revising a taxonomy

## 1. Rules for every subject

- **Account first** (Law 11). Map the one-tap menu: "slip" → test the careless conditions below; "didn't know a word" → V; "no idea" → the content mode (on a diagnostic, an untaught topic's "no idea" gets no `kind`: [measure.md](measure.md)); one line → classify from its words and the written work. With "no account", classify from the work alone, and never as C.
- **Check in this order:** not reached (time) → a word (V) → right idea, wrong form → a slip claim (test C) → the profile's content modes.
- **Careless (C) needs both:** the learner's slip account, and the same operation done right elsewhere (this sheet or a recent one). Missing either, it is not C. Careless per 10 counts only C, and a wrong idea labelled C skips its repair.
- **V and C exist in every taxonomy.** A V word used on the sheet without being defined or owned is my mistake: log an `undefined_term` defect and add the word to `sense_list` (as in [session-grade.md](session-grade.md)), and give the question no `kind`.
- **Kinds:**
  - `belief`: a wrong idea (including an unknown word). Repair sheet first; never served cold while untreated.
  - `slip`: careless or answer form. Straight onto the ladder at +1 day, no repair.
  - `shaky`: right, but on the Least-sure line (`--shaky`). Ladder at +3 days.
  - Time (unreached questions): verdict `skip`, no `kind`, no error row.
- **The `belief` text** is at most 120 characters, states the wrong idea, and never the right answer. The examples below follow that style.
- **Codes** are single capital letters stored as `mode`. Set them at `teach` from the profile's table: `ind set <subject> taxonomy '[{"code":"V","name":"a word stopped me","treatment":"…"}, …]'`. A subject spanning layers combines sets, renaming a code only if two collide. Persona A (IELTS): verbal V D E R T C, essay A S O W, and L from language.
- **Treatments are sheets,** never explanations in chat above a test (Law 2). Sheet types and check-line forms: [sheets.md](sheets.md).
- **Tell the learner the mode in plain words** (Law 10): "Question 5: the passage never says this, so the answer isn't supported. Every TRUE needs words in the passage behind it. Your other answers on that passage had them, so this is within reach. Next: a short sheet on it on Thursday; until then, copy the supporting words beside each answer."

## 2. Quantitative (maths, statistics, science calculations: persona C)

| Code | Mode | Example | Treatment |
|---|---|---|---|
| C | Careless | Wrote 0.35 for 0.53 in the last line; same subtraction right in question 4; "rushed" | `slip`. Ladder only. Ask which check would have caught it; a missing check line is the thing to fix |
| M | Method (did not know how, or a wrong method) | Divides by n for a sample standard deviation | `belief`. Repair sheet: worked case, the wrong worked example beside it, the case where both hold; one drill block; recheck at least 12 h after |
| V | A word stopped me | Didn't know what "unbiased" meant, so left it blank | `belief`. Vocabulary probe first ([measure.md](measure.md)); the word on the next theory sheet or a words sheet, and in `lexicon`; then re-serve the question type |
| F | Answer form | Gave a decimal where the question asked for a percentage to one decimal place | `slip`. A short answer-form block; the check reads the form back (units, rounding, the form asked for) |
| H | Half-answer | Found the test statistic; no conclusion in context | `slip` if the account shows they knew a conclusion was due, else `belief`. Check hint: "Did I answer every verb in the question?" |
| R | Reading to expectation | Answered the usual total-cost question; this one asked for the cost per person | `slip`. Check hint: re-read the question's key words after answering; mixed items that twist a familiar shape |
| T | Time | Questions 14–16 blank at the stop time | No error row. Check sheet size against measured pace; timed sets only after acquisition; rehearse skip-and-return in the next mock |
| P | Route | Summed seven binomial terms by hand and ran out of time | `belief` if the shorter route is unknown. Contrast sheet: both routes on one case, then "which route?" items |

## 3. Verbal (reading comprehension, verbal reasoning: persona A)

| Code | Mode | Example | Treatment |
|---|---|---|---|
| V | A word stopped me | Didn't know "albeit", so read the sentence as agreeing | `belief`. Vocabulary probe; words sheet. Words from the learner's own official misses come before any word list |
| D | Direction inverted | Read "unless" as "if", so the answer flipped | `belief` if the account shows that reading, else `slip`. Contrast pairs of direction words (unless/if, few/a few, despite/because of); check: "Read the sentence with your answer in it: same direction?" |
| E | Plausible but unsupported | Chose TRUE because it is true in real life; the passage never says it | `belief`. Check line: "Copy the words that support it"; a drill block where every answer cites its line |
| R | Rule (grammar, usage or task rule) | Wrote "informations" in a gap | `belief`. The rule on a theory sheet with a contrast pair and the case where both hold; one drill block |
| T | Time | Last passage: six answers guessed in the final two minutes | No `kind` unless a wrong idea shows. Minutes per passage; practise the skip-and-return order in timed sets |
| C | Careless | Matched iv in the margin, copied vi onto the answer line; "slip" | `slip`. Ladder; check hint: "Compare the margin with the answer line" |

## 4. Language (persona B, Spanish)

| Code | Mode | Example | Treatment |
|---|---|---|---|
| F | Form | Treats "saber" as regular in the "yo" form | `belief`. A form sheet (the pattern in whole sentences), one drill block of that form, back-translation as the check |
| M | Meaning (a known word, the wrong sense) | Reads "embarazada" as "embarrassed" | `belief`. Contrast pair with the false friend; the word joins the words ladder inside a sentence |
| O | Collocation | Pairs "decisión" with "hacer" | `belief`. Learn the whole chunk in a sentence on a words sheet; gap items on the pair |
| W | Wrong register | Used "Oye, dame la llave" with a hotel receptionist | `belief`. The same request at two registers, then a short role-play with correction after the exchange |
| L | Listening | Heard "trece" as "treinta" in a station announcement | `belief`. Minimal-pair items from audio the learner picks: answer first, then compare with the transcript |
| V | A word stopped me (never met it) | Didn't know "andén" | `belief`. Words sheet (at most 12, each in a sentence); triage as use / seen / no |
| C | Careless | Wrote "está" right in questions 2 and 5, dropped the accent in 9; "rushed" | `slip`. Ladder; back-translation check |

V is a word never met; M is a known word given the wrong meaning. Pronunciation is not scored.

## 5. Code (persona D, Rust)

| Code | Mode | Example | Treatment |
|---|---|---|---|
| S | Syntax | Writes `if x = 3` for a comparison | `belief` if the form is unknown. The learner writes what the compiler message says, in their own words, before changing anything; a short syntax block in the editor |
| O | Type or ownership model | Uses `name` after passing it by value to `greet` | `belief`. Repair sheet with a trace table (one row per line): moved vs borrowed, and a case where both compile; then a drill block the learner types |
| A | Algorithm | Loop stops at the first match, so the count is always 0 or 1 | `belief`. Trace the loop on a three-element input; predict-the-output items |
| R | Spec misread | Returned the index where the task asked for the value | `slip`. Check: one test written from the task's own words before coding |
| B | Build and tooling | Ran the program, never the tests, so the failing test never showed | `belief`. A one-page tooling card; every task ends "run the tests; copy the last line" |
| V | A word stopped me | Didn't know what "idempotent" meant in the task | `belief`. Defined on the next theory sheet; added to `lexicon` |
| C | Careless | Typed `<` for `<=` in one bound, right in the other function; "typo" | `slip`. Ladder; the check is a test that runs the other way |

Treatments are sheets, traces and questions. Never write or edit the learner's solution code (Law 12).

## 6. Essay and interview (persona A's writing; the interview profile)

| Code | Mode | Example | Treatment |
|---|---|---|---|
| A | Claim | Discussed both views, never said which the essay backs, though the task asked "to what extent" | `belief`. Write the claim in one sentence before anything else; required points listed; the model answer only after the attempt |
| S | Support | The main reason had no example or explanation after it | `belief`. Claim, reason, example frames; critique point by point |
| O | Structure | Two ideas in one paragraph; the conclusion added a new point | `belief`. Outline in three lines, then write; one-idea-per-paragraph drills |
| W | Wrong register | "Kids" and "a lot of stuff" in an academic essay | `belief`. Register contrast pairs. For second-language learners, wording is graded apart from ideas |
| T | Time | 190 words at 40 minutes; the task needs 250 | No `kind`. Timed plan-then-write drills with minutes per part |
| V | A word stopped me | Read "curb" in the prompt as "encourage" | `belief`. Vocabulary probe; words sheet |
| C | Careless | "their" for "there" twice, right elsewhere; "slip" | `slip`. Ladder; a final read-through as the check |

Model answers are only for practice prompts, after the attempt. Never write work the learner will hand in (Law 12).

## 7. Revising a taxonomy from the learner's data

The tables are starting points. Revise at the weekly review ([review.md](review.md)) once 20 or more misses have been classified since the last change:

- Count modes from `ind error list <subject>` and read the accounts.
- **Split** a code whose misses need two different treatments (for example, V into "never met the word" and "known word, a new sense here").
- **Rewrite a treatment** when errors in that mode keep failing their rechecks (2 or more fails within two weeks).
- **Add** a code when 3 or more accounts fit none.
- **Merge or drop** a code unused for 4 weeks. V and C always stay.
- Propose each change in one plain line and act on a yes: "Most of your misses this fortnight were 'the passage didn't say it'. I'd split that into two kinds so each gets its own fix. OK?"
- Log it: `ind ledger add decision --subject <s> --summary "taxonomy: split E" --why "<their words>" --check-on <date 2 weeks out> --rule "E misses not falling" --action "revert"`, then `ind set <subject> taxonomy '<new list>'` (run with `--dry-run` first).
- Old rows keep their old codes. Never re-code history.
