# -*- coding: utf-8 -*-
"""Build the index of archived pages at build time.

Wikidot built its indexes from `[[module ListPages]]`, which queried pages by
tag when the page was viewed. A static site has no query engine, and the tag
assignments did not survive the backup, so the one index the wiki still wants
is generated here instead: it regenerates on every build, and a page added
later appears in it without anyone having to remember to list it.

Any page containing the ARCHIVED-INDEX marker gets the index in its place.

(This file was hooks/glossary.py, which also generated an A-Z index of the
whole wiki. The glossary was removed - the wiki does not need one - and the
archived index is what remains.)
"""
import re

ARCHIVED_MARKER = "<!-- ARCHIVED-INDEX -->"

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
        b = re.sub(r"<br>", " ", b)
        b = " ".join(b.split())
        if len(b) < 25:
            continue
        if len(b) > MAX_SUMMARY:
            cut = b[:MAX_SUMMARY].rsplit(" ", 1)[0]
            b = cut + "…"
        return b
    return ""


def _is_archived(text):
    """True when the page's front matter carries archived: true."""
    head = text[:400]
    return "\narchived: true" in head or head.startswith("archived: true")


def _card(body):
    """Wrap generated content in the same card the rest of the wiki uses.

    This page is generated rather than converted, so the card has to be built
    here or it would be the only page whose text sits loose on the background.
    """
    return (['<div class="wd-row" style="--wd-rw: 935px" markdown>',
             '<div class="wd-cell" markdown>', ""]
            + body + ["", "</div>", "</div>", ""])


def on_page_markdown(markdown, page, config, files, **kwargs):
    if ARCHIVED_MARKER not in markdown:
        return markdown
    return markdown.replace(ARCHIVED_MARKER, _archived_index(page, files))


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

    # The heading is here rather than left to Material, which injects a bare
    # <h1> when a page has none - and that one would sit outside the cards.
    parts = _card([
        "# Archived Pages",
        "",
        "Material kept for reference but no longer part of the current"
        " setting. Archived pages do not appear in search results.",
    ])
    if not sections:
        return "\n".join(parts + _card(["*Nothing is archived.*"]))

    labels = {"wm": "Stellar Marches (5e: 2014)"}
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
