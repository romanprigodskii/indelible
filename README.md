# indelible

**Learning that survives the cold test.**

`indelible` is a skill for Claude that runs your self-study like a strict, organised tutor. It interviews you once, plans backwards from your deadline, puts sessions in your calendar, teaches from sheets you read and then close, drills you on paper, re-tests everything cold two days later, and keeps an honest record of what you actually know.

> **Status: in development.** The first release (v0.1) lands here soon.

## The method

1. **Read it, then close it.** Theory comes on a sheet you read and put away before the drills. An explanation left in view turns a test into a lookup.
2. **One thing at a time, then all mixed up.** Teaching drills come in blocks of one question type. Anything that measures is unlabelled and interleaved, like the real exam.
3. **Nothing counts until it survives 48 hours.** Every new skill comes back cold two days later, on fresh problems. Same-day scores don't count.
4. **Flag your confidence on every answer.** Sure, half-sure or guess. Confident mistakes come back first, because those are the ones you won't re-check under pressure.
5. **Every miss goes in the error log** and returns after 1 day, 3 days, 1 week and 3 weeks.
6. **You do the work.** You get the smallest hint that unblocks you and never an answer you could reach yourself. Explaining a concept back is the real test.

## Commands (planned)

| Command | What it does |
|---|---|
| `teach` | A one-time interview: goal, deadline, session length, days and times, calendar, materials. Writes the files every other command reads. |
| `session` | Runs a full study session: what's due, cold re-serves, new material, drills, marking, file updates. |
| `diagnose` · `mock` | Measure, unlabelled, timed and scored. |
| `plan` · `reschedule` · `review` | Keep the plan and the calendar honest. |

## License

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option.

Designed and field-tested by [@romanprigodskii](https://github.com/romanprigodskii). Written with Claude.
