# -*- coding: utf-8 -*-
"""Announce wiki changes on Discord.

The deploy workflow runs this as soon as the site is live. It lists the pages
that were added, edited, moved or removed, each linked to its live page, and
posts them to a Discord webhook.

One message covers a day. For 24 hours after it is posted, later changes are
folded into it by editing it, so it always shows everything that has changed
since it went up. After that, the next change starts a new message.

    python .github/scripts/announce.py --last <sha> [--head <sha>]
                                       [--state <file>] [--dry-run]

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

COLOUR = 0xBF00FF            # --wd-accent in docs/stylesheets/tokens.css

# Discord caps an embed's description at 4096 characters and a field at 1024.
# The page list stops short of the cap and says how many it left out.
DESCRIPTION_BUDGET = 3800
NOTES_MAX = 10

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


def readable(text):
    """A page's words, without the markup that only decides how they look.

    Headings keep their words, so renaming a card's title ("Overview") is a
    change; moving it up or down a level is not.
    """
    if text is None:
        return None
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", _tag, text)
    text = re.sub(r"\{:[^}]*\}|\{\s*[.#][^}]*\}", " ", text)    # { .class }
    text = re.sub(r"(?m)^\s{0,3}#+", " ", text)                   # heading level
    text = re.sub(r"[*_]+", "", text)                             # bold, italic
    return " ".join(text.split())


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


def front_matter(text):
    if not text or not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("\"'")
    return meta


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
            line = "~~%s~~" % title
        else:
            line = "[%s](%s)" % (title, page_url(site_url, new))
        if info["archived"]:
            line += " *(archived)*"
        elif info["wip"]:
            line += " *(work in progress)*"
        groups[kind].append((info["title"].lower(), line))

    if not any(groups.values()):
        return None

    headings = {"added": "New", "edited": "Edited", "moved": "Moved",
                "removed": "Removed"}
    total = sum(len(v) for v in groups.values())
    parts, used, shown = [], 0, 0
    for kind, entries in groups.items():
        if not entries or used >= DESCRIPTION_BUDGET:
            continue
        block = ["**%s**" % headings[kind]]
        for _, line in sorted(entries):
            if used + len(line) + 1 > DESCRIPTION_BUDGET:
                break
            block.append(line)
            used += len(line) + 1
            shown += 1
        if len(block) > 1:
            parts.append("\n".join(block))
    if shown < total:
        parts.append("*…and %d more*" % (total - shown))

    embed = _embed(site_name, site_url, head, "\n\n".join(parts))

    # The commits behind the pages listed. One whose every change was later
    # undone has nothing left to explain.
    subjects = []
    for subject, changed in commits:
        if (changed & listed and subject and not CMS_MESSAGE.search(subject)
                and subject not in subjects):
            subjects.append(subject)
    if subjects:
        # Newest last, and the newest kept when there are too many: a message
        # that grows through the day should show what just happened.
        lines = ["• " + escape(s) for s in subjects[-NOTES_MAX:]]
        if len(subjects) > NOTES_MAX:
            lines.insert(0, "*…and %d earlier*" % (len(subjects) - NOTES_MAX))
        embed["fields"] = [{"name": "What changed",
                            "value": "\n".join(lines)[:1024]}]

    return _payload(embed)


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
    # Nothing in a page title or a commit message should be able to ping
    # anyone, @everyone included.
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def show(payload):
    embed = payload["embeds"][0]
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


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--last", default="",
                    help="the last commit already announced (default: the parent of --head)")
    ap.add_argument("--head", default="HEAD", help="the commit just published")
    ap.add_argument("--state", help="the file that remembers the message open for edits")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message instead of posting it")
    args = ap.parse_args()

    head = git("rev-parse", "--verify", args.head + "^{commit}").strip()
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
    if fresh is None:
        print("Nothing for readers between %s and %s." % (last[:7], head[:7]))
        return

    state = load_state(args.state) if args.state else None
    now = time.time()
    if state and now - state["posted_at"] < EDIT_WINDOW and is_ancestor(state["base"], head):
        payload = build_message(state["base"], head) or undone_message(head)
        print("Editing the message posted %.1f hours ago.\n"
              % ((now - state["posted_at"]) / 3600))
    else:
        state, payload = None, fresh
        print("Posting a new message.\n")
    show(payload)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if args.dry_run:
        return
    if not webhook:
        print("\n::notice::DISCORD_WEBHOOK_URL is not set, so nothing was posted.")
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
