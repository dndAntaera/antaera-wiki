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
# Each page in the list gets a clipped account of what happened to it, worked
# out by comparing its words before and after. A few words swapped for a few
# others reads as "old → new"; anything bigger is named by the section it
# landed in ("expanded Overview", "added Dogma").

CLIP = 90       # characters a description may run to
SMALL = 6       # words either side of a swap that still reads as one
GAP = 3         # unchanged words that can sit inside one rewritten passage

# A page with one change has it on the page's own line. A page with several
# lists them under it, one to a line, each marked with this.
SUB = " ◦ "


def clip(text, limit=CLIP):
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    # End on a whole item where one ends late enough, else on a whole word.
    item = cut.rfind("; ")
    if item > limit // 2:
        return cut[:item] + "; …"
    return cut.rsplit(" ", 1)[0].rstrip(" ;,→—") + "…"


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


def describe_edit(before, after):
    old_meta, old_body = split_page(before)
    new_meta, new_body = split_page(after)
    title = new_meta.get("title")
    items = []

    if old_meta.get("title") and old_meta.get("title") != title:
        items.append("retitled from %s" % old_meta["title"])
    for flag, set_, cleared in (("wip", "marked a work in progress", "finished"),
                                ("archived", "archived", "back from the archive")):
        was, now = old_meta.get(flag) == "true", new_meta.get(flag) == "true"
        if was != now:
            items.append(set_ if now else cleared)

    a, a_sec, a_starts = tokens(old_body)
    b, b_sec, b_starts = tokens(new_body)
    old_heads, new_heads = set(a_sec), set(b_sec)
    swaps, sections, adds, cuts, relinked = {}, {}, [], [], False
    for i1, i2, j1, j2 in _passages(a, b):
        # A heading that begins in this passage and is new to the page is a
        # section added, unless one went at the same time: that is a rename,
        # and reads as a swap like any other.
        fresh = [b_sec[k] for k in range(j1, j2) if k in b_starts and b_sec[k] not in old_heads]
        gone = [a_sec[k] for k in range(i1, i2) if k in a_starts and a_sec[k] not in new_heads]
        if fresh and not gone:
            for h in fresh:
                sections.setdefault("a title card" if h == title else h, set()).add("added")
            if i2 - i1 > SMALL:
                sections.setdefault(_section(a_sec[i1], title), set()).add("rewrote")
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
    # One verb to a section: grown in one place and cut in another is rewritten.
    by_verb = {}
    for where, verbs in sections.items():
        verb = ("added" if "added" in verbs else
                verbs.pop() if len(verbs) == 1 else "rewrote")
        by_verb.setdefault(verb, []).append(where)
    for verb in ("added", "rewrote", "expanded", "cut from"):
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
            return clip(text)
    return "a new page"


def describe_move(old_path):
    return "moved from %s" % old_path[len("docs/"):-len(".md")]


def _item(text):
    return escape(clip(text[:1].upper() + text[1:]))


def build_message(base, head):
    """The embed for everything readers would notice between the two, or None."""
    site_name, site_url = site_config()
    commits = content_changes(base, head)
    paths = set().union(*(p for _, p in commits))
    groups = {"added": [], "edited": [], "moved": [], "removed": []}
    listed = set()

    for kind, old, new in changed_pages(base, head):
        if old not in paths and new not in paths:
            continue
        # Touched by a commit that changed its words, but since put back.
        if not is_content(kind, old, new, base, head):
            continue
        listed.update((old, new))
        info = page_info(base if kind == "removed" else head, new)
        title = escape(info["title"])
        if kind == "removed":
            line = "• ~~%s~~" % title
        else:
            line = "• [%s](%s)" % (title, page_url(site_url, new))
        if info["archived"]:
            line += " *(archived)*"
        elif info["wip"]:
            line += " *(work in progress)*"
        groups[kind].append((info["title"].lower(), line,
                             _changes(kind, old, new, base, head)))

    if not any(groups.values()):
        return None

    embed = _embed(site_name, site_url, head, _page_list(groups))

    # The commits behind the pages listed. One whose every change was later
    # undone has nothing left to explain.
    subjects = []
    for subject, changed in commits:
        if (changed & listed and subject and not CMS_MESSAGE.search(subject)
                and subject not in subjects):
            subjects.append(subject)
    if subjects:
        # Newest last. Only past the cap are the oldest counted instead of
        # listed, so a message that grows through the day still shows what
        # just happened.
        lines = ["• " + escape(s) for s in subjects]
        value, dropped = "\n".join(lines), 0
        while len(value) > FIELD_CAP and dropped < len(lines) - 1:
            dropped += 1
            value = "\n".join(["*…and %d earlier*" % dropped] + lines[dropped:])
        embed["fields"] = [{"name": "Summary", "value": value[:FIELD_CAP]}]

    return _payload(embed)


HEADINGS = {"added": "New", "edited": "Edited", "moved": "Moved", "removed": "Removed"}


def _changes(kind, old, new, base, head):
    """What happened to a page, one item to a change."""
    before, after = blobs.get(base, old), blobs.get(head, new)
    if kind == "added":
        items = [describe_new(after)]
    elif kind == "edited":
        items = describe_edit(before, after)
    elif kind == "moved":
        items = [describe_move(old)]
        if readable(before) != readable(after):
            items += describe_edit(before, after)
    else:
        items = []
    return [_item(i) for i in items]


def _entry(line, items, cap):
    """A page's line and its changes: one on the same line, several under it.

    cap None lists every change. Otherwise a page with more than cap has the
    rest counted instead, and cap 0 leaves the page's line alone.
    """
    if not items or cap == 0:
        return line
    if len(items) == 1:
        return line + " — " + items[0]
    if cap is not None and len(items) > cap:
        items = items[:cap] + ["*…and %d more*" % (len(items) - cap)]
    return line + "".join("\n" + SUB + i for i in items)


def _page_list(groups):
    """The description: every page and every change, in full if it fits.

    Past Discord's cap it is shortened only as far as it has to be: the
    longest lists of changes are cut first, a line at a time; then the
    changes go altogether; then, last, pages from the end.
    """
    total = sum(len(entries) for entries in groups.values())

    def render(cap, keep=total):
        parts, shown = [], 0
        for kind, entries in groups.items():
            lines = []
            for _, line, items in sorted(entries):
                if shown == keep:
                    break
                lines.append(_entry(line, items, cap))
                shown += 1
            if lines:
                parts.append("**%s**\n%s" % (HEADINGS[kind], "\n".join(lines)))
        if shown < total:
            parts.append("*…and %d more pages*" % (total - shown))
        return "\n\n".join(parts)

    most = max(len(items) for entries in groups.values() for _, _, items in entries)
    for cap in [None] + list(range(most - 1, -1, -1)):
        text = render(cap)
        if len(text) <= DESCRIPTION_CAP:
            return text
    for keep in range(total - 1, 0, -1):
        text = render(0, keep)
        if len(text) <= DESCRIPTION_CAP:
            return text
    return render(0, 1)[:DESCRIPTION_CAP]


def undone_message(head):
    """For a message whose changes have all been reverted since it went up."""
    site_name, site_url = site_config()
    return _payload(_embed(site_name, site_url, head,
                           "*The changes listed here have since been undone.*"))


def _embed(site_name, site_url, head, description):
    return {
        "title": "%s updated" % site_name,
        "url": site_url,
        "color": COLOUR,
        "description": description,
        "timestamp": git("show", "-s", "--format=%cI", head).strip(),
    }


def _payload(embed):
    # The ping is the message's only text: page titles and commit messages sit
    # in the embed, where a mention never pings, and allowed_mentions lets the
    # Scars role through but no one else, @everyone included.
    #
    # Discord pings when a message is posted, never when it is edited, so a
    # post pings once and the changes folded into it later arrive quietly.
    return {"content": PING, "embeds": [embed],
            "allowed_mentions": {"parse": [], "roles": [SCARS_ROLE_ID]}}


def show(payload):
    embed = payload["embeds"][0]
    if payload.get("content"):
        print(payload["content"])
    print(embed["title"])
    print(embed["description"])
    for field in embed.get("fields", []):
        print("\n" + field["name"])
        print(field["value"])


# --- Discord ---------------------------------------------------------------

class DiscordError(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP %d %s" % (code, body[:300].decode("utf-8", "replace")))
        self.code = code


def endpoint(webhook, suffix="", **query):
    parts = urllib.parse.urlsplit(webhook)
    params = urllib.parse.parse_qsl(parts.query) + list(query.items())
    return urllib.parse.urlunsplit(parts._replace(
        path=parts.path.rstrip("/") + suffix, query=urllib.parse.urlencode(params)))


def send(method, url, payload):
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        # Discord turns away the default Python-urllib user agent.
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT})
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


# --- State -----------------------------------------------------------------
#
# The workflow carries one small file from run to run: which message is open
# for edits, when it went up, and the commit its list counts from.

def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        return state if {"message_id", "posted_at", "base"} <= state.keys() else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def announcer_changed(last, head):
    """True if this script is different in head from how it was at last."""
    me = Path(__file__).resolve().relative_to(ROOT).as_posix()
    return subprocess.run(["git", "diff", "--quiet", last, head, "--", me],
                          cwd=ROOT, capture_output=True).returncode == 1


def webhook_url(dry_run):
    """The webhook to post to, or None when the message is only printed."""
    if dry_run:
        return None
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("\n::notice::DISCORD_WEBHOOK_URL is not set, so nothing was posted.")
    return webhook or None


def latest_change(head):
    """The newest commit up to head that changed a page's words."""
    for commit in git("rev-list", "--no-merges", "--max-count=200", head,
                      "--", PAGES).split():
        if content_changes(commit + "^", commit):
            return commit
    return None


def test(head, dry_run, ping):
    """Post the newest page change again, marked as a test.

    It goes up as a message of its own and is not remembered, so the next
    real change starts or edits a real message, never this one. It pings only
    when asked to, so checking the webhook does not wake the whole server.
    """
    commit = latest_change(head)
    if commit is None:
        sys.exit("No page change to show.")
    payload = build_message(commit + "^", commit)
    if not ping:
        del payload["content"]
        payload["allowed_mentions"] = {"parse": []}
    embed = payload["embeds"][0]
    embed["title"] += " (test)"
    embed["footer"] = {"text": "A test of the wiki's announcements: "
                               "real ones look like this."}
    print("Test message, showing %s.\n" % commit[:7])
    show(payload)

    webhook = webhook_url(dry_run)
    if not webhook:
        return
    try:
        send("POST", endpoint(webhook, wait="true"), payload)
    except DiscordError as e:
        sys.exit("Discord refused the message: %s" % e)
    print("\nPosted to Discord.")


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
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message instead of posting it")
    args = ap.parse_args()

    head = git("rev-parse", "--verify", args.head + "^{commit}").strip()
    if args.test:
        test(head, args.dry_run, args.ping)
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

    fresh = build_message(last, head)
    state = load_state(args.state) if args.state else None
    now = time.time()
    if not (state and now - state["posted_at"] < EDIT_WINDOW
            and is_ancestor(state["base"], head)):
        state = None

    if fresh is None:
        # Nothing new for readers. But if this script changed, the open
        # message is redrawn so it reads the way the next one will.
        if not (state and announcer_changed(last, head)):
            print("Nothing for readers between %s and %s." % (last[:7], head[:7]))
            return
        print("The announcer changed; redrawing the open message.")

    if state:
        payload = build_message(state["base"], head) or undone_message(head)
        print("Editing the message posted %.1f hours ago.\n"
              % ((now - state["posted_at"]) / 3600))
    else:
        payload = fresh
        print("Posting a new message.\n")
    show(payload)

    webhook = webhook_url(args.dry_run)
    if not webhook:
        return

    try:
        if state:
            try:
                send("PATCH", endpoint(webhook, "/messages/" + state["message_id"]), payload)
                print("\nEdited the message on Discord.")
                return
            except DiscordError as e:
                if e.code not in (403, 404):
                    raise
                # Deleted from the channel, or posted by an old webhook.
                if fresh is None:
                    print("\nThe open message is gone (HTTP %d), and there is "
                          "nothing new to post." % e.code)
                    return
                print("\nThe open message is gone (HTTP %d); posting a new one." % e.code)
                payload = fresh
        message = send("POST", endpoint(webhook, wait="true"), payload)
    except DiscordError as e:
        sys.exit("Discord refused the message: %s" % e)

    print("\nPosted to Discord.")
    if args.state:
        save_state(args.state, {"message_id": message["id"], "posted_at": now, "base": last})


if __name__ == "__main__":
    main()
