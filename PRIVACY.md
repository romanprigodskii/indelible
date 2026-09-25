# Privacy policy

**Effective date:** 25 September 2026. This policy covers the indelible plugin and skill, version 0.1.x.

indelible is an open-source study skill that runs inside Claude, on your own computer. This page explains what data it keeps, where that data lives and who can see it.

**In short:** your study record is a set of plain files in a folder you choose on your own computer. The plugin itself sends nothing anywhere, and it keeps no copy anywhere else. indelible is intended for adults.

## What data exists

As you use indelible, it keeps a study record made from what you tell it and the work you choose to file:

- **Your goal:** what you're preparing for, the date, what would count as success, and the materials you have.
- **Schedule preferences:** session length, days and times, sleep times, fixed commitments, rest day, and your calendar and reminder choices.
- **About you, if you choose to say:** whether you are 18 or over (and, if not, whether you are under 16 or 16–17), and your first language. If you skip the question, the adult defaults apply.
- **Your work:** photos, PDFs or typed answers you choose to file, and, for programming practice, a copy of a project folder you point it to.
- **Results:** marks, the mistakes you made with your own account of each, and when each topic or mistake is due again.
- **Session records:** when sessions opened and closed, what was taught, to-dos, decisions and short notes.
- **Sheets and answer keys** built for you. Keys are sealed until your attempt is filed.
- **Calendar references:** if you use a calendar connector, the IDs of the calendar items indelible created, so it can move them later.

indelible doesn't need your name, contact details or any account, and it doesn't ask for them. If you share signs of distress during a session, nothing about it goes into your study files.

## Where it lives

- **In a folder you choose on your own computer** (for example `~/Study`), as plain JSON, JSONL and Markdown files that you can open, copy or delete.
- **Nothing is kept inside the skill's own folder.** The scripts refuse to create a study folder there.
- **One small file outside the study folder:** `~/.indelible/workspace`, a single line holding the path of your study folder, written at setup so Claude can find it from any folder.
- **Temporary files:** when a browser prints a sheet to PDF, its throwaway profile sits in your computer's temp folder and is deleted straight away. `doctor`'s one-page test PDFs are made and deleted there too. The sheets themselves are made inside your study folder. For programming subjects, Claude marks your code on a copy in the temp folder and deletes that copy once the marks are recorded; the helper agent that builds programming sheets also tests its own reference solution in a temp folder, which holds none of your data (v0.1 doesn't yet delete that folder).
- **`CLAUDE.md` files** at the top of your study folder and in each subject's folder. Claude Code reads them automatically when it is opened there. They hold short instructions for Claude (use the skill, start with the brief, keep out of the answer keys) and any notes you asked Claude to keep; the brief reads your notes back. The scripts read no other `CLAUDE.md` and nothing in `~/.claude`. When you ask to import a study folder you've been running by hand, Claude reads that folder's own `CLAUDE.md`, because its rules are there.
- **Copies you make yourself.** If your study folder is inside a cloud-synced folder (such as iCloud Drive, OneDrive, Dropbox or Google Drive), that service copies it under its own terms; `doctor` warns when it notices this. If you choose local history, the folder becomes a git repository with no remote, and its `.gitignore` keeps answer keys, your answers, photos and the inbox out of it.

## What is sent where

- **The plugin sends nothing.** Its scripts make no network requests. When a browser prints a sheet to PDF, the scripts start it with its network access blocked, so it can't contact anything either, including its maker's background services. There are no analytics, no telemetry, no crash reports and no update checks, and nothing is ever sent to the author.
- **Your own tools, for programming subjects.** To mark your code, Claude runs it with your own compiler or test tool. That tool may download the dependencies your project declares, as it does whenever you run it; your code and marks aren't sent anywhere by indelible.
- **Claude.** Like anything else you do in Claude, your conversation is processed by Anthropic under your agreement with Anthropic. That includes what Claude reads from your study folder and the photos or files you hand it. Claude reads these only for the study task you asked for.
- **Your calendar, only if you choose it.** indelible uses only a calendar connector that you have added to Claude yourself, and only after you pick it at setup.
  - With your yes, Claude may read your busy times for the next 14 days to find free slots.
  - It writes study sessions only after showing you the changes and getting your yes. The one exception is an option you can choose at setup: moving a missed session within 24 hours and telling you afterwards.
  - It reads back what it wrote, to check it.
  - Each calendar item holds a title (such as "IELTS Academic · 2-day recheck (mixed) · 20m"), a few short steps, and the path of your study folder. It never holds your marks, mistakes or answers. Once written, these items are kept by your calendar provider under its own terms.
  - Without a connector, you get a local `.ics` file to import yourself.

## How long it's kept

Until you delete it. The plugin keeps no copy anywhere else, so deleting your study folder and `~/.indelible/` removes everything it stored. Calendar items stay in your calendar until you delete them there. Copies you made yourself (cloud sync, backups, git) are yours to delete.

## Deleting your data

- **Everything, the clean way:** delete your study folder and the `~/.indelible/` folder in your home folder.
- **One subject:** v0.1 has no command for this. Deleting that subject's folder inside your study folder removes its record, sheets, answer keys and the work you filed. Some traces stay in files the subjects share: its planned sessions and to-dos (in `plan/blocks.jsonl` and `ledger.jsonl`), any calendar files in `plan/ics/`, two small bookkeeping files in `.indelible/`, and its name in `indelible.json` and the top-level `CLAUDE.md`. Until you also remove its entry from the `subjects` list in `indelible.json`, the brief stops with an error. Removing every trace means editing those shared files yourself; deleting the whole study folder is the clean option.
- **Uninstalling** the plugin doesn't touch your study folder.
- In v0.1 the scripts never delete your data on their own. A `forget` command, which would show exactly what it deletes and delete it only after your yes, is planned for v0.2 and isn't available yet.

## Children and teens

indelible is intended for adults, and for people who are allowed to use Claude under Anthropic's terms. It doesn't verify anyone's age. At setup it asks whether you are 18 or over, and it uses the answer only to set defaults. The protective defaults below are a safety net, not a sign that the plugin is aimed at young people. If a learner says they are under 18, it applies them:

- at least 8.5 hours of sleep protected in the plan;
- no session ending after 22:00 on a school night unless the learner chooses it;
- school hours counted against the weekly study limit;
- energy checks for late sessions;
- under 16: no calendar or other connector without a parent's or guardian's agreement.

If a young learner shows distress, the skill stops studying and points them to a trusted adult.

## Changes to this policy

Changes are made in this file in the public repository, with the date above updated and a note in the [changelog](CHANGELOG.md).

## Contact

- **Questions and privacy concerns:** open an issue in the [Issues tab](../../issues) of this repository on GitHub. The repository is public, so please don't include your study files or personal details.
- **Security problems:** report them privately, as described in [SECURITY.md](SECURITY.md).

indelible is an independent open-source project. It is not made, endorsed or supported by Anthropic.
