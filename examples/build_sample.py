#!/usr/bin/env python3
"""Rebuild the synthetic sample workspace, using only the real indelible CLI.

    python3 examples/build_sample.py            # writes examples/sample-workspace
    python3 examples/build_sample.py --out DIR  # writes somewhere else

The learner is persona A from evals/fixtures/persona-a.json: an invented person,
not based on anyone real. Every passage, answer, account and answer key below is
made up for this sample.

How it runs, so that nothing touches your own files:
- everything happens in a new temporary folder, which is removed at the end;
- HOME (and USERPROFILE) point at a folder inside it, so ~/.indelible is never read
  or written, and the workspace lives at <temporary HOME>/Study (shown as ~/Study);
- INDELIBLE_NO_BROWSER=1, so no browser is started, and every sheet is built with
  --format md and --format html, so typst is never run either;
- INDELIBLE_NOW is set for every command, so the record reads as if it happened on
  the dates below;
- the CLI is started with this Python, as `indelible.py --workspace <ws> <command>`.

What Claude would write with its own tools in a real session (the builder's spec and
answers files, the grades files, the calendar results file and the learner-owned
lines of the two CLAUDE.md files) is written here directly, at the paths the skill's
references give. Every data file is written by the CLI.

The timeline (Europe/Lisbon, UTC+01:00 in October):
    Sun 11 Oct 18:00  onboarding: init, settings, subject, 4 topics, two weeks of blocks,
                      a to-do and a checkpoint safeguard, the .ics file; part A is built
    Mon 12 Oct 07:00  diagnostic part A: issued, sat, typed answers filed, marked
                      (one wrong idea, one slip, one "I don't know", one half)
    Mon 12 Oct 08:05  the theory and drills sheets for Tuesday are built ahead
    Tue 13 Oct 07:00  first skill: theory sheet read and closed, then one drill block;
                      the 2-day recheck is placed on Thursday 07:00
    Thu 15 Oct 07:00  "now" for a reviewer (INDELIBLE_NOW=2026-10-15T07:00+01:00)

At the end, the top-level CLAUDE.md gets the template's <skill> placeholder back in place
of the script's full path on this machine, every file is checked for paths from this
machine, and the workspace is copied to the output folder without the .bak copies, the
write lock and the workspace .gitignore (a real workspace keeps its keys and answers
out of git; this sample commits them on purpose, and they are all synthetic).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CLI = REPO / "skills" / "indelible" / "scripts" / "indelible.py"
DEFAULT_OUT = HERE / "sample-workspace"
SAMPLE_NOW = "2026-10-15T07:00+01:00"
REAL_HOME = os.path.expanduser("~")   # checked for: no file in the sample may contain it

SUBJECT = "ielts"
DIAG = "ielts-diagnostic-01"
THEORY = "ielts-headings-01-theory"
DRILLS = "ielts-headings-01-drills"

# Left out of the copy: backup copies, the write lock, empty folders (git keeps none).
SKIP_NAMES = {".gitignore", "write.lock", ".DS_Store"}
SKIP_SUFFIXES = (".bak",)


# ==========================================================================
# The learner's settings (persona A)
# ==========================================================================

ROOT_SETTINGS = [
    ("learner.l1", "pt"),
    ("time.sleep", {"bed": "23:30", "wake": "06:30"}),
    ("time.rest_day", "Sun"),
    ("time.windows", [{"days": ["Mon", "Tue", "Thu"], "from": "07:00", "to": "08:15"},
                      {"days": ["Sat"], "from": "10:00", "to": "12:00"}]),
    ("time.blocked", [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "from": "09:00", "to": "18:00", "what": "work"},
                      {"date": "2026-10-17", "what": "wedding"}]),
    # Option 3 at onboarding: a file to import, so no calendar service is involved.
    ("calendar.provider", "ics"),
    ("calendar.target", "Study"),
]

SUBJECT_DRAFT = {
    "target": {"goal": "IELTS Academic 7.5", "why": "master's offer",
               "success": "7.5 overall, no band under 7.0", "date": "2026-12-12", "floor": "7.0"},
    "format": {"minutes": 165, "answer_form": "short", "tools": "none", "reference_sheet": False,
               "time_of_day": "09:00", "accommodations": None, "ai_policy": None},
    "taxonomy": [
        {"code": "V", "name": "a word stopped me", "treatment": "vocabulary probe; words sheet"},
        {"code": "D", "name": "direction inverted", "treatment": "contrast pairs of direction words"},
        {"code": "E", "name": "plausible but unsupported", "treatment": "check line copies the supporting words"},
        {"code": "R", "name": "rule (grammar, usage or task rule)", "treatment": "theory sheet with a contrast pair, one drill block"},
        {"code": "T", "name": "ran out of time", "treatment": "minutes per passage; skip-and-return in timed sets"},
        {"code": "C", "name": "careless slip (slip account, same step right elsewhere)", "treatment": "ladder only; compare margin and answer line"},
        {"code": "A", "name": "essay claim", "treatment": "claim in one sentence first"},
        {"code": "S", "name": "essay support", "treatment": "claim, reason, example frames"},
        {"code": "O", "name": "essay structure", "treatment": "three-line outline, then write"},
        {"code": "W", "name": "wrong register", "treatment": "register contrast pairs"},
        {"code": "L", "name": "listening", "treatment": "answer first, then compare with the transcript"},
    ],
    "materials": {
        "sources": [
            {"what": "Cambridge IELTS 18", "path": None, "answers": False, "seen": "tests 1-2"},
            {"what": "Two official practice tests (unopened)", "path": None, "answers": True, "seen": None},
        ],
        "ration": [
            {"unit": "official test 1", "job": "checkpoint", "date": "2026-11-14", "status": "assigned"},
            {"unit": "official test 2", "job": "final mock", "date": "2026-11-21", "status": "assigned"},
        ],
    },
    "checkpoints": [
        {"date": "2026-11-14", "instrument": "official test 1, reading", "threshold": "30 of 40",
         "if_below": "two review blocks replace new material for 2 weeks", "status": "armed", "result": None},
    ],
}

TOPICS = [
    ("T01", "Matching headings", "reading", []),
    ("T02", "True, false or not given", "reading", []),
    ("T03", "Task 1 overview", "production", []),
    ("T04", "Paraphrase", "verbal", ["T01"]),
]

# Week 1 in full, week 2 as a skeleton (teach.md section 7, step 5).
BLOCKS = [
    ("mon", "diagnostic", "2026-10-12T07:00+01:00", 60, ["--protected", "--measurement"], "Diagnostic, part A"),
    ("tue", "teach", "2026-10-13T07:00+01:00", 60, ["--protected"], "Results, then the first new skill"),
    ("thu", "repair", "2026-10-15T07:00+01:00", 60, [], "2-day recheck first, then the mistakes from the diagnostic"),
    ("mon2", "teach", "2026-10-19T07:00+01:00", 60, ["--protected"], "Fix mistakes, then a new skill"),
    ("tue2", "teach", "2026-10-20T07:00+01:00", 60, ["--protected"], "New skill"),
    ("thu2", "teach", "2026-10-22T07:00+01:00", 60, ["--protected"], "2-day recheck, then a new skill"),
    ("sat2", "long", "2026-10-24T10:00+01:00", 90, [], "2-day recheck, then timed reading (practice)"),
]

ROOT_ABOUT = """- This is a synthetic sample learner (persona A in `evals/fixtures/persona-a.json` of the indelible repository), made up for reviewers. Not a real person.
- First language Portuguese; studies in English. Works 9 to 6 on weekdays in Lisbon.
"""

SUBJECT_NOTES = """- Why: a master's offer that needs IELTS Academic 7.5.
- Clearest early in the morning, before work.
- Wants Saturdays for the longer timed practice.
- If work gets busy, then keep the 2-day rechecks and shorten the rest rather than skipping a week.
"""

SUBJECT_DO_NOT_CALIBRATE = """- The September practice test at home: words were looked up during it.
- The self-estimate of about 6.0.
"""


# ==========================================================================
# Sheets (what the builder subagent would write; all synthetic)
# ==========================================================================

TFNG_LABEL = "Write T (true), F (false) or NG (not given):"
TFNG_CHECK = "Underline the passage words your answer rests on."


def ask(ask_id, label, hint=None):
    a = {"id": ask_id, "label": label, "check": hint is not None}
    if hint:
        a["check_hint"] = hint
    return a


def item(n, topic, layer, op, text, asks):
    return {"n": n, "topic": topic, "layer": layer, "op": op, "origin": "new", "text": text, "asks": asks}


DIAG_SPEC = {
    "v": 1, "id": DIAG, "type": "diagnostic", "subject": SUBJECT, "title": "Diagnostic, part A",
    "est_min": 15, "tools": "none", "answer_form": "short",
    "items": [
        item(1, "T02", "reading", "true-false-not-given",
             "Passage: The Harwick ferry leaves the harbour twice a day, at 07:00 and at 16:00. On foggy "
             "winter afternoons the second crossing sometimes waits until the fog lifts.\n\n"
             "Sentence: The ferry leaves the harbour three times a day.",
             [ask("1a", TFNG_LABEL, TFNG_CHECK)]),
        item(2, "T01", "reading", "main-idea",
             "Paragraph:\n(1) The town of Eastmere changed a great deal after its railway station closed in "
             "1965. (2) Within five years, most of the shops on Station Road stood empty. (3) Younger "
             "families moved away to find work, and the primary school lost half of its pupils.",
             [ask("2a", "Number of the sentence that carries the main idea:",
                  "Read the other two sentences: do they sit under yours?")]),
        item(3, "T04", "verbal", "swap-word",
             "Sentence: The bridge over the river was closed for repairs last spring.",
             [ask("3a", "One word that could replace 'closed' and keep the meaning:",
                  "Read the sentence again with your word in place of 'closed'.")]),
        item(4, "T03", "production", "describe-trend",
             "A shop's table shows the bicycles it sold each month from January to June: "
             "40, 55, 70, 85, 90, 120.",
             [ask("4a", "One sentence on what the monthly numbers did over the six months:",
                  "Read your sentence against the first and the last number.")]),
        item(5, "T01", "reading", "pick-heading",
             "Paragraph: Every spring, volunteers in the village of Lowden close the lane beside the pond "
             "to cars for two weeks. At dusk they carry the frogs that are crossing the lane over to the "
             "water in buckets, and they write down each one. Last year they carried more than 3,000.\n\n"
             "Headings:\nA. Why frogs go back to the pond where they hatched\n"
             "B. A village effort to keep frogs safe on their journey\n"
             "C. The harm that new roads do to wildlife\nD. How to dig a pond in your garden",
             [ask("5a", "Letter of the right heading for this paragraph:",
                  "Read the whole paragraph again under your heading.")]),
        item(6, "T02", "reading", "true-false-not-given",
             "Passage: The old mill on the River Tam closed in 1962. Ten years later the building opened "
             "again as a small museum of local crafts, run by volunteers.\n\n"
             "Sentence: The museum is popular with visitors from abroad.",
             [ask("6a", TFNG_LABEL, TFNG_CHECK)]),
        item(7, "T03", "production", "write-overview",
             "A chart shows how people in the town of Rimford travelled to work in 2000 and in 2020.\n"
             "Car: 60% in 2000, 45% in 2020\nBus: 25% in 2000, 20% in 2020\n"
             "Bicycle: 5% in 2000, 25% in 2020\nOn foot: 10% in 2000, 10% in 2020",
             [ask("7a", "One overview sentence: the main changes, with no figures:",
                  "Read your sentence against the chart: does it hold for both years?")]),
        item(8, "T04", "verbal", "match-meaning",
             "Sentence from a report: 'Visitor numbers fell sharply after the fire.'\n\n"
             "A. After the fire, far fewer people came to visit.\nB. The fire was started by a visitor.\n"
             "C. After the fire, the number of visitors slowly recovered.\nD. Few people saw the fire.",
             [ask("8a", "Letter of the sentence that says the same:",
                  "Read your sentence and the report sentence side by side.")]),
    ],
    "blocks": [], "terms": [], "theory": None, "least_sure": True,
}

DIAG_KEY = {
    "1a": {"accept": ["F"], "check": "07:00 and 16:00 underlined: two crossings",
           "solution": "The passage gives two times, so three a day contradicts it."},
    "2a": {"accept": ["1"], "check": "sentences 2 and 3 are results of the station closing",
           "solution": "Sentence 1 states the change; 2 and 3 are examples of it."},
    "3a": {"accept": ["shut"], "check": "'The bridge was shut for repairs' reads with the same meaning",
           "solution": "Closed means not open to use here."},
    "4a": {"accept": ["rose", "increased", "went up", "grew", "climbed", "more than tripled"],
           "check": "40 first, 120 last: an upward trend",
           "solution": "Sales rose every month, from 40 to 120."},
    "5a": {"accept": ["B"], "check": "every sentence is about the volunteers moving frogs",
           "solution": "The paragraph is about a village effort; A, C and D name other things."},
    "6a": {"accept": ["NG"], "check": "no words in the passage about visitors from abroad",
           "solution": "The passage says nothing about who visits."},
    "7a": {"accept": ["car travel fell while cycling grew"],
           "check": "no figures; car down and bicycle up both named",
           "solution": "Between 2000 and 2020 car use fell while cycling became far more common; bus and walking changed little."},
    "8a": {"accept": ["A"], "check": "fell sharply = far fewer",
           "solution": "Fell sharply means dropped a lot."},
}

THEORY_SPEC = {
    "v": 1, "id": THEORY, "type": "theory", "subject": SUBJECT,
    "title": "Headings: the whole paragraph first", "est_min": 10, "tools": "none", "answer_form": "short",
    "items": [item(
        1, "T01", "reading", "pick-heading",
        "Pencil questions: the same steps as the worked case, on a new paragraph.\n\n"
        "Paragraph: In 2019 the primary school in Carden dug up half of its car park and planted "
        "vegetables. The pupils water the beds before lessons. Last autumn the garden gave so many "
        "potatoes that the school kitchen bought no vegetables for a month, and the extra went to the "
        "village market.\n\n"
        "Headings:\nA. Why children should learn to cook\nB. A busy market in a small village\n"
        "C. How a school came to feed itself\nD. The trouble with car parks",
        [ask("1a", "Step 1: the whole paragraph in five words or fewer:"),
         ask("1b", "Step 3: letter of the heading that matches your five words:")])],
    "blocks": [],
    "terms": [{"term": "heading", "resolution": "defined_here"},
              {"term": "distractor", "resolution": "defined_here"}],
    "theory": {
        "floor": ["The main idea of a paragraph: the point that the other sentences explain or give "
                  "examples of. You found one on the diagnostic."],
        "words": [
            {"term": "heading", "gloss": "título",
             "def": "a short title that says what a whole paragraph is about"},
            {"term": "distractor", "gloss": "distrator",
             "def": "a wrong option written to look right, often because it repeats a word from the paragraph"},
        ],
        "sections": [
            {"kind": "worked", "title": "A worked case", "body":
                "Paragraph: In 1890 the town of Selby had no clean water. Families carried water up from the "
                "river, and every summer many children fell ill. In 1902 the council built a pumping station "
                "and laid pipes to every street. Within ten years, summer illness in the town had almost "
                "disappeared.\n\n"
                "Headings: A. The history of the river · B. How clean water changed a town's health · "
                "C. Why children fall ill in summer\n\n"
                "Step 1. Cover the headings. Say what the whole paragraph is about in five words or fewer: "
                "'piped water ended town illness'.\n\n"
                "Step 2. Look at the distractors. A repeats 'river', but the paragraph is not about the "
                "river. C repeats 'children', 'ill' and 'summer', but those are details inside the story.\n\n"
                "Step 3. Compare each heading with your five words, not with single words in the paragraph. "
                "B says the same thing as 'piped water ended town illness'.\n\n"
                "Step 4. Check: read the whole paragraph again under B. Every sentence belongs under it."},
            {"kind": "rule", "title": "The rule", "body":
                "Say the main idea of the whole paragraph in your words before you look at the headings. "
                "Then choose the heading that says the same thing. A heading that repeats a word from the "
                "paragraph is not a reason to choose it."},
            {"kind": "contrast", "title": "Two headings, one paragraph", "body":
                "Paragraph: Rain fell on the valley for two days in March. Then warm air melted the snow on "
                "the hills, the river climbed a metre in one night, and the lower streets flooded.\n\n"
                "'Rain in the valley' matches the first sentence. 'Why the valley flooded that spring' "
                "matches the whole paragraph. The second is the heading."},
            {"kind": "both_hold", "title": "When matching words works", "body":
                "Sometimes the heading that repeats a word is also the right one, because that word names "
                "the main idea. That is why matching words feels safe: it works often enough. Your five-word "
                "summary shows you when it does not."},
            {"kind": "warning", "title": "The likeliest wrong turn", "body":
                "Choosing the heading that shares the most words with the first sentence. First sentences "
                "often describe the scene; the main idea can come later in the paragraph."},
            {"kind": "where", "title": "Where this lives", "body":
                "IELTS Academic reading: a list of headings, one for each paragraph, with more headings than "
                "paragraphs. The same steps help with questions on the main idea of a whole passage."},
        ],
        "pages": None,
    },
    "least_sure": False,
}

THEORY_KEY = {
    "1a": {"accept": ["school garden feeds its kitchen", "pupils grow the school's food",
                      "a school grows its food"],
           "check": "n/a (pencil question)",
           "solution": "Every sentence is about the school producing food for itself."},
    "1b": {"accept": ["C"], "check": "n/a (pencil question)",
           "solution": "C says the same as the five words; A, B and D pick up single details."},
}

DRILL_CHECK = "Read the whole paragraph again under your heading."
HEADING_LABEL = "Letter of the heading for this paragraph:"

DRILLS_SPEC = {
    "v": 1, "id": DRILLS, "type": "drills", "subject": SUBJECT,
    "title": "Choose the heading from the whole paragraph", "est_min": 8, "tools": "none",
    "answer_form": "short",
    "items": [
        item(1, "T01", "reading", "pick-heading",
             "Worked for you. Read it, then answer the one question below.\n\n"
             "Paragraph: One family has kept bees on the hill above Oldcastle for four generations. "
             "Their honey sells in the town's shops, and each August they open the hives to school groups. "
             "The money from those visits now pays for a second hillside of wild flowers.\n\n"
             "Headings:\nA. The dangers of keeping bees\nB. A family business that keeps growing\n"
             "C. Where to buy honey in Oldcastle\nD. Why wild flowers need bees\n\n"
             "Step 1. The whole paragraph in five words: 'bee family business keeps expanding'.\n"
             "Step 2. C repeats 'honey' and 'Oldcastle'; D repeats 'wild flowers'. Both name details.\n"
             "Step 3. B says the same as the five words, so B is the heading.",
             [ask("1a", "Why step 3 does not choose C, which shares two words with the paragraph (one line):",
                  "Read your reason against the paragraph's last sentence.")]),
        item(2, "T01", "reading", "pick-heading",
             "Step 1 is done for you; finish steps 2 and 3.\n\n"
             "Paragraph: For years the ferry to Inchmore carried only twelve cars, and in summer drivers "
             "waited half a day to cross. In 2021 a larger boat arrived with room for forty cars. Queues on "
             "the pier have almost disappeared, and more visitors now come for a single day.\n\n"
             "Headings:\nA. The history of Inchmore's pier\nB. How a bigger ferry ended the long waits\n"
             "C. Summer holidays on the island\nD. How to drive onto a ferry\n\n"
             "Step 1. The whole paragraph in five words: 'bigger boat ended the queues'.",
             [ask("2a", "Step 3: letter of the heading that says the same as the five words:", DRILL_CHECK)]),
        item(3, "T01", "reading", "pick-heading",
             "Paragraph: A retired postal worker in the town began painting at sixty. Her "
             "first pictures showed the garden behind her house. Ten years later, her paintings of the coast "
             "hang in the national gallery, and art schools invite her to speak.\n\n"
             "Headings:\nA. Life at the post office\nB. A late start that led to success\n"
             "C. How to paint the coast\nD. Gardens in art",
             [ask("3a", HEADING_LABEL, DRILL_CHECK)]),
        item(4, "T01", "reading", "pick-heading",
             "Paragraph: The Kell valley once had eleven working farms. Today two are left. Most of the land "
             "is now a forest planted in the 1980s, and the old farmhouses have become holiday cottages.\n\n"
             "Headings:\nA. A valley that turned from farming to forest and holidays\n"
             "B. How to plant a forest\nC. The best holiday cottages\nD. Farm work in the 1980s",
             [ask("4a", HEADING_LABEL, DRILL_CHECK)]),
        item(5, "T01", "reading", "pick-heading",
             "Paragraph: At the start of the school year, the pupils at Harlow Road asked for a quieter lunch "
             "hall. The teachers split lunch into two sittings, added a wall of plants and asked the older "
             "pupils to eat outside on dry days. By December the noise had halved, and fewer pupils skipped "
             "lunch.\n\n"
             "Headings:\nA. Plants that grow indoors\nB. Why pupils skip lunch\n"
             "C. How one school made lunch calmer\nD. The school year in December",
             [ask("5a", HEADING_LABEL, DRILL_CHECK)]),
        item(6, "T01", "reading", "pick-heading",
             "Paragraph: Lighthouse keepers once lived beside every lamp on the Welsh coast. Machines took "
             "over the last lamps in 1998. Some keepers' houses are now museums, and one is a small hotel "
             "where guests can climb the tower.\n\n"
             "Headings:\nA. A day in the life of a keeper\nB. How lighthouse lamps work\n"
             "C. The end of the keepers, and new uses for their homes\nD. The best hotels on the coast",
             [ask("6a", HEADING_LABEL, DRILL_CHECK)]),
    ],
    "blocks": [{"title": "Block A: choose the heading from the whole paragraph", "items": [1, 2, 3, 4, 5, 6]}],
    "terms": [], "theory": None, "least_sure": True,
}

DRILLS_KEY = {
    "1a": {"accept": ["C names a detail, not the whole paragraph"],
           "check": "the last sentence is about the business, not where to buy honey",
           "solution": "C picks up two words but only one detail; the paragraph is about the business."},
    "2a": {"accept": ["B"], "check": "all three sentences sit under B", "solution": "B matches the five words."},
    "3a": {"accept": ["B"], "check": "every sentence is about her late start and where it led",
           "solution": "A, C and D each name one detail."},
    "4a": {"accept": ["A"], "check": "farms, forest and cottages all sit under A",
           "solution": "A covers the whole change; B, C and D name details."},
    "5a": {"accept": ["C"], "check": "every sentence is about a quieter lunch",
           "solution": "C covers the problem, the changes and the result."},
    "6a": {"accept": ["C"], "check": "keepers gone, houses used in new ways",
           "solution": "C covers both halves of the paragraph."},
}


# ==========================================================================
# The learner's typed answers and Claude's marking (synthetic)
# ==========================================================================

DIAG_TYPED = """Diagnostic, part A
Start time: 07:05
1. F | check: the passage gives 07:00 and 16:00, which is two a day
2. 1 | check: sentences 2 and 3 are what changed after the station closed
3. shut (first wrote "stopped") | check: "was stopped for repairs" sounded wrong; "was shut for repairs" reads right
4. The number of bicycles sold went up every month, from 40 in January to 120 in June. | check: 40 first, 120 last
5. I don't know
6. F | check: the passage says the museum is small and run by volunteers
7. In 2020, 45% went to work by car and 25% by bicycle, so cars went down. | check: the numbers match the chart
8. C
Stop time: 07:24
Least sure of: 7
"""

DIAG_GRADES = {
    "start": "07:05", "stop": "07:24", "date": "2026-10-12",
    "asks": [
        {"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "3a", "verdict": "right", "check": "caught", "least_sure": False},
        {"ask": "4a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "5a", "verdict": "dont_know", "check": "n/a", "least_sure": False},
        {"ask": "6a", "verdict": "wrong", "check": "filled", "least_sure": False, "mode": "R", "kind": "belief",
         "account": "It doesn't say the museum is popular, so I took that to mean it's false.",
         "belief": "treats a point the passage does not mention as one the passage contradicts"},
        {"ask": "7a", "verdict": "half", "check": "filled", "least_sure": True,
         "account": "I wasn't sure what an overview needs, so I gave the numbers."},
        {"ask": "8a", "verdict": "wrong", "check": "missing", "least_sure": False, "mode": "C", "kind": "slip",
         "account": "Slip: I circled A next to the question but wrote C in the box.",
         "belief": "copied a different letter into the box from the one chosen"},
    ],
}

THEORY_TYPED = """Theory sheet, pencil questions
1a. school garden feeds its kitchen
1b. C
"""

# No start or stop time: the pencils share the sheet with the reading, so their time says nothing about pace.
THEORY_GRADES = {
    "date": "2026-10-13",
    "asks": [
        {"ask": "1a", "verdict": "right", "check": "n/a", "least_sure": False},
        {"ask": "1b", "verdict": "right", "check": "n/a", "least_sure": False},
    ],
}

DRILLS_TYPED = """Drills: choose the heading
Start time: 07:19
1. C only names a detail (where to buy the honey); the paragraph is about the business growing. | check: the last sentence is about the business, not the honey
2. B | check: read it again under B, all of it belongs
3. B (first wrote D) | check: under D only one sentence belonged, so I changed to B
4. A | check: farms, forest and cottages all sit under A
5. C | check: every sentence is about making lunch quieter
6. C | check: keepers gone, houses used for new things
Stop time: 07:29
Least sure of: 5
"""

DRILLS_GRADES = {
    "start": "07:19", "stop": "07:29", "date": "2026-10-13",
    "asks": [
        {"ask": "1a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "2a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "3a", "verdict": "right", "check": "caught", "least_sure": False},
        {"ask": "4a", "verdict": "right", "check": "filled", "least_sure": False},
        {"ask": "5a", "verdict": "right", "check": "filled", "least_sure": True},
        {"ask": "6a", "verdict": "right", "check": "filled", "least_sure": False},
    ],
}


# ==========================================================================
# Running the CLI
# ==========================================================================

def write_text(path, text):
    """UTF-8 with \\n line endings on every system (Path.write_text would use \\r\\n on Windows)."""
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


# Environment for child processes: only the variables a Python child process
# needs, each named explicitly. The whole environment is never copied, so no
# unrelated variable (a token, a key) is ever passed along.
def base_env():
    """A minimal environment for a child process: each variable is named explicitly."""
    pairs = (
        ("PATH", os.environ.get("PATH")), ("PATHEXT", os.environ.get("PATHEXT")),
        ("SYSTEMROOT", os.environ.get("SYSTEMROOT")), ("SYSTEMDRIVE", os.environ.get("SYSTEMDRIVE")),
        ("WINDIR", os.environ.get("WINDIR")), ("COMSPEC", os.environ.get("COMSPEC")),
        ("TEMP", os.environ.get("TEMP")), ("TMP", os.environ.get("TMP")), ("TMPDIR", os.environ.get("TMPDIR")),
        ("LANG", os.environ.get("LANG")), ("LC_ALL", os.environ.get("LC_ALL")), ("LC_CTYPE", os.environ.get("LC_CTYPE")),
        ("TZ", os.environ.get("TZ")), ("PYTHONTZPATH", os.environ.get("PYTHONTZPATH")),
        ("PROGRAMFILES", os.environ.get("PROGRAMFILES")), ("PROGRAMFILES(X86)", os.environ.get("PROGRAMFILES(X86)")),
        ("LOCALAPPDATA", os.environ.get("LOCALAPPDATA")),
        ("INDELIBLE_NO_BROWSER", os.environ.get("INDELIBLE_NO_BROWSER")),
        ("INDELIBLE_TEST_BROWSER", os.environ.get("INDELIBLE_TEST_BROWSER")),
    )
    return {name: value for name, value in pairs if value is not None}


class Builder(object):
    def __init__(self, root, verbose=False):
        self.root = root
        self.home = root / "home"
        self.ws = self.home / "Study"
        self.subj = self.ws / SUBJECT
        self.typed_dir = root / "typed"   # where the learner saved typed answers, outside the workspace
        self.verbose = verbose
        self.home.mkdir(parents=True)
        self.typed_dir.mkdir()

    def env(self, now):
        e = base_env()
        e.update({
            "INDELIBLE_NOW": now, "INDELIBLE_NO_BROWSER": "1",
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
        })
        return e

    def run(self, now, *args, stdin=None, expect=0, workspace=True):
        cmd = [sys.executable, str(CLI)]
        if workspace:
            cmd += ["--workspace", str(self.ws)]
        cmd += [str(a) for a in args]
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=self.env(now), cwd=str(self.home), timeout=180)
        label = " ".join(str(a) for a in args[:4])
        if self.verbose:
            print("$ [%s] %s\n%s%s" % (now, label, r.stdout, r.stderr))
        if expect is not None and r.returncode != expect:
            raise SystemExit("build_sample: '%s' exited %s (expected %s)\nstdout:\n%s\nstderr:\n%s"
                             % (label, r.returncode, expect, r.stdout, r.stderr))
        return r

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return path

    def edit_section(self, path, placeholder, text):
        """Fill a learner-owned CLAUDE.md section, as Claude would with its edit tool."""
        body = path.read_text(encoding="utf-8")
        if placeholder not in body:
            raise SystemExit("build_sample: placeholder not found in %s: %r" % (path, placeholder))
        write_text(path, body.replace(placeholder, text.rstrip("\n"), 1))

    def build_sheet(self, now, sheet_id, spec, key, budget=None):
        """The builder subagent's steps: spec and answers into tmp, sheet new, lint, build."""
        tmp = self.subj / ".indelible" / "tmp"
        sp = self.write_json(tmp / (sheet_id + ".spec.json"), spec)
        ap = self.write_json(tmp / (sheet_id + ".answers.json"), key)
        self.run(now, "sheet", "new", SUBJECT, sheet_id, "--spec", sp, "--answers", ap)
        if ap.exists():
            raise SystemExit("build_sample: sheet new left the answers file behind")
        lint = ["sheet", "lint", SUBJECT, sheet_id] + (["--budget-min", budget] if budget else [])
        r = self.run(now, *lint)
        if "FAIL" in r.stdout or "WARN" in r.stdout:
            raise SystemExit("build_sample: lint for %s:\n%s" % (sheet_id, r.stdout))
        # Markdown first, then HTML: the record points at the HTML (what a learner without a
        # PDF renderer gets); the Markdown copy stays beside it for reading on GitHub.
        self.run(now, "sheet", "build", SUBJECT, sheet_id, "--format", "md")
        self.run(now, "sheet", "build", SUBJECT, sheet_id, "--format", "html")

    def file_and_grade(self, now_ingest, now_grade, sheet_id, typed, grades):
        """Evidence first, then the key, then the grades file and grade record."""
        tf = write_text(self.typed_dir / (sheet_id + ".txt"), typed)
        self.run(now_ingest, "scan", "ingest", SUBJECT, sheet_id, "--typed", tf)
        self.run(now_ingest, "key", "open", SUBJECT, sheet_id)   # Claude marks privately; output not kept
        gp = self.write_json(self.subj / ".indelible" / "tmp" / (sheet_id + ".grades.json"), grades)
        return self.run(now_grade, "grade", "record", SUBJECT, sheet_id, "--from", gp)

    def blocks(self, now):
        return json.loads(self.run(now, "plan", "list", "--json").stdout)

    def ack(self, now, rows):
        path = self.write_json(self.ws / ".indelible" / "cal-results.json", rows)
        self.run(now, "cal", "ack", "--from", path)

    def close(self, now, note=None):
        args = ["session", "close", SUBJECT] + (["--note", note] if note else [])
        r = self.run(now, *args)
        if "FAIL" in r.stdout:
            raise SystemExit("build_sample: session close failed:\n%s" % r.stdout)
        return r

    # ------------------------------------------------------------------ the story

    def build(self):
        # ---- Sunday 11 Oct, 18:00: onboarding, after the readback "yes" ----------------
        t = "2026-10-11T18:00+01:00"
        self.run(t, "init", self.ws, "--timezone", "Europe/Lisbon", workspace=False)
        for dotted, value in ROOT_SETTINGS:
            self.run(t, "set", "root", dotted, json.dumps(value, ensure_ascii=False))
        draft = self.write_json(self.ws / ".indelible" / "ielts-draft.json", SUBJECT_DRAFT)
        self.run(t, "subject", "add", SUBJECT, "--title", "IELTS Academic", "--profile", "exam", "--from", draft)
        draft.unlink()   # teach.md: remove the draft
        for tid, name, layer, confusable in TOPICS:
            args = ["topic", "add", SUBJECT, tid, "--name", name, "--layer", layer]
            if confusable:
                args += ["--confusable"] + confusable
            self.run(t, *args)
        ids = {}
        for key, kind, start, minutes, flags, content in BLOCKS:
            r = self.run(t, "plan", "add", SUBJECT, "--kind", kind, "--start", start, "--min", minutes,
                         "--content", content, *flags)
            ids[key] = r.stdout.split()[0]
        self.run(t, "plan", "check")
        self.run(t, "ledger", "add", "owed", "--subject", SUBJECT, "--by", "learner",
                 "--what", "Register for the 12 Dec sitting", "--due", "2026-10-20T20:00+01:00")
        self.run(t, "ledger", "add", "decision", "--subject", SUBJECT,
                 "--summary", "Checkpoint: official test 1, reading",
                 "--why", "I want to know by mid-November whether this is working",
                 "--check-on", "2026-11-14", "--rule", "below 30 of 40",
                 "--action", "two review blocks replace new material for 2 weeks")
        self.edit_section(self.ws / "CLAUDE.md", "(Learner-owned. Short facts that hold for every subject.)",
                          ROOT_ABOUT)
        subj_md = self.subj / "CLAUDE.md"
        self.edit_section(subj_md, "(Learner-owned: language reflexes, framing that helps, the learner's own "
                                   "words about their role in any work.)", SUBJECT_NOTES)
        self.edit_section(subj_md, "(Items that must never count as measurement, such as a practice test the "
                                   "learner has already seen.)", SUBJECT_DO_NOT_CALIBRATE)
        self.run(t, "render", "all")
        self.run(t, "cal", "ics", self.ws / "plan" / "ics" / "study-20261011.ics",
                 "--from", "2026-10-11", "--to", "2026-10-24")
        # The builder makes part A right after the welcome card.
        self.build_sheet("2026-10-11T18:20+01:00", DIAG, DIAG_SPEC, DIAG_KEY)

        # ---- Monday 12 Oct, 07:00: diagnostic part A -----------------------------------
        self.run("2026-10-12T07:00+01:00", "session", "open", SUBJECT, "--planned", 60, "--block", ids["mon"])
        # "Is the calendar file in?" "Yes": acknowledge every imported block.
        self.ack("2026-10-12T07:01+01:00", [
            {"block": b["id"], "provider": "ics", "id": "%s@indelible" % b["id"], "etag": None, "start": b["start"]}
            for b in self.blocks("2026-10-12T07:01+01:00") if b.get("start")])
        self.run("2026-10-12T07:02+01:00", "sheet", "issue", SUBJECT, DIAG, "--block", ids["mon"])
        self.run("2026-10-12T07:25+01:00", "sheet", "sat", SUBJECT, DIAG, "--start", "07:05", "--stop", "07:24")
        r = self.file_and_grade("2026-10-12T07:26+01:00", "2026-10-12T07:40+01:00", DIAG, DIAG_TYPED, DIAG_GRADES)
        if "[measured n=8]" not in r.stdout:
            raise SystemExit("build_sample: unexpected diagnostic result:\n%s" % r.stdout)
        self.run("2026-10-12T07:45+01:00", "note", "append", SUBJECT, "session",
                 stdin="Diagnostic part A marked. No topic had both of its part A questions right, so part B "
                       "is not needed (the adaptive stop). Tuesday: results, then the first skill.\n")
        self.close("2026-10-12T07:50+01:00", note="Diagnostic part A sat and marked")
        # Tuesday's sheets are built ahead, after the close message.
        self.build_sheet("2026-10-12T08:05+01:00", THEORY, THEORY_SPEC, THEORY_KEY, budget=40)
        self.build_sheet("2026-10-12T08:10+01:00", DRILLS, DRILLS_SPEC, DRILLS_KEY, budget=40)

        # ---- Tuesday 13 Oct, 07:00: results, then the first skill ----------------------
        self.run("2026-10-13T07:00+01:00", "session", "open", SUBJECT, "--planned", 60, "--block", ids["tue"])
        self.run("2026-10-13T07:03+01:00", "sheet", "issue", SUBJECT, THEORY, "--block", ids["tue"])
        self.file_and_grade("2026-10-13T07:14+01:00", "2026-10-13T07:15+01:00", THEORY, THEORY_TYPED,
                            THEORY_GRADES)
        # The learner says "closed": the 2-day recheck window opens 44 h from now.
        self.run("2026-10-13T07:17+01:00", "session", "taught", SUBJECT, "T01", "--by", "sheet",
                 "--block", ids["tue"])
        self.run("2026-10-13T07:18+01:00", "sheet", "issue", SUBJECT, DRILLS, "--block", ids["tue"])
        r = self.file_and_grade("2026-10-13T07:33+01:00", "2026-10-13T07:40+01:00", DRILLS, DRILLS_TYPED,
                                DRILLS_GRADES)
        if "[practice]" not in r.stdout:
            raise SystemExit("build_sample: unexpected drills result:\n%s" % r.stdout)
        # Place the recheck at the start of Thursday's slot and move the session block after it
        # (plan.md, "Placing a recheck").
        t = "2026-10-13T07:44+01:00"
        obligations = [b for b in self.blocks(t) if b.get("kind") == "cold" and not b.get("start")]
        if len(obligations) != 1:
            raise SystemExit("build_sample: expected one open recheck, found %r" % obligations)
        recheck = obligations[0]["id"]
        self.run(t, "plan", "place", recheck, "--start", "2026-10-15T07:00+01:00", "--min", 15)
        self.run(t, "plan", "move", ids["thu"], "--start", "2026-10-15T07:15+01:00", "--min", 45)
        self.run(t, "plan", "check")
        # With an .ics file, no hand edit: both blocks are acknowledged against the imported item.
        item_id = "%s@indelible" % ids["thu"]
        self.ack("2026-10-13T07:46+01:00", [
            {"block": recheck, "provider": "ics", "id": item_id, "etag": None, "start": "2026-10-15T07:00+01:00"},
            {"block": ids["thu"], "provider": "ics", "id": item_id, "etag": None, "start": "2026-10-15T07:15+01:00"},
        ])
        if json.loads(self.run("2026-10-13T07:47+01:00", "plan", "diff", "--json").stdout):
            raise SystemExit("build_sample: the calendar diff is not empty after the ack")
        self.run("2026-10-13T07:48+01:00", "note", "append", SUBJECT, "session",
                 stdin="First skill: theory sheet read and closed, pencils right, then one drill block. "
                       "The 2-day recheck opens Thursday's session at 07:00 (15 min). The calendar item "
                       "for Thursday stays as imported.\n")
        self.close("2026-10-13T07:52+01:00", note="Results given; first skill taught; recheck booked for Thursday")

        # The workspace CLAUDE.md names the skill's script by its full path on this machine;
        # the sample keeps the template's placeholder so it points at no one's folders.
        root_md = self.ws / "CLAUDE.md"
        script = CLI.resolve().as_posix()
        for written in ('"%s"' % script, script):
            body = root_md.read_text(encoding="utf-8")
            if written in body:
                write_text(root_md, body.replace(written, "<skill>/scripts/indelible.py"))
                break
        else:
            raise SystemExit("build_sample: the script path was not found in CLAUDE.md")

    def check_at_sample_clock(self):
        """brief and plan check at the sample's clock, on a throwaway copy (brief counts opens)."""
        copy = self.root / "check" / "Study"
        shutil.copytree(str(self.ws), str(copy))
        saved, self.ws = self.ws, copy
        try:
            self.run(SAMPLE_NOW, "plan", "check")
            data = json.loads(self.run(SAMPLE_NOW, "brief", SUBJECT, "--json").stdout)
        finally:
            self.ws = saved
        if data.get("chars", 0) > 4500:
            raise SystemExit("build_sample: the brief is over 4,500 characters")
        if "2-day recheck" not in data.get("text", "") or "ready now" not in data.get("text", ""):
            raise SystemExit("build_sample: the brief at the sample clock shows no recheck ready:\n%s"
                             % data.get("text"))

    # ------------------------------------------------------------------ the copy

    def files_to_export(self):
        """The workspace files to copy, after checking that none holds a path from this machine."""
        local = [str(self.root), str(self.root.resolve()), str(self.home), str(self.ws), str(REPO),
                 REPO.as_posix(), REAL_HOME, Path(REAL_HOME).as_posix()]
        local = [x for x in set(local) if x and len(x.strip("/\\")) > 3]
        files = []
        for p in sorted(self.ws.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.ws)
            if p.name in SKIP_NAMES or p.name.endswith(SKIP_SUFFIXES):
                continue
            text = p.read_bytes().decode("utf-8", "replace")
            for path in local:
                if path in text:
                    raise SystemExit("build_sample: %s contains a path from this machine (%s)" % (rel, path))
            files.append(rel)
        return files

    def copy_to(self, out, files):
        out.mkdir(parents=True)
        for rel in files:
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(self.ws / rel), str(dest))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rebuild the synthetic sample workspace with the real CLI.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default: %(default)s)")
    ap.add_argument("--force", action="store_true", help="replace the output folder if it holds a sample")
    ap.add_argument("--verbose", action="store_true", help="print every command and its output")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            raise SystemExit("build_sample: %s exists; pass --force to replace it" % out)
        if not (out / "indelible.json").is_file():
            raise SystemExit("build_sample: %s is not a sample workspace; not replacing it" % out)
    root = Path(tempfile.mkdtemp(prefix="indelible-sample-"))
    try:
        b = Builder(root, verbose=args.verbose)
        b.build()
        b.check_at_sample_clock()
        files = b.files_to_export()
        if out.exists():
            shutil.rmtree(str(out))
        b.copy_to(out, files)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    print("Sample workspace written to %s (%d files). Its clock: INDELIBLE_NOW=%s" % (out, len(files), SAMPLE_NOW))
    return 0


if __name__ == "__main__":
    sys.exit(main())
