# -*- coding: utf-8 -*-
"""Convert the Wikidot backup into the MkDocs site.

Run from the repository root:
    .venv/Scripts/python.exe _migration/convert.py <path-to-extracted-backup>

Rerunnable: it rewrites docs/ from the backup each time, so fixing a rule here
and re-running is the way to iterate rather than hand-editing the output.
"""
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
TABLES = os.path.join(ROOT, "_migration", "tables")
BASE = "/antaera-wiki"

# Wikidot furniture, not this wiki's content.
#
# Wikidot category slugs use a colon ("system:members") but the backup writes
# them with an underscore ("system_members.txt"), so both forms are matched -
# the colon form alone silently let 26 system pages through.
SKIP = re.compile(
    r"^(admin_|chatter|nav[:_]|forum_|featured|talk_|inc_|template|glossary_|_"
    r"|wiki[:_]|snippet[:_]|system[:_]|legal[:_]|theme[:_]|search[:_])"
    r"|^(1234|amadeus-mozart|help|new-wiki-help|main_about|random|wiki|contact"
    r"|about|donate)$"
)

# Slug prefixes with enough pages to be worth a folder.
FOLDERS = {
    "pantheon": "pantheon",
    "spelljamming": "spelljamming",
    "deity": "deity",
    "wm": "wm",
    "anthropology": "anthropology",
    "rules": "rules",
    "nation": "nation",
}

TODO = []


def target_path(slug):
    """Where a Wikidot slug lands under docs/."""
    if slug == "start":
        return "index.md"
    slug = slug.replace(":", "-")
    m = re.match(r"^([a-z]+)-(.+)$", slug)
    if m and m.group(1) in FOLDERS:
        return FOLDERS[m.group(1)] + "/" + m.group(2) + ".md"
    return slug + ".md"


# Titles a slug cannot produce. Set here rather than in the nav so the browser
# tab, search results and the glossary all agree with the sidebar.
TITLES = {
    "start": "Main Page",
    "pantheons": "The Pantheons",
    "cosmology": "The Cosmology",
    "spelljamming-known-spheres": "The Known Spheres",
    "map-antaera": "Antæra World Map",
    "taxonomy-main": "Taxonomies",
    "calendar": "Antæran Calendar",
    "spelljamming-main": "Spelljamming",
    "wm-index": "Stellar Marches (5e: 2014)",
}


# Headings too generic to serve as a page title.
GENERIC_HEADINGS = {
    "overview", "introduction", "intro", "summary", "description",
    "background", "contents", "about",
}


def title_from(slug):
    """Human title from a slug, minus any folder prefix it duplicates."""
    m = re.match(r"^([a-z]+)-(.+)$", slug)
    if m and m.group(1) in FOLDERS:
        slug = m.group(2)
    return slug.replace(":", " ").replace("-", " ").replace("_", " ").strip().title()


def strip_layout_tables(s):
    """Unwrap [[table]] used as a page frame rather than as data."""

    def repl(m):
        inner = m.group(1)
        cells = re.findall(r"\[\[cell[^\]]*\]\](.*?)\[\[/cell\]\]", inner, re.S | re.I)
        rows = re.findall(r"\[\[row[^\]]*\]\]", inner, re.I)
        if len(cells) <= 1 or len(cells) == len(rows):
            return "\n\n".join(c.strip() for c in cells)
        keep = [c.strip() for c in cells if len(c.strip()) > 40]
        if keep:
            return "\n\n".join(keep)
        return m.group(0)

    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\[\[table[^\]]*\]\](.*?)\[\[/table\]\]", repl, s, flags=re.S | re.I)
    return s


def wikidot_table_to_md(s):
    """Convert genuine [[table]] grids that survived unwrapping."""

    def repl(m):
        rows = re.findall(r"\[\[row[^\]]*\]\](.*?)\[\[/row\]\]", m.group(1), re.S | re.I)
        grid = []
        for r in rows:
            cells = re.findall(r"\[\[cell[^\]]*\]\](.*?)\[\[/cell\]\]", r, re.S | re.I)
            grid.append([" ".join(c.split()) for c in cells])
        if len(grid) < 2:
            return m.group(0)
        width = max(len(r) for r in grid)
        grid = [r + [""] * (width - len(r)) for r in grid]
        head = "| " + " | ".join(grid[0]) + " |"
        sep = "|" + "---|" * width
        body = "\n".join("| " + " | ".join(r) + " |" for r in grid[1:])
        return "\n\n" + head + "\n" + sep + "\n" + body + "\n\n"

    return re.sub(r"\[\[table[^\]]*\]\](.*?)\[\[/table\]\]", repl, s, flags=re.S | re.I)


def convert(src, slug, img_by_url, tables, linkmap):
    s = src.replace("\r\n", "\n")
    s = re.sub(r"\[!--.*?--\]", "", s, flags=re.S)
    s = re.sub(r"\[\[toc[^\]]*\]\]", "", s, flags=re.I)

    def todo(what):
        TODO.append((slug, what))
        return "\n<!-- TODO(" + what + ") -->\n"

    # [[code]] blocks become fenced code before anything else touches them.
    s = re.sub(r"\[\[code[^\]]*\]\](.*?)\[\[/code\]\]",
               lambda m: "\n```\n" + m.group(1).strip() + "\n```\n", s, flags=re.S | re.I)

    s = re.sub(r"\[\[module\s+(\w+).*?(?:\[\[/module\]\]|\]\])",
               lambda m: todo("module " + m.group(1)), s, flags=re.S | re.I)
    # Orphaned closers left when the opener matched its own ]] first.
    s = re.sub(r"\[\[/module\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[user\s+([^\]]+)\]\]", r"\1", s, flags=re.I)
    s = re.sub(r"\[\[/?button[^\]]*\]\]", "", s, flags=re.I)
    # Manual anchors and back-to-top links: Material generates heading anchors
    # and shows a back-to-top button, so both are redundant scaffolding.
    s = re.sub(r"\[\[#[^\]]*\]\]", "", s)
    s = re.sub(r"\[/#[^\s\]]*\s*\([^)]*\)\]", "", s)
    s = re.sub(r"\[\[include\s+([^\s\]]+).*?\]\]",
               lambda m: todo("include " + m.group(1)), s, flags=re.S | re.I)
    s = re.sub(r"\[\[iframe.*?\]\]", lambda m: todo("iframe"), s, flags=re.S | re.I)

    s = strip_layout_tables(s)
    s = wikidot_table_to_md(s)

    # Images: swap the imgur URL for the local file, or inline the transcribed
    # table when the picture was a picture of a table.
    def image(m):
        url = m.group(1)
        fn = img_by_url.get(url)
        if not fn:
            return ""
        stem = os.path.splitext(fn)[0]
        if stem in tables:
            return "\n\n" + tables[stem].strip() + "\n\n"
        return "![](" + BASE + "/img/" + fn + ")"

    s = re.sub(r"\[\[f?image\s+([^\s\]]+)[^\]]*\]\]", image, s, flags=re.I)

    # Hide URLs so the italic rule cannot eat the // in https://
    urls = []

    def hide(m):
        urls.append(m.group(0))
        return "\x00U%d\x00" % (len(urls) - 1)

    s = re.sub(r"https?://[^\s\)\]\"']+", hide, s)

    s = re.sub(r"\[\[/?(?:size|span|div)[^\]]*\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[note\]\](.*?)\[\[/note\]\]",
               lambda m: "!!! note\n" + "\n".join("    " + l for l in m.group(1).strip().split("\n")),
               s, flags=re.S | re.I)

    here = os.path.dirname(target_path(slug))

    def link(target, text):
        dest = linkmap.get(target.strip().lstrip("/"))
        if not dest:
            return text
        rel = os.path.relpath(dest, here or ".").replace("\\", "/")
        return "[" + text + "](" + rel + ")"

    s = re.sub(r"\[\[\[([^\]|]+)\|([^\]]+)\]\]\]", lambda m: link(m.group(1), m.group(2).strip()), s)
    s = re.sub(r"\[\[\[([^\]|]+)\]\]\]", lambda m: link(m.group(1), m.group(1).strip()), s)

    # Wikidot internal links of the form [/some-slug link text]
    s = re.sub(r"\[/([a-z0-9:_/-]+)\s+([^\]]+)\]",
               lambda m: link(m.group(1).split("/")[0], m.group(2).strip()), s, flags=re.I)

    # External links. Wikidot writes [url text], and [*url text] when the link
    # should open in a new window - the asterisk sits between the bracket and
    # the URL, so it has to be allowed for or the link never converts. Image
    # credit lines all use the starred form.
    s = re.sub(r"\[\*?(\x00U\d+\x00)\s+([^\]]+)\]", r"[\2](\1)", s)

    # Protect finished Markdown tables. The strikethrough rule below turns
    # "--x--" into "~~x~~", which would otherwise chew through a "|---|---|"
    # separator row and silently stop the table being a table.
    blocks = []

    def stash(m):
        blocks.append(m.group(0))
        return "\x00T%d\x00" % (len(blocks) - 1)

    s = re.sub(r"(?:^\|.*\|[ \t]*\n)+", stash, s, flags=re.M)

    s = re.sub(r"^(\+{1,6})\s*(.+)$",
               lambda m: "#" * len(m.group(1)) + " " + m.group(2).strip(), s, flags=re.M)
    s = re.sub(r"(?<!\w)//(?=\S)(.+?)(?<=\S)//(?!\w)", r"*\1*", s, flags=re.S)
    s = re.sub(r"(?<!-)--(?=\S)(.+?)(?<=\S)--(?!-)", r"~~\1~~", s)
    s = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<u>\1</u>", s)
    s = re.sub(r"^(\s*)\*\s+", r"\1- ", s, flags=re.M)
    s = re.sub(r"^-{4,}$", "---", s, flags=re.M)
    s = re.sub(r"\x00T(\d+)\x00", lambda m: blocks[int(m.group(1))], s)
    s = re.sub(r"\x00U(\d+)\x00", lambda m: urls[int(m.group(1))], s)
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def main(backup):
    src_dir = os.path.join(backup, "source")
    slugs = [f[:-4] for f in sorted(os.listdir(src_dir))]
    keep = [s for s in slugs if not SKIP.match(s)]
    linkmap = {s: target_path(s) for s in keep}

    imgs = json.load(open(os.path.join(ROOT, "_migration", "images.json"), encoding="utf-8"))
    img_by_url = {e["url"]: e["final"] for e in imgs}

    tables = {}
    for f in os.listdir(TABLES):
        if f.endswith(".md"):
            tables[f[:-3]] = open(os.path.join(TABLES, f), encoding="utf-8").read()

    # Wipe generated pages; leave img/ and stylesheets/ alone.
    for root, dirs, files in os.walk(DOCS, topdown=False):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), DOCS).replace("\\", "/")
            if rel.startswith(("img/", "stylesheets/")):
                continue
            if f.endswith(".md"):
                os.remove(os.path.join(root, f))
        for d in dirs:
            p = os.path.join(root, d)
            if os.path.relpath(p, DOCS) not in ("img", "stylesheets") and not os.listdir(p):
                os.rmdir(p)

    written = 0
    for slug in keep:
        raw = open(os.path.join(src_dir, slug + ".txt"), "rb").read().decode("utf-8", "replace")
        body = convert(raw, slug, img_by_url, tables, linkmap)

        # Promote the opening heading to the title only when the page has a
        # single top-level heading. A page like the glossary uses "# A", "# B"
        # as section markers; taking the first would title the page "A".
        title = None
        h1s = re.findall(r"^#\s+(.+)$", body, re.M)
        if len(h1s) == 1:
            m = re.search(r"^#\s+(.+)$", body, re.M)
            candidate = m.group(1).strip()
            plain = re.sub(r"[*_`~]", "", candidate).strip().lower()
            if body[:m.start()].strip() == "" and plain not in GENERIC_HEADINGS:
                title = candidate
                body = (body[:m.start()] + body[m.end():]).strip() + "\n"
        if not title:
            title = title_from(slug)
        # Headings carry inline markup; a title is plain text.
        title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)
        title = re.sub(r"[*_`~]", "", title)
        title = re.sub(r"^\s*Name\s*:\s*", "", title, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" :-")
        title = title.replace('"', "'")
        if not title:
            title = title_from(slug)
        title = TITLES.get(slug, title)

        # The glossary was 26 ListPages queries. It is regenerated at build
        # time by hooks/glossary.py, so the page is just a marker.
        if slug == "glossary":
            title = "Glossary"
            body = (
                "An index of every page on the wiki, in alphabetical order.\n\n"
                "<!-- GLOSSARY -->\n"
            )

        out_abs = os.path.join(DOCS, target_path(slug))
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        with open(out_abs, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('---\ntitle: "' + title + '"\n---\n\n' + body)
        written += 1

    print("pages written : %d  (skipped %d system pages)" % (written, len(slugs) - len(keep)))
    print("TODO markers  : %d" % len(TODO))
    for what, n in Counter(w for _, w in TODO).most_common():
        print("    %3d  %s" % (n, what))


if __name__ == "__main__":
    main(sys.argv[1])
