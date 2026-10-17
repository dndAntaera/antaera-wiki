# -*- coding: utf-8 -*-
"""Announce wiki changes on Discord.

The deploy workflow runs this as soon as the site is live. It lists the pages
that were added, edited, moved or removed, each linked to its live page with
a clipped account of what changed on it ("Shadowlands → Plane of Shadow",
"expanded Overview"), and posts the list to a Discord webhook.

One message covers a day. For 24 hours after it is posted, later changes are
folded into it by editing it, so it always shows everything that has changed
since it went up. After that, the next change starts a new message. When this
script itself changes, the open message is redrawn in its new form.

    python .github/scripts/announce.py --last <sha> [--head <sha>]
                                       [--state <file>] [--dry-run]
    python .github/scripts/announce.py --test [--ping] [--dry-run]

Each new message pings the Scars role. Edits do not ping again: Discord only
notifies when a message is posted.

What counts as a change is what a reader would see. Changes to the coding of
the wiki stay quiet:

  - Only Markdown pages under docs/ are considered. Styles, hooks, images and
    config are never announced.
  - A page whose words are the same before and after is left out, so a change
    to its layout markup, classes or line breaks does not count. Titles are
    words: renaming a card's heading ("Overview") is announced.
  - A commit with [quiet] anywhere in its message is left out, for coding
    changes that also touch a page's text.

With no DISCORD_WEBHOOK_URL in the environment, or with --dry-run, the message
is printed and not posted.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Every Markdown page under docs/, at any depth ("**/" also matches none).
PAGES = ":(glob)docs/**/*.md"

QUIET = "[quiet]"

# Pages CMS names the file it saved and nothing else, which the page list
# already says better. Its default templates all end the same way.
CMS_MESSAGE = re.compile(r"\(via Pages CMS\)\s*$")

# How long a message keeps taking edits before the next change gets a new one.
EDIT_WINDOW = 24 * 60 * 60

# Who a new post notifies: the Scars role, behind a spoiler. A webhook can
# only ping a role by its ID; "@Scars" written out would stay plain text.
SCARS_ROLE_ID = "1336400088997564678"
PING = "Ping: || <@&%s> ||" % SCARS_ROLE_ID

COLOUR = 0xBF00FF            # --wd-accent in docs/stylesheets/tokens.css

# Discord caps an embed's description at 4096 characters and a field at 1024.
# Everything is listed in full. Only a message that would run past a cap is
# shortened, and only as far as it takes to fit.
DESCRIPTION_CAP = 4096
FIELD_CAP = 1024

USER_AGENT = "antaera-wiki-announcer (https://github.com/dndAntaera/antaera-wiki, 1.0)"


# --- Git -------------------------------------------------------------------

def git(*args):
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8")


def is_ancestor(older, newer):
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=ROOT, capture_output=True,
    ).returncode == 0


class Blobs:
    """File contents at any commit, read through one long-lived git process.

    A batch of layout changes can touch every page in the wiki, and comparing
    each one before and after is two reads apiece.
    """

    def __init__(self):
        self.proc = None
        self.seen = {}

    def get(self, rev, path):
        key = "%s:%s" % (rev, path)
        if key not in self.seen:
            if self.proc is None:
                self.proc = subprocess.Popen(
                    ["git", "cat-file", "--batch"], cwd=ROOT,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.proc.stdin.write(key.encode("utf-8") + b"\n")
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().split()
            text = None
            if len(header) == 3:
                data = self.proc.stdout.read(int(header[2]) + 1)[:-1]
                if header[1] == b"blob":
                    text = data.decode("utf-8", "replace")
            self.seen[key] = text
        return self.seen[key]


blobs = Blobs()


def changed_pages(old_rev, new_rev):
    """(kind, old path, new path) for each page that differs between two commits."""
    out = git("diff", "--name-status", "-z", "-M", old_rev, new_rev, "--", PAGES)
    fields = out.split("\0")
    kinds = {"A": "added", "C": "added", "M": "edited", "T": "edited",
             "R": "moved", "D": "removed"}
    pages, i = [], 0
    while i < len(fields) and fields[i]:
        status = fields[i][0]
        if status in "RC":
            old, new = fields[i + 1], fields[i + 2]
            i += 3
        else:
            old = new = fields[i + 1]
            i += 2
        if status in kinds:
            pages.append((kinds[status], old, new))
    return pages


# --- What a reader sees ----------------------------------------------------

# A tag is layout, except where an attribute is something a reader sees: the
# picture or page it points at, alt text and hover titles, and the wiki's own
# data-wd-* labels, which the stylesheet prints on the card ("Spell").
SHOWN_ATTRS = re.compile(
    r"""\b(?:src|href|alt|title|data-wd-[\w-]+)\s*=\s*["']([^"']*)["']""", re.I)


def _tag(match):
    return " %s " % " ".join(SHOWN_ATTRS.findall(match.group(0)))


HEADING = re.compile(r"^\s{0,3}#+\s*(.*?)\s*#*\s*$")


def _strip_markup(text):
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", _tag, text)
    return re.sub(r"\{:[^}]*\}|\{\s*[.#][^}]*\}", " ", text)     # { .class }


def _words(line):
    return re.sub(r"[*_]+", "", line).split()                     # bold, italic


def tokens(text):
    """A page's words in order, the heading each one sits under, and where
    each heading's own words begin."""
    words, sections, starts, current = [], [], set(), None
    for line in _strip_markup(text).splitlines():
        m = HEADING.match(line)
        if m:
            line = m.group(1)
            current = " ".join(_words(line)) or current
            starts.add(len(words))
        for word in _words(line):
            words.append(word)
            sections.append(current)
    return words, sections, starts


def readable(text):
    """A page's words, without the markup that only decides how they look.

    Headings keep their words, so renaming a card's title ("Overview") is a
    change; moving it up or down a level is not.
    """
    if text is None:
        return None
    return " ".join(tokens(text)[0])


def is_content(kind, old, new, old_rev, new_rev):
    if kind != "edited":
        return True
    return readable(blobs.get(old_rev, old)) != readable(blobs.get(new_rev, new))


def content_changes(base, head):
    """Commits between the two that changed a page's words, oldest first.

    Each is (subject, the pages it changed). A [quiet] commit is not counted.
    """
    found = []
    for commit in git("rev-list", "--reverse", "--no-merges",
                      "%s..%s" % (base, head), "--", PAGES).split():
        message = git("log", "-1", "--format=%B", commit)
        if QUIET in message:
            continue
        parent = commit + "^"
        paths = set()
        for kind, old, new in changed_pages(parent, commit):
            if is_content(kind, old, new, parent, commit):
                paths.update((old, new))
        if paths:
            found.append((message.strip().split("\n", 1)[0].strip(), paths))
    return found


# --- The message -----------------------------------------------------------

def site_config():
    # mkdocs.yml carries !!python/name tags that a plain YAML loader refuses,
    # and these two lines are all that is needed from it.
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    name = re.search(r"^site_name:\s*(.+)$", text, re.M).group(1)
    url = re.search(r"^site_url:\s*(\S+)", text, re.M).group(1)
    return name.strip().strip("\"'"), url.strip("\"'").rstrip("/") + "/"


def page_url(site_url, path):
    """docs/deity/ornus.md -> <site>/deity/ornus/, the way MkDocs serves it."""
    stem = path[len("docs/"):-len(".md")]
    folder, _, name = stem.rpartition("/")
    if name in ("index", "README"):
        rel = folder + "/" if folder else ""
    else:
        rel = stem + "/"
    return site_url + urllib.parse.quote(rel)


def split_page(text):
    """(front matter as a dict, the body that follows it)."""
    text = text or ""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("\"'")
    return meta, text[end + 4:]


def front_matter(text):
    return split_page(text)[0]


def page_info(rev, path):
    """Title and flags of a page as it stood at one commit."""
    text = blobs.get(rev, path) or ""
    meta = front_matter(text)
    title = meta.get("title")
    if not title:
        m = re.search(r"^#\s+(.+?)\s*#*\s*$", text, re.M)
        title = m.group(1) if m else None
    if not title:
        stem = path[len("docs/"):-len(".md")]
        folder, _, name = stem.rpartition("/")
        if name in ("index", "README"):
            name = folder.rpartition("/")[2] or "Main Page"
        title = name.replace("-", " ").replace("_", " ").title()
    return {
        "title": title,
        "wip": meta.get("wip") == "true",
        "archived": meta.get("archived") == "true",
    }


def escape(text):
    return re.sub(r"([\\*_~`|\[\]<>#])", r"\\\1", text)


# --- Describing a change ---------------------------------------------------
#
# Each page in the list gets a short account of what happened to it, worked
# out by comparing its words before and after. Nothing in it is cut short. A few words swapped for a few
# others reads as "old → new"; anything bigger is named by the section it
# landed in ("expanded Overview", "added Dogma").

SMALL = 6       # words either side of a swap that still reads as one
GAP = 3         # unchanged words that can sit inside one rewritten passage

# A page with one change has it on the page's own line. A page with several
# lists them under it, one to a line, each marked with this.
SUB = " ◦ "


def _phrase(words):
    """Words lifted from a page, read back as plain text."""
    text = " ".join(words)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links, pictures
    text = re.sub(r"\]\([^)]*\)|[\[\]|]", " ", text)             # half a link, table bars
    text = " ".join(text.split()).strip(" -–—.,;:!?\"'“”‘’")
    if text.count("(") != text.count(")"):                        # half a bracket
        text = " ".join(re.sub(r"[()]", " ", text).split())
    return text.strip(" -–—.,;:!?\"'“”‘’")


def _passages(a, b):
    """The stretches that differ, as (i1, i2, j1, j2).

    Changes only a few unchanged words apart are one passage: a sentence
    rewritten is not a dozen separate swaps of the words in it.
    """
    passages = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if passages and i1 - passages[-1][1] <= GAP and j1 - passages[-1][3] <= GAP:
            passages[-1][1], passages[-1][3] = i2, j2
        else:
            passages.append([i1, i2, j1, j2])
    return passages


def _core(phrase):
    """A phrase without the article or possessive that varies around a name."""
    phrase = re.sub(r"^(the|a|an)\s+", "", phrase.lower())
    return re.sub(r"['’]s$", "", phrase)


def _section(name, title):
    # Before the first heading, or under the page's own title card, a change
    # is in the page's opening rather than in a section of it.
    return "the opening" if not name or name == title else name


class Change:
    """One page's change, read closely enough to describe."""

    def __init__(self, kind, old, new, base, head, title):
        self.kind, self.old, self.new, self.title = kind, old, new, title
        self.before = None if kind == "added" else blobs.get(base, old)
        self.after = None if kind == "removed" else blobs.get(head, new)
        self.old_meta, old_body = split_page(self.before)
        self.new_meta, new_body = split_page(self.after)
        self.a, self.a_sec, self.a_starts = tokens(old_body)
        self.b, self.b_sec, self.b_starts = tokens(new_body)
        self.passages = _passages(self.a, self.b)
        # Passages that are part of a move, by index: the line that says so,
        # or None where the other end of the move says it.
        self.moves = {}


# A passage this long that leaves one place and turns up in another, near
# enough word for word, was moved; it is described as the move, not as a
# section cut here and every heading in it added there.
MOVE_MIN = 40       # words
MOVE_MATCH = 0.6    # share of words in common


def _bag(words):
    return Counter(w.lower() for w in words)


def _shared(x, y):
    return sum((x & y).values())


def _block_name(words_sec, starts, lo, hi):
    """The first heading that begins inside a passage, if one does."""
    return next((words_sec[k] for k in range(lo, hi) if k in starts), None)


def _movable(lo, hi, starts):
    # Long enough to be sure of, or a whole section however short: a passage
    # that carries its own heading is unlikely to match another by chance.
    return hi - lo >= MOVE_MIN or (hi - lo > SMALL and any(k in starts for k in range(lo, hi)))


def find_moves(changes):
    cuts = [(c, n) for c in changes for n, (i1, i2, _, _) in enumerate(c.passages)
            if _movable(i1, i2, c.a_starts)]
    adds = [(c, n) for c in changes for n, (_, _, j1, j2) in enumerate(c.passages)
            if _movable(j1, j2, c.b_starts)]
    adds.sort(key=lambda cn: cn[0].passages[cn[1]][2] - cn[0].passages[cn[1]][3])
    for dest, dn in adds:
        _, _, j1, j2 = dest.passages[dn]
        added = _bag(dest.b[j1:j2])
        best, score = None, MOVE_MATCH
        for src, sn in cuts:
            if (src, sn) == (dest, dn) or sn in src.moves:
                continue
            i1, i2, _, _ = src.passages[sn]
            s = _shared(added, _bag(src.a[i1:i2])) / max(j2 - j1, i2 - i1)
            if s >= score:
                best, score = (src, sn), s
        if best is None:
            continue
        src, sn = best
        i1, i2, _, _ = src.passages[sn]
        name = (_block_name(dest.b_sec, dest.b_starts, j1, j2)
                or _block_name(src.a_sec, src.a_starts, i1, i2))
        _describe_move(src, sn, dest, dn, name)
        # Smaller pieces of the same move, split off where a few words on
        # either side happened to match, go with it.
        left = added - _bag(src.a[i1:i2])
        for n, (k1, k2, _, _) in enumerate(src.passages):
            piece = _bag(src.a[k1:k2])
            if n not in src.moves and k2 > k1 and _shared(left, piece) >= 0.8 * (k2 - k1):
                src.moves[n] = None
                left -= piece


def _describe_move(src, sn, dest, dn, name):
    if src is dest:
        dest.moves[dn] = "moved %s" % (name or "a passage")
        src.moves[sn] = None
        return
    dest.moves[dn] = "moved here from %s" % src.title
    if dest.kind == "added" and name == dest.title:
        src.moves[sn] = "%s moved to a page of its own" % name
    else:
        src.moves[sn] = "moved to %s" % dest.title
    # Named on both sides, unless the name is one of the pages': a whole
    # page folded into another needs no name beyond its own.
    if name and name not in (src.title, dest.title):
        dest.moves[dn] = "%s %s" % (name, dest.moves[dn])
        src.moves[sn] = "%s %s" % (name, src.moves[sn])


def _sections_named(names):
    """A run of sections added or taken away together, named as one."""
    names = list(dict.fromkeys(names))
    return " and ".join(names) if len(names) <= 2 else names[0]


def describe_edit(change):
    c = change
    title = c.new_meta.get("title")
    items = []

    if c.old_meta.get("title") and c.old_meta.get("title") != title:
        items.append("retitled from %s" % c.old_meta["title"])
    for flag, set_, cleared in (("wip", "marked a work in progress", "finished"),
                                ("archived", "archived", "back from the archive")):
        was, now = c.old_meta.get(flag) == "true", c.new_meta.get(flag) == "true"
        if was != now:
            items.append(set_ if now else cleared)

    a, a_sec, a_starts = c.a, c.a_sec, c.a_starts
    b, b_sec, b_starts = c.b, c.b_sec, c.b_starts
    old_heads, new_heads = set(a_sec), set(b_sec)
    swaps, sections, blocks, adds, cuts, relinked = {}, {}, [], [], [], False
    for n, (i1, i2, j1, j2) in enumerate(c.passages):
        if n in c.moves:
            if c.moves[n]:
                blocks.append(c.moves[n])
            continue
        # Headings that begin in this passage and are new to the page are
        # sections added, as one change however many there are; headings
        # that went are sections removed. Both at once is a rename, and reads
        # as a swap like any other.
        fresh = [b_sec[k] for k in range(j1, j2) if k in b_starts and b_sec[k] not in old_heads]
        gone = [a_sec[k] for k in range(i1, i2) if k in a_starts and a_sec[k] not in new_heads]
        if fresh and not gone:
            blocks.append("added " + _sections_named(
                "a title card" if h == title else h for h in fresh))
            if i2 - i1 > SMALL:
                sections.setdefault(_section(a_sec[i1], title), set()).add("rewrote")
            continue
        if gone and not fresh and j2 - j1 <= SMALL:
            blocks.append("removed " + _sections_named(gone))
            continue
        # A word or two slipped in or out of a name reads better as the
        # name changing: "Radiance → Quasi-Elemental Plane of Radiance".
        if (i1 == i2 or j1 == j2) and max(i2 - i1, j2 - j1) <= SMALL \
                and i2 < len(a) and a[i2][:1].isupper():
            i2, j2 = i2 + 1, j2 + 1
        old, new = _phrase(a[i1:i2]), _phrase(b[j1:j2])
        if old == new:
            relinked = relinked or bool(old)   # only a link's target moved
            continue
        if old and new and i2 - i1 <= SMALL and j2 - j1 <= SMALL:
            swaps[(old, new)] = swaps.get((old, new), 0) + 1
        elif new and not old and j2 - j1 <= SMALL:
            adds.append(new)
        elif old and not new and i2 - i1 <= SMALL:
            cuts.append(old)
        else:
            if j1 == j2:
                where = a_sec[i1]
            else:
                where = b_sec[j1] if j1 < len(b_sec) else (b_sec[-1] if b_sec else None)
            grown, shrunk = j2 - j1 > 2 * (i2 - i1), i2 - i1 > 2 * (j2 - j1)
            verb = "expanded" if grown else "cut from" if shrunk else "rewrote"
            sections.setdefault(_section(where, title), set()).add(verb)

    # The most repeated swap first: a renamed term reads before a stray fix.
    # One that only restates another ("the Luminara" for "Luminara") is left
    # out.
    kept = []
    for (old, new), _ in sorted(swaps.items(), key=lambda kv: (-kv[1], len(kv[0][0]))):
        core = (_core(old), _core(new))
        if any(o in core[0] and n in core[1] for o, n in kept):
            continue
        kept.append(core)
        items.append("%s → %s" % (old, new))
    items += list(dict.fromkeys(blocks))
    # One verb to a section: grown in one place and cut in another is rewritten.
    by_verb = {}
    for where, verbs in sections.items():
        verb = verbs.pop() if len(verbs) == 1 else "rewrote"
        by_verb.setdefault(verb, []).append(where)
    for verb in ("rewrote", "expanded", "cut from"):
        items += ["%s %s" % (verb, where) for where in by_verb.get(verb, [])]
    items += ["added “%s”" % s for s in dict.fromkeys(adds)]
    items += ["cut “%s”" % s for s in dict.fromkeys(cuts)]
    if relinked and not items:
        items.append("links updated")
    return items or ["small edits"]


def describe_new(text):
    """A new page's opening line: its first prose, or failing that its first list."""
    _, body = split_page(text)
    body = "\n".join(l for l in _strip_markup(body).splitlines() if not HEADING.match(l))
    prose, lists = [], []
    for block in re.split(r"\n\s*\n", body):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines or lines[0].startswith(("|", "```", ">", "---", "!!!", "???")):
            continue
        # A bold label on a line of its own ("**Origins**") is a heading in all
        # but name, not the first words of the paragraph under it.
        if len(lines) > 1 and len(lines[0].split()) <= 3 and lines[0][-1:] not in ".:;,":
            lines = lines[1:]
        if all(l.startswith(("- ", "* ")) for l in lines):
            lists.append("; ".join(_phrase(_words(l[2:])) for l in lines))
        else:
            prose.append(_phrase(_words(" ".join(lines))))
    for text in prose + lists:
        if len(text) >= 25:
            return first_sentence(text)
    return "a new page"


def first_sentence(text):
    """A paragraph's first sentence, whole: short, and not cut off mid-thought."""
    m = re.match(r"(.+?[.!?])(?:\s|$)", text)
    return m.group(1) if m and len(m.group(1)) >= 25 else text


def describe_move(old_path):
    return "moved from %s" % old_path[len("docs/"):-len(".md")]


def _item(text):
    # A line opens with a capital, except a before-and-after swap: those are
    # the page's own words, and capitalising them could hide the change itself
    # ("flail → Flail" read as "Flail → Flail").
    if " → " not in text:
        text = text[:1].upper() + text[1:]
    return escape(text)


def build_messages(base, head, notes=""):
    """The messages for everything readers would notice between the two, or None.

    One message when it fits, and as many as it takes when it does not:
    nothing is cut. The DM's Notes, if any, go at the top of the first.
    """
    site_name, site_url = site_config()
    commits = content_changes(base, head)
    paths = set().union(*(p for _, p in commits))
    groups = {"added": [], "edited": [], "moved": [], "removed": []}
    listed = set()

    pages = []
    for kind, old, new in changed_pages(base, head):
        if old not in paths and new not in paths:
            continue
        # Touched by a commit that changed its words, but since put back.
        if not is_content(kind, old, new, base, head):
            continue
        listed.update((old, new))
        info = page_info(base if kind == "removed" else head, new)
        pages.append((info, Change(kind, old, new, base, head, info["title"])))
    if not pages:
        return None

    find_moves([change for _, change in pages])
    for info, change in pages:
        title = escape(info["title"])
        if change.kind == "removed":
            line = "• ~~%s~~" % title
        else:
            line = "• [%s](%s)" % (title, page_url(site_url, change.new))
        if info["archived"]:
            line += " *(archived)*"
        elif info["wip"]:
            line += " *(work in progress)*"
        groups[change.kind].append((info["title"].lower(), line, _changes(change)))

    # The commits behind the pages listed. One whose every change was later
    # undone has nothing left to explain.
    subjects = []
    for subject, changed in commits:
        if (changed & listed and subject and not CMS_MESSAGE.search(subject)
                and subject not in subjects):
            subjects.append(subject)

    return _messages(site_name, site_url, head, _page_chunks(groups, notes),
                     ["• " + escape(s) for s in subjects])


HEADINGS = {"added": "New", "edited": "Edited", "moved": "Moved", "removed": "Removed"}


def _changes(change):
    """What happened to a page, one item to a change."""
    c = change
    moved = [m for m in c.moves.values() if m]
    if c.kind == "added":
        # A page made from a passage moved out of another says so; any
        # other new page shows its opening line.
        items = moved or [describe_new(c.after)]
    elif c.kind == "removed":
        items = moved
    elif c.kind == "edited":
        items = describe_edit(c)
    else:
        items = [describe_move(c.old)]
        if readable(c.before) != readable(c.after):
            items += describe_edit(c)
    return [_item(i) for i in items]


def _entry(line, items):
    """A page's line and its changes: one on the same line, several under it."""
    if not items:
        return line
    if len(items) == 1:
        return line + " — " + items[0]
    return line + "".join("\n" + SUB + i for i in items)


# Discord caps a message's embeds at 6000 characters between them, besides each
# description's 4096 and each field's 1024; a little is kept back for the title
# and footer.
EMBED_CAP = 6000 - 200


def _split_line(line, room):
    """A line longer than a whole description, in pieces that each fit."""
    return [line[i:i + room] for i in range(0, len(line), room)] or [""]


def _page_chunks(groups, notes=""):
    """The list of pages, in descriptions that each fit in one embed.

    It breaks between pages, never inside one unless a single page will not
    fit an embed on its own; a group carried into the next embed says so
    under its heading. The DM's Notes open the first.
    """
    chunks, lines, kind_here, started = [], [], None, set()
    room = DESCRIPTION_CAP

    def flush():
        nonlocal lines, kind_here
        if lines:
            chunks.append("\n".join(lines))
        lines, kind_here = [], None

    def text(extra):
        return "\n".join(lines + extra)

    if notes:
        lines = notes.split("\n")
    for kind, entries in groups.items():
        for _, line, items in sorted(entries):
            entry = _entry(line, items).split("\n")
            heading = []
            if kind_here != kind:
                label = "**%s**" % HEADINGS[kind]
                if kind in started:
                    label += " *(continued)*"
                heading = ([""] if lines and lines[-1] != NOTES_END else []) + [label]
            if lines and len(text(heading + entry)) > room:
                flush()
                heading = ["**%s**%s" % (HEADINGS[kind], " *(continued)*" if kind in started else "")]
            if not lines and len(text(heading + entry)) > room:
                # One page too long for an embed of its own: line by line.
                for piece in heading + [p for l in entry for p in _split_line(l, room)]:
                    if lines and len(text([piece])) > room:
                        flush()
                        lines = ["**%s** *(continued)*" % HEADINGS[kind]]
                    lines.append(piece)
            else:
                lines += heading + entry
            kind_here = kind
            started.add(kind)
    flush()
    return chunks or [""]


def _summary_fields(summary):
    """The summary in fields of at most FIELD_CAP characters, every line kept."""
    fields, value = [], []
    for line in summary:
        for piece in _split_line(line, FIELD_CAP):
            if value and len("\n".join(value + [piece])) > FIELD_CAP:
                fields.append(value)
                value = []
            value.append(piece)
    if value:
        fields.append(value)
    return [{"name": "Summary" if i == 0 else "Summary (continued)", "value": "\n".join(v)}
            for i, v in enumerate(fields)]


def _size(embed):
    return (len(embed.get("title", "")) + len(embed.get("description", ""))
            + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", [])))


def _messages(site_name, site_url, head, chunks, summary):
    """One message per chunk of the list, the summary after them, the ping on the first."""
    embeds = [_embed(site_name, site_url, head, chunk) for chunk in chunks]
    for field in _summary_fields(summary):
        last = embeds[-1]
        if len(last.get("fields", [])) < 25 and _size(last) + len(field["name"]) + len(field["value"]) <= EMBED_CAP:
            last.setdefault("fields", []).append(field)
        else:
            embeds.append(dict(_embed(site_name, site_url, head, ""), fields=[field]))
    if len(embeds) > 1:
        for i, embed in enumerate(embeds, 1):
            embed["title"] += " (%d/%d)" % (i, len(embeds))
    for embed in embeds:
        if not embed["description"]:
            del embed["description"]
    # The ping comes after the announcement, as a message of its own: Discord
    # shows a message's text above its embed, so in the same message it could
    # only come first. The announcement's own messages say nothing in their
    # text, and ping no one.
    messages = [{"embeds": [embed], "allowed_mentions": {"parse": []}} for embed in embeds]
    return messages + [ping_message()]


def ping_message(notify=True):
    """The ping that follows an announcement.

    Only the role is let through, so nothing else in it could ever ping. A ping
    posted again later, when an announcement grows and its ping has to move to
    the end, lets nothing through: everyone was notified the first time.
    """
    return {"content": PING,
            "allowed_mentions": {"parse": [], "roles": [SCARS_ROLE_ID] if notify else []}}


def is_ping(message):
    return not message.get("embeds")


# --- DM's Notes --------------------------------------------------------------
#
# /dmnotes (antaera-bot's worker/src/features/dmnotes.js) writes the DM's own
# thoughts at the top of an announcement's embed:
#
#   **DM's Notes**
#   The calendar has a home now.
#   (an invisible line: NOTES_END)
#   **Edited**
#   ...
#
# Redrawing the list must not lose them, so every edit reads the post first
# and carries them over, leaving the list that much less room. Before they
# lived in the embed they sat in the message's text, under "### DM's Notes";
# a post that still has them there has them moved into the embed.

NOTES_HEADER = "**DM's Notes**"
OLD_NOTES_HEADER = "### DM's Notes"
NOTES_END = "​"     # as antaera-bot's dmnotes.js writes it (END there)


def _quoted(text, header):
    lines = (text or "").split("\n")
    if lines[0] != header:
        return []
    quoted = []
    for line in lines[1:]:
        if not line.startswith(">"):
            break
        quoted.append(line)
    return quoted


def notes_block(message):
    """The DM's Notes on a posted message, ready to go back at the top of its embed.

    They are plain prose under their heading, closed by a line holding only
    NOTES_END, an invisible zero-width space that shows as a blank line and
    lets the notes have blank lines of their own. Notes quoted line by line,
    the way they were first written, are turned into that.
    """
    if not message:
        return ""
    embeds = message.get("embeds") or [{}]
    lines = (embeds[0].get("description") or "").split("\n")
    if lines[0] == NOTES_HEADER and NOTES_END in lines[1:]:
        return "\n".join(lines[:lines.index(NOTES_END, 1) + 1])
    quoted = (_quoted(embeds[0].get("description"), NOTES_HEADER)
              or _quoted(message.get("content"), OLD_NOTES_HEADER))
    if not quoted:
        return ""
    prose = [re.sub(r"^> ?", "", line) for line in quoted]
    return "\n".join([NOTES_HEADER] + prose + [NOTES_END])


def fitted(base, head, block):
    """The messages for base..head, the DM's Notes at the top of the first."""
    return build_messages(base, head, block) or undone_messages(head, block)


def undone_messages(head, notes=""):
    """For an announcement whose changes have all been reverted since it went up."""
    site_name, site_url = site_config()
    undone = "*The changes listed here have since been undone.*"
    return _messages(site_name, site_url, head, [notes + "\n" + undone if notes else undone], [])


def _embed(site_name, site_url, head, description):
    return {
        "title": "%s updated" % site_name,
        "url": site_url,
        "color": COLOUR,
        "description": description,
        "timestamp": git("show", "-s", "--format=%cI", head).strip(),
    }


def show(messages):
    for n, payload in enumerate(messages):
        if n:
            print("\n--- next message ---")
        if payload.get("content"):
            print(payload["content"])
        for embed in payload.get("embeds", []):
            print(embed["title"])
            if embed.get("description"):
                print(embed["description"])
            for field in embed.get("fields", []):
                print("\n" + field["name"])
                print(field["value"])


# --- Discord ---------------------------------------------------------------
#
# Announcements go up as the Discord bot (the one antaera-bot's Worker runs,
# whose /dmnotes writes the DM's Notes on them) when DISCORD_BOT_TOKEN is set,
# and through the webhook when it is not. The webhook is how the channel is
# found either way, and how posts it made earlier are edited or taken down.

API = os.environ.get("DISCORD_API", "https://discord.com/api/v10")    # elsewhere only in tests


class DiscordError(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP %d %s" % (code, body[:300].decode("utf-8", "replace")))
        self.code = code


def endpoint(webhook, suffix="", **query):
    parts = urllib.parse.urlsplit(webhook)
    params = urllib.parse.parse_qsl(parts.query) + list(query.items())
    return urllib.parse.urlunsplit(parts._replace(
        path=parts.path.rstrip("/") + suffix, query=urllib.parse.urlencode(params)))


def send(method, url, payload=None, token=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    # Discord turns away the default Python-urllib user agent.
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bot " + token
    for attempt in range(3):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code == 429 and attempt < 2:
                retry = json.loads(body or b"{}").get("retry_after", 2)
                time.sleep(min(float(retry), 30))
                continue
            raise DiscordError(e.code, body)


class Channel:
    """The announcement channel, and the two ways of posting to it."""

    def __init__(self, webhook, token):
        self.webhook, self.token, self._id = webhook, token, None

    @property
    def poster(self):
        return "bot" if self.token else "webhook"

    def _channel(self):
        if self._id is None:
            self._id = send("GET", self.webhook)["channel_id"]
        return self._id

    def _url(self, by, message_id=""):
        if by == "bot":
            return "%s/channels/%s/messages%s" % (
                API, self._channel(), "/" + message_id if message_id else "")
        if message_id:
            return endpoint(self.webhook, "/messages/" + message_id)
        return endpoint(self.webhook, wait="true")

    def post(self, payload):
        token = self.token if self.poster == "bot" else None
        return send("POST", self._url(self.poster), payload, token)["id"]

    def _call(self, method, message_id, by, payload=None):
        if by == "bot" and not self.token:
            raise DiscordError(403, b"the bot posted it, and DISCORD_BOT_TOKEN is not set")
        token = self.token if by == "bot" else None
        return send(method, self._url(by, message_id), payload, token)

    def get(self, message_id, by):
        return self._call("GET", message_id, by)

    def edit(self, message_id, by, payload):
        return self._call("PATCH", message_id, by, payload)

    def delete(self, message_id, by):
        return self._call("DELETE", message_id, by)


# --- State -----------------------------------------------------------------
#
# The workflow carries one small file from run to run: the messages that make
# up the announcement open for edits, and who posted each; when it went up;
# and the commit its list counts from.

def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        if not {"posted_at", "base"} <= state.keys():
            return None
        if "messages" not in state:
            # From when an announcement was one message, and before the bot
            # posted them, the webhook.
            if "message_id" not in state:
                return None
            state["messages"] = [{"id": state["message_id"], "by": state.get("by", "webhook")}]
        return state
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def save_state(path, messages, posted_at, base):
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"messages": messages, "posted_at": posted_at, "base": base}, fh)


def announcer_changed(last, head):
    """True if this script is different in head from how it was at last."""
    me = Path(__file__).resolve().relative_to(ROOT).as_posix()
    return subprocess.run(["git", "diff", "--quiet", last, head, "--", me],
                          cwd=ROOT, capture_output=True).returncode == 1


def channel_for(dry_run):
    """The announcement channel, or None when the message is only printed."""
    if dry_run:
        return None
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("\n::notice::DISCORD_WEBHOOK_URL is not set, so nothing was posted.")
        return None
    return Channel(webhook, os.environ.get("DISCORD_BOT_TOKEN", "").strip())


def latest_change(head):
    """The newest commit up to head that changed a page's words."""
    for commit in git("rev-list", "--no-merges", "--max-count=200", head,
                      "--", PAGES).split():
        if content_changes(commit + "^", commit):
            return commit
    return None


def post_all(channel, messages):
    """Post the messages in order; what was posted, as the state keeps it."""
    return [{"id": channel.post(m), "by": channel.poster} for m in messages]


def take_down(channel, parts):
    for part in parts:
        try:
            channel.delete(part["id"], part["by"])
        except DiscordError as e:
            if e.code not in (403, 404):
                raise


def test(head, dry_run, ping):
    """Post the newest page change again, marked as a test.

    It goes up as messages of its own and is not remembered, so the next real
    change starts or edits a real announcement, never this one. It pings only
    when asked to, so checking the bot does not wake the whole server.
    """
    commit = latest_change(head)
    if commit is None:
        sys.exit("No page change to show.")
    messages = [m for m in build_messages(commit + "^", commit) if ping or not is_ping(m)]
    for m in messages:
        if not is_ping(m):
            m["embeds"][0]["title"] += " (test)"
    [m for m in messages if not is_ping(m)][-1]["embeds"][0]["footer"] = {
        "text": "A test of the wiki's announcements: real ones look like this."}
    print("Test message, showing %s.\n" % commit[:7])
    show(messages)

    channel = channel_for(dry_run)
    if not channel:
        return
    try:
        post_all(channel, messages)
    except DiscordError as e:
        sys.exit("Discord refused the message: %s" % e)
    print("\nPosted to Discord as the %s." % channel.poster)


def first_message(channel, state):
    """The open announcement's first message, or None if it has gone."""
    part = state["messages"][0]
    try:
        return channel.get(part["id"], part["by"])
    except DiscordError as e:
        if e.code not in (403, 404):
            raise
        return None


def repost(state, head, channel, state_path):
    """Take the open announcement down and put it up again, from whoever posts now.

    The list is the same, counted from the same commit; DM's Notes on the old
    one go across with it. It is new, so it pings, and its day of edits starts
    again.
    """
    messages = fitted(state["base"], head, notes_block(first_message(channel, state)))
    show(messages)
    posted = post_all(channel, messages)
    print("\nPosted again as the %s, in %d message%s." % (
        channel.poster, len(posted), "" if len(posted) == 1 else "s"))
    take_down(channel, state["messages"])
    print("Took down the old one.")
    save_state(state_path, posted, time.time(), state["base"])


def update(channel, state, messages, current):
    """Edit the open announcement into these messages, the ping last.

    The messages already up are reused in order, each edited into what its
    place now needs: an embed with nothing in its text, or the ping. Edits
    never notify anyone, so the ping moving down a place does not ping again.
    Messages it now needs are posted after them, and ones it no longer needs
    are taken down.
    """
    parts = state["messages"]
    kept = []
    for n, message in enumerate(messages):
        if n < len(parts):
            if is_ping(message):
                body = dict(message, embeds=[])
            else:
                body = {"content": "", "embeds": message["embeds"], "allowed_mentions": {"parse": []}}
            channel.edit(parts[n]["id"], parts[n]["by"], body)
            kept.append(parts[n])
        else:
            if is_ping(message):
                message = ping_message(notify=False)
            kept += post_all(channel, [message])
    take_down(channel, parts[len(messages):])
    return kept


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--last", default="",
                    help="the last commit already announced (default: the parent of --head)")
    ap.add_argument("--head", default="HEAD", help="the commit just published")
    ap.add_argument("--state", help="the file that remembers the message open for edits")
    ap.add_argument("--test", action="store_true",
                    help="post the newest page change again, marked as a test")
    ap.add_argument("--ping", action="store_true",
                    help="with --test: ping Scars, as a real announcement does")
    ap.add_argument("--repost", action="store_true",
                    help="take the open message down and post it again")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message instead of posting it")
    args = ap.parse_args()

    head = git("rev-parse", "--verify", args.head + "^{commit}").strip()
    if args.test:
        test(head, args.dry_run, args.ping)
        return

    if args.repost:
        state = load_state(args.state) if args.state else None
        if not state:
            sys.exit("There is no open message to post again.")
        channel = channel_for(args.dry_run)
        if not channel:
            return
        try:
            repost(state, head, channel, args.state)
        except DiscordError as e:
            sys.exit("Discord refused: %s" % e)
        return

    last = args.last

    if last and is_ancestor(head, last):
        print("Nothing new: %s was already announced." % args.head)
        return
    if not last or not is_ancestor(last, head):
        if last:
            print("%s is not in the history of %s; announcing %s alone."
                  % (last[:7], head[:7], head[:7]))
        last = git("rev-parse", head + "^").strip()

    fresh = build_messages(last, head)
    state = load_state(args.state) if args.state else None
    now = time.time()
    if not (state and now - state["posted_at"] < EDIT_WINDOW
            and is_ancestor(state["base"], head)):
        state = None

    if fresh is None:
        # Nothing new for readers. But if this script changed, the open
        # announcement is redrawn so it reads the way the next one will.
        if not (state and announcer_changed(last, head)):
            print("Nothing for readers between %s and %s." % (last[:7], head[:7]))
            return
        print("The announcer changed; redrawing the open announcement.")

    channel = channel_for(args.dry_run)
    if state:
        print("Editing the announcement posted %.1f hours ago.\n"
              % ((now - state["posted_at"]) / 3600))
        if not channel:
            show(fitted(state["base"], head, ""))
            return
    else:
        print("Posting a new announcement.\n")
        show(fresh)
        if not channel:
            return

    try:
        if state:
            current = first_message(channel, state)
            if current is not None:
                # The DM's Notes at the top of the first message carried over.
                messages = fitted(state["base"], head, notes_block(current))
                show(messages)
                try:
                    parts = update(channel, state, messages, current)
                    save_state(args.state, parts, state["posted_at"], state["base"])
                    print("\nEdited the announcement on Discord (%d message%s)."
                          % (len(parts), "" if len(parts) == 1 else "s"))
                    return
                except DiscordError as e:
                    if e.code not in (403, 404):
                        raise
            # Deleted from the channel, or posted by an old webhook.
            take_down(channel, state["messages"])
            if fresh is None:
                print("\nThe open announcement is gone, and there is nothing new to post.")
                return
            print("\nThe open announcement is gone; posting a new one.")
            show(fresh)
        posted = post_all(channel, fresh)
    except DiscordError as e:
        sys.exit("Discord refused the message: %s" % e)

    print("\nPosted to Discord as the %s, in %d message%s." % (
        channel.poster, len(posted), "" if len(posted) == 1 else "s"))
    save_state(args.state, posted, now, last)


if __name__ == "__main__":
    main()
