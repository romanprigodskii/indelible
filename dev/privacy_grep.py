#!/usr/bin/env python3
"""Privacy check for the public indelible repository. Run it before every push.

    python3 dev/privacy_grep.py [--source DIR] [--show-sources] [--shingle N]
                                [--denylist PATH] [--no-git-meta]

What it checks:

1. Denylist. Regular expressions, one per line, are read from
   dev/.privacy-denylist.txt. Blank lines and lines starting with "#" are
   ignored, and surrounding whitespace is stripped. That file is git-ignored,
   is built locally and is never committed. Patterns are case-sensitive, as in
   grep (so an all-capitals acronym doesn't hit ordinary words); start a
   pattern with "(?i)" to make it case-insensitive, as a name pattern should
   be, so that a lower-case handle outside the allowlist is caught too.
   A line starting with "identity: Name <email>" accepts that git identity in
   the metadata check (step 4), for an identity the maintainer has chosen to
   publish. A line starting with "allow:" is an allow pattern instead (case-sensitive,
   exact): the text it matches is blanked out of every scanned line before the
   denylist runs. Use it only for known false positives, such as a font name
   that contains a denylisted word; the rest of the line is still scanned.
   Every git-tracked file and every untracked file that is not ignored
   (git ls-files -co --exclude-standard) is scanned, and so are the file paths.
   A hit is printed as  path:line:N  where N is the line number of the pattern
   in the denylist and line 0 means the file's path. The matched text is never
   printed.
2. Allowlist. The maintainer's handle may appear only in:
   - README.md: the credit line, exactly, and the plugin-marketplace install
     command;
   - .claude-plugin/*.json: the author and owner fields, and the homepage and
     repository fields that carry the same handle.
   The handle is read from .claude-plugin/plugin.json (author.name), so this
   script never contains it.
3. Credit line. README.md must still contain the credit line, exactly.
4. Git metadata (skip with --no-git-meta). Every commit's author and committer
   (git log --all), every annotated tag's tagger, and the effective
   `git config user.name` / `user.email` must be the handle (or "GitHub" /
   a "[bot]" account) with a users.noreply.github.com address (or
   noreply@github.com). Only counts and field names are printed, never a
   value. Fixing old commits means rewriting history: the maintainer's call.
5. Fingerprints (only with --source DIR). Every distinctive N-word shingle
   (a run of N consecutive words, lower-cased; N is 8 unless --shingle says
   otherwise) in DIR/**/*.md, *.tex and *.txt is hashed, and the repository's
   text files are checked for any shared shingle. Only repo file names and
   counts are printed (source file names too with --show-sources); no text is
   copied or shown.

Exit codes: 0 clean; 1 at least one hit; 2 the denylist is missing, or a usage
or setup error. Python 3.9+, standard library only.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DENYLIST_REL = "dev/.privacy-denylist.txt"
PLUGIN_JSON_REL = ".claude-plugin/plugin.json"
README_REL = "README.md"

CREDIT_TEMPLATE = ("Designed and field-tested by [@{h}](https://github.com/{h}). "
                   "Written with Claude.")
INSTALL_TEMPLATE = "claude plugin marketplace add {h}/indelible"
HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
ALLOW_PREFIX = "allow:"
IDENTITY_PREFIX = "identity:"
NOREPLY_EMAIL_RE = re.compile(r"^(?:[0-9]+\+)?[A-Za-z0-9-]+(?:\[bot\])?@users\.noreply\.github\.com$", re.I)
SERVICE_IDENTITIES = {("github", "noreply@github.com")}

# JSON keys under .claude-plugin/ whose values may carry the handle.
PLUGIN_KEYS_RE = re.compile(r'"(author|owner|homepage|repository)"\s*:')

SHINGLE_WORDS = 8
SOURCE_GLOBS = ("*.md", "*.tex", "*.txt")
WORD_RE = re.compile(r"[^\W_]+")
BINARY_SNIFF = 8192


def _out(line=""):
    sys.stdout.write(line + "\n")


def _err(line):
    sys.stderr.write(line + "\n")


def _reconfigure_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


class SetupError(Exception):
    """A problem that stops the check before it can run (exit 2)."""


# ---------------------------------------------------------------- inputs

def load_denylist(path):
    """Return ([(line_no, compiled)], [compiled allow]) from the denylist file. Raises SetupError."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    patterns, allows = [], []
    for no, line in enumerate(text.splitlines(), 1):
        pat = line.strip()
        if not pat or pat.startswith("#") or pat.startswith(IDENTITY_PREFIX):
            continue
        allow = pat.startswith(ALLOW_PREFIX)
        if allow:
            pat = pat[len(ALLOW_PREFIX):].strip()
            if not pat:
                continue
        try:
            rx = re.compile(pat)
        except re.error as exc:
            # exc.msg and exc.pos never contain the pattern text itself.
            raise SetupError("denylist line %d: not a valid regular expression (%s at position %s)"
                             % (no, exc.msg, exc.pos))
        if rx.search("") is not None:
            raise SetupError("denylist line %d: the pattern matches empty text, so it would hit "
                             "every line; tighten it" % no)
        if allow:
            allows.append(rx)
        else:
            patterns.append((no, rx))
    return patterns, allows


def git_files(root):
    """Tracked plus untracked-but-not-ignored files, as repo-relative POSIX paths."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SetupError("could not run git (%s)" % exc)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise SetupError("git ls-files failed: %s" % (msg[0] if msg else "unknown error"))
    names = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    seen = []
    for n in names:
        if n and n not in seen:
            seen.append(n)
    return seen


def read_text(path):
    """The file's text, or None when it looks binary or cannot be read."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:BINARY_SNIFF]:
        return None
    text = data.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def read_handle(root):
    """The maintainer's handle from plugin.json author.name, or None."""
    path = root / PLUGIN_JSON_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    author = data.get("author") if isinstance(data, dict) else None
    name = author.get("name") if isinstance(author, dict) else None
    if isinstance(name, str) and HANDLE_RE.match(name):
        return name
    return None


# ---------------------------------------------------------------- allowlist

def allowed_tokens(handle):
    """Strings that may be masked in allowlisted places, longest first."""
    if not handle:
        return []
    toks = [
        "https://github.com/%s/indelible" % handle,
        "https://github.com/%s" % handle,
        "%s/indelible" % handle,
        handle,
    ]
    return sorted(set(toks), key=len, reverse=True)


def _mask(line, tokens):
    for t in tokens:
        if t in line:
            line = line.replace(t, " " * len(t))
    return line


def is_plugin_json(rel):
    parts = rel.split("/")
    return len(parts) == 2 and parts[0] == ".claude-plugin" and parts[1].endswith(".json")


def allowlist_mask(rel, lines, handle):
    """Return the lines with allowlisted handle occurrences blanked out.

    Only exact tokens built from the handle are masked, and only on the
    allowlisted lines, so any other private text on those lines still hits.
    """
    tokens = allowed_tokens(handle)
    if not tokens:
        return lines
    if rel == README_REL:
        exact = {CREDIT_TEMPLATE.format(h=handle), INSTALL_TEMPLATE.format(h=handle)}
        return [_mask(l, tokens) if l.strip() in exact else l for l in lines]
    if is_plugin_json(rel):
        out = []
        inside = False  # inside a multi-line object such as "author": { ... }
        for l in lines:
            m = PLUGIN_KEYS_RE.search(l)
            out.append(_mask(l, tokens) if (m or inside) else l)
            rest = l[m.end():] if m else ""
            if m and "{" in rest and "}" not in rest:
                inside = True
            elif inside and "}" in l:
                inside = False
        return out
    return lines


# ---------------------------------------------------------------- checks

def _blank_allowed(line, allows):
    for rx in allows:
        line = rx.sub(lambda m: " " * len(m.group(0)), line)
    return line


def scan_denylist(root, files, patterns, handle, allows=()):
    """Yield (rel, line_no, pattern_line_no) for every hit."""
    for rel in files:
        for pno, rx in patterns:
            if rx.search(rel):
                yield rel, 0, pno
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if text is None:
            continue
        lines = allowlist_mask(rel, text.splitlines(), handle)
        for lno, line in enumerate(lines, 1):
            line = _blank_allowed(line, allows)
            for pno, rx in patterns:
                if rx.search(line):
                    yield rel, lno, pno


def _git_lines(root, args):
    try:
        proc = subprocess.run(["git"] + args, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise SetupError("could not run git (%s)" % exc)
    if proc.returncode not in (0, 1):   # 1: an unset config key
        msg = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise SetupError("git %s failed: %s" % (args[0], msg[0] if msg else "unknown error"))
    return proc.stdout.decode("utf-8", errors="replace").splitlines()


def load_identities(path):
    """Accepted git identities from "identity: Name <email>" lines of the (git-ignored) denylist.

    The maintainer lists an identity here on purpose, e.g. a real name and address that are
    already public elsewhere. Values are never printed."""
    out = set()
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(IDENTITY_PREFIX):
            continue
        m = re.match(r"^(.*?)\s*<([^>]+)>\s*$", line[len(IDENTITY_PREFIX):].strip())
        if m:
            out.add((m.group(1).strip().casefold(), m.group(2).strip().casefold()))
    return out


def _identity_ok(name, email, handle, identities=()):
    name = (name or "").strip()
    email = (email or "").strip().strip("<>")
    if (name.casefold(), email.casefold()) in SERVICE_IDENTITIES:
        return True
    if (name.casefold(), email.casefold()) in identities:
        return True
    name_ok = bool(handle) and (name.casefold() == handle.casefold() or name.endswith("[bot]"))
    return name_ok and bool(NOREPLY_EMAIL_RE.match(email))


def check_git_meta(root, handle, identities=()):
    """Return problem lines about commit, tag and config identities. Values are never included."""
    problems = []
    sep = "\x1f"
    rows = _git_lines(root, ["log", "--all", "--format=%an%x1f%ae%x1f%cn%x1f%ce"])
    bad_author = bad_committer = 0
    for row in rows:
        parts = row.split(sep)
        if len(parts) != 4:
            continue
        if not _identity_ok(parts[0], parts[1], handle, identities):
            bad_author += 1
        if not _identity_ok(parts[2], parts[3], handle, identities):
            bad_committer += 1
    if bad_author:
        problems.append("git metadata: %d of %d commits have an author name or email that is not the handle "
                        "with a users.noreply.github.com address (rewriting history is the maintainer's call)"
                        % (bad_author, len(rows)))
    if bad_committer:
        problems.append("git metadata: %d of %d commits have a committer name or email that is not the handle "
                        "with a users.noreply.github.com address" % (bad_committer, len(rows)))
    tags = _git_lines(root, ["for-each-ref", "refs/tags", "--format=%(taggername)%1f%(taggeremail)"])
    bad_tags = 0
    for row in tags:
        name, _, email = row.partition(sep)
        if not name and not email:
            continue    # a lightweight tag has no tagger
        if not _identity_ok(name, email, handle, identities):
            bad_tags += 1
    if bad_tags:
        problems.append("git metadata: %d tag%s with a tagger that is not the handle with a noreply address"
                        % (bad_tags, "" if bad_tags == 1 else "s"))
    cfg_name = _git_lines(root, ["config", "--get", "user.name"])
    cfg_email = _git_lines(root, ["config", "--get", "user.email"])
    name = cfg_name[0] if cfg_name else ""
    email = cfg_email[0] if cfg_email else ""
    if (name or email) and not _identity_ok(name, email, handle, identities):
        problems.append("git config: user.name / user.email is not the handle with a users.noreply.github.com "
                        "address, so the next commit would repeat the problem")
    return problems


def credit_ok(root, handle):
    if not handle:
        return False
    text = read_text(root / README_REL)
    if text is None:
        return False
    want = CREDIT_TEMPLATE.format(h=handle)
    return any(l.strip() == want for l in text.splitlines())


def _shingle_hashes(text, n=SHINGLE_WORDS):
    """Hashes of the distinctive n-word shingles of a text."""
    words = WORD_RE.findall(text.casefold())
    out = set()
    min_distinct = min(5, n - 1)
    for i in range(len(words) - n + 1):
        gram = words[i:i + n]
        # Skip runs with little content (tables of numbers, repeated tokens).
        if len(set(gram)) < min_distinct or all(w.isdigit() for w in gram):
            continue
        h = hashlib.blake2b(" ".join(gram).encode("utf-8"), digest_size=10).digest()
        out.add(h)
    return out


def fingerprint(root, files, source, n=SHINGLE_WORDS):
    """Return ([(rel, shared_count, {source_rel: count})], n_source_files)."""
    src_index = {}
    found = set()
    for pattern in SOURCE_GLOBS:
        found.update(p for p in source.rglob(pattern) if p.is_file())
    src_files = sorted(found)
    for p in src_files:
        text = read_text(p)
        if text is None:
            continue
        rel_src = p.relative_to(source).as_posix()
        for h in _shingle_hashes(text, n):
            src_index.setdefault(h, set()).add(rel_src)
    try:
        source_in_repo = source.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        source_in_repo = None
    results = []
    for rel in files:
        if source_in_repo is not None and (rel + "/").startswith(source_in_repo.rstrip("/") + "/"):
            continue
        if rel == DENYLIST_REL:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if text is None:
            continue
        shared = [h for h in _shingle_hashes(text, n) if h in src_index]
        if shared:
            by_src = {}
            for h in shared:
                for s in src_index[h]:
                    by_src[s] = by_src.get(s, 0) + 1
            results.append((rel, len(shared), by_src))
    return results, len(src_files)


# ---------------------------------------------------------------- main

def main(argv=None):
    _reconfigure_streams()
    ap = argparse.ArgumentParser(
        prog="privacy_grep.py",
        description="Scan the repository for private text before a push. Exit 0 clean, 1 hits, 2 setup error.")
    ap.add_argument("--source", metavar="DIR",
                    help="also compare N-word shingles of DIR/**/*.md, *.tex and *.txt with the repo "
                         "(counts and file names only)")
    ap.add_argument("--shingle", type=int, default=SHINGLE_WORDS, metavar="N",
                    help="shingle length in words for --source (default %d, at least 5)" % SHINGLE_WORDS)
    ap.add_argument("--no-git-meta", action="store_true",
                    help="skip the commit, tag and git config identity check")
    ap.add_argument("--show-sources", action="store_true",
                    help="with --source, also list which source files share shingles")
    ap.add_argument("--denylist", metavar="PATH",
                    help="denylist file (default: %s)" % DENYLIST_REL)
    args = ap.parse_args(argv)

    root = REPO
    deny_path = Path(args.denylist) if args.denylist else root / DENYLIST_REL
    if not deny_path.is_file():
        _err("WARNING: %s not found. Build the denylist locally (it is git-ignored) and run "
             "again. Nothing was checked." % (args.denylist or DENYLIST_REL))
        return 2

    if args.shingle < 5:
        _err("--shingle: use 5 or more words")
        return 2

    source = None
    if args.source:
        source = Path(args.source).expanduser()
        if not source.is_dir():
            _err("--source: not a folder: %s" % args.source)
            return 2

    try:
        patterns, allows = load_denylist(deny_path)
        files = git_files(root)
    except SetupError as exc:
        _err("privacy_grep: %s" % exc)
        return 2
    if not patterns:
        _err("WARNING: the denylist has no patterns; only the credit line and fingerprints are checked.")

    handle = read_handle(root)
    hits = 0

    if DENYLIST_REL in files:
        _out("%s: the denylist itself is tracked or not ignored; add it to .gitignore "
             "(and git rm --cached it if it was committed)" % DENYLIST_REL)
        hits += 1
    scan_list = [f for f in files if f != DENYLIST_REL]

    if handle is None:
        _out("%s: author.name is missing or not a plain handle; cannot check the allowlist "
             "or the credit line" % PLUGIN_JSON_REL)
        hits += 1

    n_text = 0
    for rel in scan_list:
        p = root / rel
        if p.is_file() and read_text(p) is not None:
            n_text += 1

    deny_hits = 0
    for rel, lno, pno in scan_denylist(root, scan_list, patterns, handle, allows):
        _out("%s:%d:%d" % (rel, lno, pno))
        deny_hits += 1
    hits += deny_hits

    if handle is not None and not credit_ok(root, handle):
        _out("%s: the credit line is missing or has changed" % README_REL)
        hits += 1

    meta_note = "; git metadata: not checked (--no-git-meta)"
    if not args.no_git_meta:
        try:
            meta = check_git_meta(root, handle, load_identities(deny_path))
        except SetupError as exc:
            _err("privacy_grep: %s" % exc)
            return 2
        for line in meta:
            _out(line)
        hits += len(meta)
        meta_note = "; git metadata: %d problem%s" % (len(meta), "" if len(meta) == 1 else "s")

    fp_hits = 0
    if source is not None:
        results, n_src = fingerprint(root, scan_list, source, args.shingle)
        for rel, count, by_src in results:
            _out("%s: shares %d shingle%s with %d source file%s"
                 % (rel, count, "" if count == 1 else "s", len(by_src), "" if len(by_src) == 1 else "s"))
            if args.show_sources:
                for s in sorted(by_src):
                    _out("    %s (%d)" % (s, by_src[s]))
            fp_hits += 1
        hits += fp_hits
        fp_note = "; fingerprints: %d source file%s, %d repo file%s sharing text" % (
            n_src, "" if n_src == 1 else "s", fp_hits, "" if fp_hits == 1 else "s")
    else:
        fp_note = "; fingerprints: not run (use --source DIR)"

    summary = "privacy_grep: %d text file%s, %d pattern%s, %d denylist hit%s%s%s" % (
        n_text, "" if n_text == 1 else "s", len(patterns), "" if len(patterns) == 1 else "s",
        deny_hits, "" if deny_hits == 1 else "s", meta_note, fp_note)
    if hits:
        _out(summary)
        _out("FAIL: %d problem%s. Fix them before pushing." % (hits, "" if hits == 1 else "s"))
        return 1
    _out(summary)
    _out("CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
