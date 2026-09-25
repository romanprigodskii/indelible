# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue.

1. Use GitHub's private vulnerability reporting: open this repository's **Security** tab and choose **Report a vulnerability** ([direct link](../../security/advisories/new)).
2. Describe what you found, how to reproduce it (the steps, command or prompt, your operating system and Python version) and what someone could gain from it.
3. Use made-up data only. The synthetic learners in `evals/fixtures/` work well. Please don't send real study records or personal details.

If the form isn't available to you, open a public issue that says only that you have a security report and would like a private way to send it. Leave out the details.

## What counts

Anything that breaks the promises in the README's [What it runs, writes and sends](README.md#what-it-runs-writes-and-sends) section, or the seal on answer keys. For example:

- **An answer key shown too early:** any path that prints, copies, renders or otherwise reveals an answer key, or its content, before the learner's attempt is filed.
- **Writing outside the workspace:** the scripts creating, changing or deleting files outside the learner's study folder, beyond what the README lists. Examples are path traversal through a subject id, sheet id or file name, or following a symbolic link.
- **Command injection:** a file name, id, sheet text or calendar text that makes the scripts, or the programs they start, run a command.
- **Data leaving the computer:** anything that sends data off the machine, or makes the plugin fetch anything from the network, beyond what the README lists.
- **Settings and permissions:** anything that changes Claude's settings or permission rules. The skill's `allowed-tools` patterns are text patterns that match more than `indelible.py`, as the README's [Install](README.md#install) section says; a way to steer Claude into using them to run other code (for example through text in a sheet or an imported file) is in scope.
- **Prompt injection that works:** text inside a sheet, photo, calendar item or imported file that gets Claude to break one of the points above.
- **Learner data inside the skill's own folder.**

**Usually not in scope:** a wrong mark or a scheduling bug (please open a normal issue, as described in the README's [Support and security](README.md#support-and-security) section); a learner deliberately editing their own files; and problems in Claude, Claude Code, typst, a browser or a calendar service themselves, which belong with their makers. If you're not sure, report it privately anyway.

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (the latest release) | Yes |
| Anything older | No |

Fixes are released as a new 0.1.x version and noted in the [changelog](CHANGELOG.md).

## What to expect

indelible is maintained by one volunteer, so responses are best effort:

- an acknowledgement within 7 days;
- then an assessment: a fix, a workaround, or an explanation of why it isn't a vulnerability;
- credit in the advisory and the changelog, if you'd like it.

Please allow reasonable time for a fix before you disclose the problem publicly. We'll agree a date with you.
