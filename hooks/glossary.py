# -*- coding: utf-8 -*-
"""Generate the A-Z glossary at build time.

Replaces the Wikidot `[[module ListPages]]` blocks the glossary used to be
built from. Those queried pages by tag at view time; a static site has no
query engine, and the tag assignments did not survive the Wikidot backup.

Indexing by title instead removes the manual step the old glossary needed -
every page appears the moment it exists, with no tagging - and it regenerates
on every build, so pages added through the CMS show up on their own.

Any page containing the GLOSSARY marker gets the index injected in its place.
"""
import re

MARKER = "<!-- GLOSSARY -->"
ARCHIVED_MARKER = "<!-- ARCHIVED-INDEX -->"

# Pages that index everything should not index themselves, and the landing
# page is navigation rather than an article.
EXCLUDE = {"index.md", "glossary.md", "the-index.md", "archived.md"}

MAX_SUMMARY = 220


def _read_title(text, fallback):
    m = re.search(r'^title:\s*"(.*)"\s*$', text, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"^title:\s*(.+)$", text, re.M)
    if m:
        return m.group(1).strip().strip('"')
    return fallback


def _strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _first_paragraph(text):
    """First run of prose, skipping headings, images, tables and comments."""
    body = _strip_frontmatter(text)
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b:
            continue
        if b.startswith(("#", "|", ">", "!", "<", "```", "---", "!!!", "???")):
            continue
        # Many pages open with a definition list (Symbol:, Home Plane:, ...).
        # Reading the bullets out flat beats showing a stray "- " to the reader.
        if b.startswith(("- ", "* ")):
            items = [re.sub(r"^[-*]\s+", "", ln).strip()
                     for ln in b.split("\n") if ln.strip().startswith(("-", "*"))]
            b = "; ".join(i for i in items if i)
        b = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", b)          # images
        b = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", b)      # links -> text
        b = re.sub(r"[*_`~]", "", b)                        # inline markup
        b = re.sub(r"<[^>]+>", "", b)                       # stray html
        b = " ".join(b.split())
        if len(b) < 25:
            continue
        if len(b) > MAX_SUMMARY:
            cut = b[:MAX_SUMMARY].rsplit(" ", 1)[0]
            b = cut + "…"
        return b
    return ""


def _letter(title):
    t = re.sub(r"^(the|a|an)\s+", "", title.strip(), flags=re.I)
    for ch in t:
        if ch.isalpha():
            return ch.upper()
        if ch.isdigit():
            return "#"
    return "#"


def _is_archived(text):
    """True when the page's front matter carries archived: true."""
    head = text[:400]
    return "\narchived: true" in head or head.startswith("archived: true")


def on_page_markdown(markdown, page, config, files, **kwargs):
    if ARCHIVED_MARKER in markdown:
        return markdown.replace(ARCHIVED_MARKER, _archived_index(page, files))
    if MARKER not in markdown:
        return markdown

    buckets = {}
    for f in files.documentation_pages():
        if f.src_uri in EXCLUDE or f.src_uri == page.file.src_uri:
            continue
        try:
            with open(f.abs_src_path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        # Archived pages are deliberately absent from the glossary.
        if _is_archived(text):
            continue
        title = _read_title(text, f.src_uri.rsplit("/", 1)[-1][:-3])
        buckets.setdefault(_letter(title), []).append(
            (title, f.src_uri, _first_paragraph(text))
        )

    letters = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c in buckets]
    if "#" in buckets:
        letters.append("#")

    def heading(c):
        return "Number" if c == "#" else c

    def anchor(c):
        return "number" if c == "#" else c.lower()

    total = sum(len(v) for v in buckets.values())
    # The heading is here rather than left to Material, which injects a bare
    # <h1> when a page has none - and that one would sit outside the cards.
    parts = _card([
        "# Glossary",
        "",
        "An index of every page on the wiki, in alphabetical order.",
        "",
        " · ".join("[%s](#%s)" % (heading(c), anchor(c)) for c in letters),
        "",
        "*%d entries, generated from page titles when the site is built.*" % total,
    ])
    # A card per letter rather than one long sheet: the index is 24 sections of
    # very different lengths, and a box around each is what tells them apart.
    for c in letters:
        body = ["## " + heading(c), ""]
        for title, uri, summary in sorted(buckets[c], key=lambda e: e[0].lower()):
            line = "**[%s](%s)**" % (title, uri)
            if summary:
                line += " — " + summary
            body.append(line)
            body.append("")
        parts += _card(body)

    return markdown.replace(MARKER, "\n".join(parts))


def _card(body):
    """Wrap generated content in the same card the rest of the wiki uses.

    Every page with a body on this wiki puts it on a card; these two pages are
    generated here rather than converted, so the card has to be built here too
    or they are the only pages whose text sits loose on the background.
    """
    return (['<div class="wd-row" style="--wd-rw: 935px" markdown>',
             '<div class="wd-cell" markdown>', ""]
            + body + ["", "</div>", "</div>", ""])


def _archived_index(page, files):
    """List the archived pages, grouped by the section they belong to."""
    sections = {}
    for f in files.documentation_pages():
        if f.src_uri == page.file.src_uri:
            continue
        try:
            with open(f.abs_src_path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if not _is_archived(text):
            continue
        title = _read_title(text, f.src_uri.rsplit("/", 1)[-1][:-3])
        folder = f.src_uri.split("/")[0] if "/" in f.src_uri else ""
        sections.setdefault(folder, []).append((title, f.src_uri, _first_paragraph(text)))

    if not sections:
        return "\n".join(_card(["*Nothing is archived.*"]))

    labels = {"wm": "Stellar Marches (5e: 2014)"}
    parts = _card([
        "# Archived Pages",
        "",
        "Material kept for reference but no longer part of the current"
        " setting. Archived pages do not appear in the glossary or in search"
        " results.",
    ])
    for folder in sorted(sections):
        body = ["## " + labels.get(folder, folder or "Other"), ""]
        for title, uri, summary in sorted(sections[folder], key=lambda e: e[0].lower()):
            line = "**[%s](%s)**" % (title, uri)
            if summary:
                line += " — " + summary
            body.append(line)
            body.append("")
        parts += _card(body)
    return "\n".join(parts)
