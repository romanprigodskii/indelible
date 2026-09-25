# teach: the onboarding interview

For a new workspace or a new subject. Ask only what the first plan needs, show the plan, read it all back, write nothing before "yes". Load [profiles.md](profiles.md) once the profile is known; its §10 holds the defaults used for every skipped question.

**Always the learner's call** (on express, as visible defaults): session length and frequency (Q6); days, times, clearest time, sleep (Q7); fixed commitments (Q8); the calendar and reminder (Q10, under the plan preview, never before it).

**Contents:** 1 Budget · 2 Stage 0 · 3 Opener · 4 Questions · 5 Preview and Q10 · 6 Readback · 7 Writes · 8 Welcome · 9 Express, second subject. Questions skipped here are asked later, one at a time: [session-open.md](session-open.md) §6.

## 1. Budget and cards

- **8 minutes** target, 15 at most. **At most 12 replies**, all counted: Q1–Q8 + preview + readback = 10 (9 when the first message answers Q1); Q9 and the authorship follow-up add 1 each; express = 4–5. Counter: "(2 of 8)", then "(plan)", "(last step)". Nothing else needs a reply: the scope map is a readback row; an `.ics` import is confirmed at the next open.
- **One card per message:** the wording below, numbered options one per line, the default marked, a "why" of at most 12 words. A card is one topic with a few parts and counts as one question (Law 9). Replies: a number, free text, "skip", "defaults" (for the rest), "why?". AskUserQuestion may carry up to 3 parts of one card (Q5 a–c; Q6; Q10 and reminder), at most 4 options each.
- **Free text fills many fields,** the first message included: echo the parse atop the next card; skip what is answered. At 10 replies: "I'll use defaults for the rest; you'll see them in a moment." Never skip the preview or readback.
- **No writes before the readback "yes":** no `ind init`, no `ind set`, no calendar item, no file.

## 2. Stage 0: silent scan

1. Say once: "I'll run a small script that keeps your study record as files in a folder on your computer. It sends nothing over the internet." Run `ind doctor --json` (it only reports, and may make a one-page test PDF in a temporary folder). No Python 3.9+: SKILL.md, "Without Python or a lasting folder".
2. **Folder:** the current one only if empty, outside git and not cloud-synced; else `~/Study` (`%USERPROFILE%\Study`). In Cowork, a new folder inside the shared folder. A temporary sandbox only after saying it will be lost (SKILL.md, setup step 1). Never change an existing `CLAUDE.md`.
3. **Calendar, by inspection only:** match your tool list against [calendar.md](calendar.md) §2; loading a deferred schema is not a call. **No connector calls, no account reads.**
4. **Note:** a multiple-choice tool, a narrow screen, the learner's language (interview in it), the time zone, `py -3` on Windows, any permission prompt (readback row 12).

## 3. Opener

Persona A wrote "I need a 7.5 in IELTS Academic by December for my master's offer. Can you set me up and keep me honest?", which answers Q1:

```
Got it: IELTS Academic 7.5 · December · for a master's offer.
I'll set this up in about 8 minutes: up to 7 more short questions, each with a default ("skip" takes it). Then a two-week plan for you to check, and a short diagnostic: I teach from measurement, not guesses.
In a hurry? Say "just start": 3 questions, then the plan.
Found: Python 3.12 · PDF sheets · time zone Lisbon · Google Calendar (I won't read or write it unless you say so).
(1 of 7) When is it? Are you registered, and by when must you be? …
```

"Found" lists only what exists ("no calendar connected (a file you import works too)"). Nothing parsed: end with Q1, "(1 of 8)".

## 4. Questions

**Q1 · Goal, why, success** (no default): "What do you want to learn or pass, why does it matter to you, and what result would count as success? One line is enough, like 'IELTS Academic 7.5 for a master's offer' or 'enough Spanish to get around on a trip'."
Sets the profile (`intensity: light` if for interest; unsure: add "Is there an exam at the end?" to Q2), the id and `target.*`. No success named: exam, the target plus a floor one step lower; otherwise draft a capstone (B: "order a meal, ask directions, 3 minutes of small talk"; D: "a command-line tool that reads a CSV file, with tests").

**Q2 · Date and format** (feeds `target.date`, `format.*`):
- exam: "When is it (or the window, and what fixes it)? Are you registered, and by when must you be? How many attempts, and what does a retake cost? Format: length, sections, marking, answer form, calculator, reference sheet? What time of day? Any accommodations, like extra time or a computer?" Skipped: public format in ≤5 lines, `[published]`; unknown registration: a to-do due in 3 days.
- course: "When is the final, and what's allowed (formula sheet, calculator)? Any past papers? Will any of this be handed in for a grade, and what does your course allow AI to do?" Record the AI rule; never write graded work.
- interview: "When is it, who's on the panel, and what will they probe?"
- language, code, skill: "Is there a date you're aiming at, like a trip or a project? If not, I'll plan in 4-week cycles with a check-in at the end of each."

**Q3 · Where you are now:** "Where are you now, in your own words? Any real evidence, like a score report or a practice test you've taken? And was earlier work in this subject done with a lot of help (AI, a tutor, a group)? I ask only so I don't mistake it for your starting point; the diagnostic decides anyway."
Code adds "Have you ever written and run a program yourself?"; language, "Could you order a meal, ask directions and chat for two minutes today: yes, with effort, or no?". Estimates and assisted work go under "Do not calibrate on". **Authorship follow-up**, only if substantial help is reported on work they will present as theirs: "For the parts you'll present as yours, which decisions did you make yourself? I'll help you describe your role accurately: never bigger, never smaller." Keep the answer verbatim.

**Q4 · Materials:** "What do you already have: official past papers or practice tests (how many haven't you seen yet?), question banks, textbooks or course notes, an official syllabus (a link or a file)? Any book whose notation or pages I should use for the theory? If any come with answers, I'll keep those sealed until marking."
Feeds `materials.sources`, `.ration` (shapes: [sheets.md](sheets.md) §11) and the theory source. Answer files: path only, never opened here.

**Q5 · About you:** "Three quick ones. (a) Are you 18 or over? If not, say 'under 16' or '16–17': it only changes sleep, load and reminder defaults. (b) Is your first language different from the one you'll study in? Then I'll explain hard words in it the first time they appear, and you may draft 'why' answers in it. (c) Which feedback suits you, for a wrong answer on question 7?
A: '7 is wrong: you used the mean where the question asks for the median. Redo it with the median.'
B: '7 is wrong: mean used where the question asks for the median. That's a definition slip, and your method was right. Next: two median questions.'"
Ask (b) only if the languages may differ; language profile: "Which language should I explain things in?". indelible is meant for adults; the under-18 defaults are a safety net, not a target audience. Under 18: sleep ≥8.5 h, nothing ending after 22:00 on school nights unless chosen, school plus study against the ceiling; under 16: no connector without a guardian's agreement. Feeds `learner.*`.

**Q6 · How long, how often:** "How long should a normal session be: 15–20, 30, 45, 60, 90, or 120–150 minutes? On how many days a week? And what's the longest you'd ever want one to run?"
Weekly = length × days. ≤30 min: a sheet and its drills may fall on different days. ≥120 min: breaks, plus a daily 15-minute review offered as an if-then plan.

**Q7 · When:** "Which days and times usually work, or shall I look at your calendar for free time (read-only)? When is your head clearest? Roughly when do you sleep on work or school nights, and on free days? Anything you want at a fixed time, like 'Saturday mornings for longer practice'? Or say 'whenever'."
Read the calendar only on a yes (busy times, 14 days). Plan into named times, never leftover gaps. "Whenever" (no fixed times) with no date: `time.schedule` `on_demand`.

**Q8 · Fixed commitments:** "What's fixed or coming up that I should plan around: work or school, training, classes or a tutor, travel, other exams? And, if you like: what has made you stop studying something before?"
Feeds `time.blocked`, `time.rest_day`; a tutor queues P7 ([session-open.md](session-open.md) §6). The obstacle becomes one if-then plan in their words ("If work gets busy, then I keep the 2-day rechecks and shorten the rest"; Gollwitzer & Sheeran, 2006).

**Q9 · Priorities** (second subject or several goals): "Which matters most right now, what outranks all of it, and what gives way first when a week gets tight?" Default: nearest deadline first; 2-day rechecks never give way.

## 5. Plan preview, then Q10

One message, preview first. Two weeks (to the date if ≤3 weeks away): week 1 from [measure.md](measure.md) §1 and §11, week 2 a skeleton. `ind plan check` runs only after the writes, so apply [plan.md](plan.md)'s hard rules by hand. Measurements and new material go first, in the clearest window. If a recheck can't fit its window, move the teach. With a date, add a **rough-fit line** ([measure.md](measure.md) §9, every topic at mastery 0 until the diagnostic).

Persona A (set up Sun 11 Oct; wedding on Sat 17 Oct; both official tests kept for a checkpoint and the final mock, so the diagnostic is Claude-built):

```
(plan) Your first two weeks: IELTS Academic · ~4 h a week · 60-min sessions · exam Sat 12 Dec (62 days)
           Week 1                                   Week 2
Mon 07:00  Diagnostic, part A                       First skill: read the sheet, close it, drills
Tue 07:00  Diagnostic, part B                       Second skill
Thu 07:00  Your results, short checks (40 min)      2-day recheck, then third skill
Sat 10:00  Wedding: no session                      2-day recheck, then timed reading (practice)
Load: 2 h 40, then 4 h, plus work · ceiling ~6 h · Sundays off · 1 spare block
Rough fit [mine]: up to ~65 h if you start from zero; ~33 h planned by 12 Dec. The diagnostic shows what you already own; if it still doesn't fit, you choose what gives.
No new skill in week 1: its 2-day recheck would land on the wedding or your day off.
To do: register for the 12 Dec sitting by Tue 20 Oct.
Change anything in plain words ("no Mondays", "45-minute sessions"), or say "looks good".

Want these in your calendar? I found Google Calendar. Is that where study sessions should go?
1) Yes, and ask me before each batch of changes (recommended)
2) Yes, and you may also move a missed session within 24 h and tell me afterwards
3) Give me a file to import (.ics): made once; later changes come as a short list
4) No calendar: tell me what's next when I open Claude (default)
Which calendar or list, if not your main one? Reminder: 15 minutes before (default), 5, 30, or none?
```

- **Narrow screen (B):** one day per line; week 2 in one line.
- **On demand (D):** no slots, only windows ("2-day rechecks: best 44–72 h after each new topic; I'll say when one is open"), then "With no fixed times, nothing goes in a calendar: 4) no calendar (default), or name fixed times."
- **No connector:** options 3 and 4, plus "If you use Google Calendar or TickTick, connect it later and say 'sync my calendar'." Apple Calendar (C): 3.

The Q10 answer maps to `calendar.*` and `policies.*` as in [calendar.md](calendar.md) §2, step 6.

## 6. Readback: the only write gate

At most 12 lines, rows that apply; "more" shows the other defaults. Persona A:

```
(last step) Here's what I'll set up. Correct? (yes / change a number)
1 Goal: IELTS Academic 7.5, no band under 7.0, for your master's offer · Sat 12 Dec 2026 · register by Tue 20 Oct
2 Now: about 6.0 by your estimate · the diagnostic decides (the September practice test doesn't count)
3 Materials: Cambridge 18 (tests 1–2 seen: practice only) · 2 unopened official tests: a checkpoint on 14 Nov, the final mock on 21 Nov
4 What's tested: the published format, 4 parts [published] · I'll list the question types as topics; say if any is missing
5 Week: 60 min × 4 days ≈ 4 h · ceiling ~6 h · rest day Sunday · 1 spare block
6 When (Lisbon time): Mon/Tue/Thu 07:00–08:15, Sat 10:00–12:00 · sleep 23:30–06:30 · Sat 17 Oct kept clear
7 Calendar: Google, a calendar called "Study" · I ask before each batch · reminder 15 min before
8 Missed session: I ask next time; 2-day rechecks are always rebooked · Running long: a warning 10 min before the end, then close or one short extension
9 Answers: read on screen, write on paper, send phone photos (no printer needed)
10 Feedback style B · plain words · hard words explained in Portuguese the first time
11 Files: ~/Study (new folder) · local history with git, never uploaded
12 One-time step, for fewer prompts: type /permissions and allow Bash(python3 *indelible.py*) (it allows any python3 command that mentions indelible.py)
```

Row 12 only if a permission prompt appeared during this setup (Windows: `Bash(py -3 *indelible.py*)`). "change N": apply, show changed rows, ask again. "yes": §7 at once.

## 7. What teach writes (after "yes" only)

Exit 2: stop, say so in one line. Exit 1: fix what it names, go on.

1. `ind init <path> --pointer`, then `ind doctor` (records the renderer).
2. `ind set root <path> <json>` per answer that differs from the default (`ind schema indelible`). First the `session.*` numbers, keeping length ≤ `max_min` at every step (C: `max_min` 150, then `length_min` 120; B: `length_min` 20, then `max_min` 30), then `days_per_week`: the CLI derives the weekly target and ceiling.
3. Draft the subject in the `subject.json` shape ([profiles.md](profiles.md) §9) at `<ws>/.indelible/<id>-draft.json`, including the `taxonomy` for the profile ([taxonomies.md](taxonomies.md)), `materials.sources` and `materials.ration`, and `checkpoints` from the phase plan; `ind subject add <id> --title "<title>" --profile <profile> --from <draft>`; remove the draft.
4. Known topics: `ind topic add <id> T01 --name "<name>" --layer <layer>` (the scope from readback row 4; [measure.md](measure.md) §2). Weights and the out-of-scope list: `ind note append <id> scope`.
5. Week 1 in full, week 2 as a skeleton: `ind plan add ielts --kind diagnostic --start 2026-10-12T07:00+01:00 --min 60 --protected --measurement --content "Diagnostic, part A"` (on demand: none). Then `ind plan check`; fix every FAIL, say if a session moved.
6. To-dos and safeguards: `ind ledger add owed --subject ielts --what "Register for the 12 Dec sitting" --due 2026-10-20T20:00+01:00 --by learner`, and one ledger decision mirroring each checkpoint ([measure.md](measure.md) §12).
7. Outside the generated markers: subject `CLAUDE.md` "Learner notes" (why, if-then plan, authorship answer, fixed-time wishes, "prefers few questions"), "Do not calibrate on"; root "About the learner". Longer: `ind note append <id> onboarding`.
8. `ind render all`.
9. Calendar 1–2: the sync in [calendar.md](calendar.md) §3; the "yes" covers this batch only if it matches the preview. 3: `ind cal ics <ws>/plan/ics/study.ics --from <first day> --to <last day>` and how to import it; at the next open, ask once whether it's in, then `ind cal ack` ([calendar.md](calendar.md) §5).
10. If row 11 stands: `git init` in the workspace (the shipped `.gitignore` keeps keys, photos, typed answers and the inbox out); no remote.

## 8. Welcome card and the diagnostic

```
IELTS Academic · target 7.5 (floor 7.0) · Sat 12 Dec 2026 (62 days)
Week: ~4 h · 60-min sessions · clearest before work
Me: I name mistakes exactly and tell you the next step. "I don't know" is always an accepted answer.
You: turn up, work on paper, write the check beside each answer, name what you're least sure of, and tell me honestly what happened.
What I keep: your answers, sheets and marks, all in ~/Study. Say "what do you keep?" to see it.
Next time: open Claude in ~/Study and say "start ielts".
Building your diagnostic now (about 3 minutes). Part A is set for Mon 07:00.
```

- Offer "part A now" only inside a learner window. First `teach` only: "While I build sheets, don't expand my tool calls or thinking: they can contain answers."
- The build is outside the budget. Instrument and blueprint: [measure.md](measure.md) §1 and §3. The builder (`assets/prompts/builder.md`) gets the blueprint only (topics, part, counts, formats, minutes, tools), runs `sheet new`, `lint` and `build`, and returns one line. Issue the sheet at hand-over, when part A starts: `ind sheet issue <subject> <sheet> --block <block>`.

## 9. Express path and second subject

**Express** ("just start", a first message like "please don't ask me a million questions", or anyone rushed): Q1 (unless the first message answers it), Q2's date, Q6, preview with Q10, readback: 4–5 replies. Opener:

```
Got it: Rust. I'll keep questions to a minimum: 3 now, then a plan; everything else gets a default you can change any time.
(1 of 3) What's it for, and is there something you'd like to build? If not, I'll pick a small project.
```

The rest are visible defaults ([profiles.md](profiles.md) §10); a skipped question is asked alone when its trigger fires ([session-open.md](session-open.md) §6). Record "prefers few questions" under Learner notes. While it stands:
- the scope map is shown as a statement ("Say if anything here is missing"), never a question;
- Q4 (asked later) includes the theory-source part; tone stays B unless the learner raises it (Q5 drops part c);
- the 10-minute warning is the only word on time: no question follows, and the session closes unless they say "extend" ([close.md](close.md) §2).

**Second subject:** no `init`; reuse windows, sleep, commitments, calendar, tone, age, language, folder. Ask Q1–Q4, Q6 if it differs, and Q9. Preview marks clashes; readback shows new or changed rows. Writes: §7 steps 3–9, then `ind set root subjects.<id>.priority <n>` (also `target_weekly_min`, `min_weekly_min`) and `ind set root drop_order '<list>'`.
