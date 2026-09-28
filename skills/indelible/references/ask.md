# ask: a question outside a session

Load for `ask`: a content question ("what does 'median' mean again?") in a workspace with no session running. It opens no lock and no session. `<s>` is the subject id, `<T>` a topic id.

1. **Read the state:**
   - `ind brief <s>`, without `--open`;
   - `ind sheet show <s>`: a sheet is out while its status is `issued`, or `sat` (taken, not yet marked), except a theory, external, example or triage sheet, which needs no marking (as `ind session status <s>` counts them);
   - `ind topic show <s>`: the topic id step 4 needs, since a plain brief gives topic names only.
2. **A question on a sheet that is out** (issued or taken, and not yet marked) is sealed (Law 3): "Write 'I don't know' for now. We'll go through it right after marking." Nothing more.
3. **Otherwise ask before telling** (Law 2): one probe ("What do you remember about it?"), or a pointer to the sheet that taught it ("Look at 'What it is and why' on your sheet about it."). "Teach me X", or a question needing a lesson, goes to `session`.
4. **After a pointer, or an explanation** (a few lines), log it at once: `ind session expose <s> <T> --kind review` for the pointer (a look at the sheet), `--kind chat` for the explanation. A WARN about a booked 2-day recheck: `ind plan check`, and move that recheck as [plan.md](plan.md) says (a preview and a yes before any calendar write). Tell the learner only "Your next 2-day recheck moves to <day>, so it still counts", never its topics or block id.
