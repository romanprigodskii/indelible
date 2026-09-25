# method: the reasons behind the rules

Load this when a learner asks why a rule exists ("why wait two days?"), wants to change a default at `review`, or a contributor proposes a rule change. It explains; it never overrides the laws in SKILL.md.

## Contents

1. The six principles
2. Classes and evidence grades
3. The rule table
4. Why a written check replaced confidence marks
5. Where the defaults bend
6. Honest limits
7. Explaining a rule to a learner
8. Changing a rule
9. References

## 1. The six principles

The README's method (keep the two in step), with the mechanism each relies on.

1. **Read it, then close it.** Theory comes on a sheet that is read and put away before the drills. People judge their learning too high while the answer is in view (Koriat & Bjork, 2005), and expecting an open book lowers later closed-book recall (Agarwal & Roediger, 2011). What matters is recall with the source closed, not paper as such.
2. **One thing at a time, then all mixed up.** Teaching drills come in blocks of one question type; anything that measures mixes topics and hides their names. Blocks help first contact. Mixing makes the learner choose the method, which the exam demands and a heading gives away (Rohrer et al., 2020; Brunmair & Richter, 2019).
3. **Nothing counts until it survives 48 hours.** Performance during learning is a poor guide to learning (Soderstrom & Bjork, 2015). Retrieval after a gap, repeated across days, is what lasts (Roediger & Karpicke, 2006; Cepeda et al., 2006; Rawson et al., 2013).
4. **Check backwards, in writing.** Beside every answer, a check that runs the other way, including the definition used. Each sheet ends with one line: "Least sure of: ___". See section 4.
5. **Every miss goes in the error log** and returns after 1 day, 3 days, 1 week and 3 weeks. Errors need corrective feedback (Pashler et al., 2005; Metcalfe, 2017), and corrected errors made with confidence can come back (Butler, Fazio & Marsh, 2011), so each one returns on a spaced schedule until it has survived several returns.
6. **You do the work.** The smallest hint that unblocks, never an answer the learner could reach. Generating beats reading (Slamecka & Graf, 1978; Bertsch et al., 2007), explaining exposes gaps (Chi et al., 1994; Rozenblit & Keil, 2002), and unrestricted AI answers can lower later unaided performance (Bastani et al., 2025).

Where the method came from, always stated exactly so:

> Developed with one learner over about four weeks; not a controlled study. The cited literature is why we expect the principles, not the parameters, to generalise.

## 2. Classes and evidence grades

| Class | Meaning |
|---|---|
| core | Always on. Rests on strong literature, integrity, or one of the six principles; changes only in a new skill version with a CHANGELOG line. Its numbers are defaults |
| default | On, with a stated range. Set at `teach`; changed at `review` as a dated decision. A learner may lock one (`overrides[].locked`) so it can't change mid-session |
| opt | Off unless the learner chooses it |

| Grade | Meaning | Plain words for a learner |
|---|---|---|
| [lit-strong] | Replicated experiments or meta-analyses back the principle | "well studied" |
| [lit-mixed] | Research backs the mechanism, with limits or mixed results | "supported, with limits" |
| [one-learner] | Observed while the skill was developed; never tested | "tried in practice, not proven" |
| [design] | An engineering choice that keeps the system cheap, checkable or honest | "how the tool works" |
| [integrity] | Honesty, consent, safety or valid measurement | "a fairness rule" |

A parameter (48 hours, six per block, the ladder's days, 12 words per sheet) is [one-learner] or [design] even when its principle is [lit-strong].

## 3. The rule table

IDs are stable, so `overrides[].rule` in `subject.json` can name one (for example R36). Never show an ID or a grade code to a plain-vocabulary learner.

| ID | Rule, in plain words | Class | Grade | Key citation |
|---|---|---|---|---|
| R1 | Measure before teaching; plan from measurement, not self-report or old homework | core | [lit-strong] | Simonsmeier et al., 2022 |
| R3a | An answer given with the explanation in view is practice, never evidence | core | [lit-strong] | Koriat & Bjork, 2005 |
| R3b | Theory on its own sheet (or named book pages), read, then closed; nothing taught in chat right above its own test | core | [lit-mixed] | Agarwal & Roediger, 2011 |
| R4 | Same-day scores are practice; mastery moves only on a 2-day recheck or a measurement | core | [lit-strong] | Soderstrom & Bjork, 2015 |
| R5 | Every new skill comes back cold, on fresh questions, and that recheck is protected in the plan | core | [lit-strong] | Cepeda et al., 2006; Rawson et al., 2013 |
| R5 window | Aim for 48 hours, inside 44–72 | default | [one-learner] | Cepeda et al., 2008 |
| R6 | A wrong idea gets a fix sheet before it comes back cold, at least 12 hours before | core | [lit-strong] | Pashler et al., 2005; Metcalfe, 2017 |
| R7 | Nothing on a topic in the 24 hours before its recheck, which opens the session; a sealed question is marked or discussed, never both | core | [integrity] | |
| R8 | No answer before a real attempt; keys open only after the attempt is filed | core | [integrity] | Bastani et al., 2025 |
| R9 | Every word on a sheet is defined there, already owned, or published by the exam | core | [integrity] | Abedi & Lord, 2001 |
| R11 | One labelled box per answer, start and stop times, one Least-sure line per sheet | core | [design] | Butler, Karpicke & Roediger, 2008 |
| R12 | A worked concrete case before the definition; at mastery 0–1 the worked example comes first, then fades | default | [lit-strong] | Renkl & Atkinson, 2003 |
| R13 | Each theory sheet lists what it stands on, and missing ground comes first | default | [lit-mixed] | Simonsmeier et al., 2022 |
| R15 | A sheet fits the minutes left; an over-budget sheet is refused | default | [design] | |
| R16 | Every session has a planned end, a 10-minute warning and at most one capped extension | core | [integrity] | |
| R17 | Close inside the session; no "later" without a dated to-do | core | [integrity] | Gollwitzer & Sheeran, 2006 |
| R20 | The learner's account comes before any label, and an "I don't know" is always accepted | core | [integrity] | |
| R21 | Each miss gets a failure mode, and the mode picks the fix | default | [design] | |
| R23 | Every miss comes back until it has survived several spaced returns | core | [lit-strong] | Rawson et al., 2013 |
| R23 ladder | Back after 1 day, 3 days, 1 week and 3 weeks, capped before the deadline | default | [lit-mixed] | Latimier et al., 2021 |
| R24 | Every number carries its label; two instruments never share a trend | core | [integrity] | |
| R28 | Calendar changes only after a preview and a yes; move rather than delete | core | [integrity] | |
| R29 | Sleep is protected: nothing in the sleep window or within 30 minutes of bedtime | core | [lit-strong] | Mazza et al., 2016 |
| R31 | Claude's own mistakes are logged; a repeat in one category forces a structural fix | core | [design] | |
| R34 | Claude makes the call; the learner can override it, predicting specific questions | core | [lit-mixed] | Patall et al., 2008 |
| R36 | Teaching drills in blocks of one question type (3–8, default 6), with a stop after question 3 if two fail | core (one type) / default (size) | [lit-mixed] | Carvalho & Goldstone, 2014 |
| R38 | Explaining it back is a test: captured word for word, critiqued, model answer after | core (interview, verbal) | [lit-strong] | Bisra et al., 2018 |
| R39 | Hard words glossed in the first language the first time they appear | default | [lit-mixed] | Abedi & Lord, 2001 |
| R40 | The learner writes every line of their own solutions; worked code and line-ordering puzzles at mastery 0–1 | core | [lit-mixed] | Ericson et al., 2017 |
| R41 | A written backwards check beside every answer, including the definition used | core | [one-learner] | section 4 |
| R43 | A plan change carries a dated safeguard: a check date, a rule and an action | core | [design] | |
| R47 | Anything that measures mixes topics and hides their names | core | [lit-strong] | Rohrer et al., 2020 |
| R48 | Easily confused topics are learned apart, then mixed weekly once both are owned | default | [lit-strong] | Brunmair & Richter, 2019 |
| R49 | Distress stops the study frame | core | [integrity] | |
| R50 | The learner owns the data; nothing is deleted without a preview and a yes (a `forget` command comes in v0.2) | core | [integrity] | |
| Law 10 | Feedback names the error, states the standard, says it is within reach, gives the next step; no person-level praise | core | [lit-mixed] | Yeager et al., 2014 |
| breaks | One 10-minute break per 75 minutes in long sessions | default | [lit-mixed] | Biwer et al., 2023 |
| if-then | One if-then plan for the obstacle the learner names | default | [lit-strong] | Gollwitzer & Sheeran, 2006 |
| early exit | Leave a block after 3 right answers | opt (off) | [one-learner] | Rohrer & Taylor, 2006 |
| auto-move | Move a missed block within 24 hours without asking | opt | [design] | |

## 4. Why a written check replaced confidence marks

Graded [one-learner]. An earlier version asked for a confidence mark beside every answer. The skill now asks for a written backwards check beside every answer and one closing line per sheet, "Least sure of: ___". The reasons were observed during development, not tested:

- **Friction.** A mark on every answer costs a moment each time, and learners stop filling it in. A half-filled record measures compliance, not doubt.
- **Doubt fires on the wrong thing.** Unease tends to attach to arithmetic, while the costly errors are confident misreadings of a definition: reading "per person" as "per group", or "excluding tax" as "including tax". A "sure" mark beside those hides exactly the errors that matter.
- **A written check catches what re-solving replays.** Re-solving in your head repeats the same reading of the question, and so the same slip. A check that runs the other way (the answer put back in, the total rebuilt, the definition used written out and tested against the question's words) puts a misreading on paper.
- **One line keeps the useful part.** Naming a few questions separates known doubts from surprises. Named questions never count toward mastery, and right-but-unsure ones come back, where feedback helps most (Butler, Karpicke & Roediger, 2008). Wrong answers not named are the confident errors: their accounts come first and they return first, the job confidence marks were meant to do.

What the literature says: errors made with high confidence are corrected more readily after feedback (Butterfield & Metcalfe, 2001; Metcalfe, 2017), but some return (Butler, Fazio & Marsh, 2011), hence the ladder. Rating confidence can itself change performance, in different directions for different people (Double & Birney, 2019). No study compares written backwards checks with per-answer ratings, which is why R41 is [one-learner]. `ind stats` reports check coverage, check catches and the share of wrong answers not named on the Least-sure line, so the trade can be tested on more learners.

## 5. Where the defaults bend

- **Six per block is a ceiling, not a target.** Extra same-type questions add little later (Rohrer & Taylor, 2006). Blocking helps when categories differ a lot, mixing when they are easily confused (Carvalho & Goldstone, 2014); blocking can win for word lists (Brunmair & Richter, 2019).
- **The ladder's shape is a convenience.** Expanding gaps do no better than equal ones (Latimier et al., 2021), and the best gap grows with the time left before the test (Cepeda et al., 2008). Hence the deadline cap and a per-subject recheck window (`cold_window_h`).
- **Worked examples first, for novices only.** The advantage reverses as expertise grows (Kalyuga, 2007), and struggling first then being taught also works (Sinha & Kapur, 2021). A stuck learner gets a worked example on a separate sheet, never the answer in chat (Koedinger & Aleven, 2007).
- **A same-day failure is real evidence;** only same-day success can't show mastery.
- **Hypercorrection is shown mostly on facts.** A wrong procedure also needs a contrast with a wrong worked example (Durkin & Rittle-Johnson, 2012), which fix sheets include.
- **"Careless" needs two things:** the learner's slip account and the same step done right elsewhere.
- **Predictions are per question, never totals.** [one-learner]: in the lab, estimates of a total can be better calibrated than confidence in single items (Gigerenzer et al., 1991).

## 6. Honest limits

- **A skill cannot physically stop the model** from breaking one of its rules. Three structural properties do the work: `ind sheet build` requires a lint PASS; `ind key open` refuses until the attempt is filed; `ind brief` flags anything the last session skipped, and SKILL.md deals with it first.
- **On the learner's machine they can be bypassed** (a key file opened directly, a failed check ignored); only a hosted platform could prevent that.
- **Claude writes most questions and keys, and some will be wrong.** They stay `[unverified]`, and a challenged mark is settled from the record (Law 11).
- **Few questions per topic make noisy levels.** Mastery 0–5 is coarse, and a diagnostic is triage, not a verdict.
- **The sentence in section 1 is the whole claim.** Nothing in this repository reports an efficacy result.

## 7. Explaining a rule to a learner

Answer "why?" in two or three plain sentences: the reason, what it protects, and which part can change. No IDs and no grade codes; use the plain words in section 2.

```
Why wait two days? If you get it right two days later, with nothing looked at in between, it has really stuck. Right after the lesson the explanation is still fresh, so a good score then doesn't tell us much. The two days can change at the weekly review; the recheck itself stays.
```

```
Why no "sure / not sure" beside each answer? People stop filling it in, and the mistakes that cost most are the ones you felt sure about. A check written beside each answer catches those, and one closing line, "Least sure of", covers the rest.
```

## 8. Changing a rule

- **Core rules** change only with a new skill version and a CHANGELOG line, on a [lit-strong] or [integrity] basis or a change to the six principles.
- **Defaults** change per learner at `review`: `ind ledger add decision --subject S --summary TEXT --why "<their words>" --check-on DATE --rule TEXT --action TEXT`, then `ind set` for the value, and the subject's `overrides` list for a rule-level change ([review.md](review.md)).
- **A rule that failed as prose becomes a mechanism:** a checker rule, a schema field, a template feature or a planner check (R31).
- **A proposal names its grade** and the data that would reverse it. Every example uses personas A–D. No real learner's data, and no trend that joins two instruments.

## 9. References

*JEP*: *Journal of Experimental Psychology* (*LMC*: Learning, Memory, and Cognition). One line per first author.

- Abedi & Lord (2001), *Applied Measurement in Education*.
- Agarwal & Roediger (2011), *Memory*.
- Bastani et al. (2025), *PNAS*.
- Bertsch et al. (2007), *Memory & Cognition*.
- Bisra et al. (2018), *Educational Psychology Review*.
- Biwer et al. (2023), *British Journal of Educational Psychology*.
- Brunmair & Richter (2019), *Psychological Bulletin*.
- Butler, Fazio & Marsh (2011), *Psychonomic Bulletin & Review*; Butler, Karpicke & Roediger (2008), *JEP: LMC*.
- Butterfield & Metcalfe (2001), *JEP: LMC*.
- Carvalho & Goldstone (2014), *Memory & Cognition*.
- Cepeda et al. (2006), *Psychological Bulletin*. Cepeda et al. (2008), *Psychological Science*.
- Chi et al. (1994), *Cognitive Science*.
- Double & Birney (2019), *Frontiers in Psychology*.
- Durkin & Rittle-Johnson (2012), *Learning and Instruction*.
- Ericson, Margulieux & Rick (2017), *Koli Calling* (computing education conference).
- Gigerenzer, Hoffrage & Kleinbölting (1991), *Psychological Review*.
- Gollwitzer & Sheeran (2006), *Advances in Experimental Social Psychology*.
- Kalyuga (2007), *Educational Psychology Review*.
- Koedinger & Aleven (2007), *Educational Psychology Review*.
- Koriat & Bjork (2005), *JEP: LMC*.
- Latimier, Peyre & Ramus (2021), *Educational Psychology Review*.
- Mazza et al. (2016), *Psychological Science*.
- Metcalfe (2017), *Annual Review of Psychology*.
- Pashler et al. (2005), *JEP: LMC*.
- Patall, Cooper & Robinson (2008), *Psychological Bulletin*.
- Rawson, Dunlosky & Sciartelli (2013), *Educational Psychology Review*.
- Renkl & Atkinson (2003), *Educational Psychologist*.
- Roediger & Karpicke (2006), *Psychological Science*.
- Rohrer & Taylor (2006), *Applied Cognitive Psychology*. Rohrer et al. (2020), *Journal of Educational Psychology*.
- Rosenshine (2012), *American Educator*.
- Rozenblit & Keil (2002), *Cognitive Science*.
- Simonsmeier et al. (2022), *Educational Psychologist*.
- Sinha & Kapur (2021), *Review of Educational Research*.
- Slamecka & Graf (1978), *JEP: Human Learning and Memory*.
- Soderstrom & Bjork (2015), *Perspectives on Psychological Science*.
- Yeager et al. (2014), *JEP: General*.
