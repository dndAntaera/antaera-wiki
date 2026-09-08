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
import unicodedata
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
    r"|about|donate|spelljamming-sphere-template)$"
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
    "race": "race",
    "item": "item",
    "faction": "faction",
    # Wikidot had three prefixes for one idea - a city, a settlement and a
    # point of interest are all places people live. They share a folder.
    "city": "settlement",
    "settlement": "settlement",
}

# Prefixes that classify a page but are not worth a folder of their own. They
# are stripped from the title, so "events-crucible-of-valor" is "Crucible of
# Valor" rather than "Events Crucible Of Valor" - the slug says what kind of
# thing it is, the title should say which thing.
TITLE_PREFIXES = {
    "poi", "events", "taxonomy",
}

# Pages that are two halves of one thing. Wikidot filed the arcane and the
# psionic version of a spell as separate pages, which split one rules entry
# across two URLs and gave both the same name. The wiki's own spelljamming
# magic page already keeps such pairs together - "Create Major Helm" and
# "Create Major Helm, psionic" sit side by side there - so this follows the
# convention the wiki set for itself.
#
# Each part keeps its own section and its own anchor, so a link that meant the
# psionic version still lands on the psionic version.
MERGES = {
    "stabilize-crystal": {
        "title": "Stabilize Crystal",
        "lead": "Stabilizing a [[[planar-crystal|Planar Crystal]]] can be done "
                "with magic or with psionics. Both forms are below.",
        "parts": [
            ("Spell", "spell-stabilize-crystal"),
            ("Psionic Power", "power-stabilize-crystal"),
        ],
    },
}

# part slug -> (merged slug, anchor of its section)
MERGE_PARTS = {}
for _merged, _spec in MERGES.items():
    for _label, _part in _spec["parts"]:
        MERGE_PARTS[_part] = (_merged, _label.lower().replace(" ", "-"))


# Pages whose slug never got a prefix, listed under the folder they belong to.
#
# Wikidot's prefixes were applied by hand and inconsistently: twelve gods were
# filed under "deity-" and eighteen were not, six of the seven factions were
# left loose, and no plane or region ever got one. The pages are the same
# shape either way, so this is authoring drift rather than a distinction.
#
# Membership is deliberately a list rather than a rule. "Void" and "Plane of
# Faerie" are stubs of the same shape as the deity stubs and are not gods;
# nothing in the page itself separates them. Each name below was checked
# against what the wiki says about it - the pantheon index for the gods, The
# Index's own Factions and Homebrew: Items sections, cosmology for the planes,
# and the world map's legend for the regions.
LOOSE_PAGES = {
    "deity": {
        "asmodeus", "cavri", "droma", "enigma", "fink", "fronir", "frymrit",
        "ithlwick", "leshrac", "nessa", "orion", "ornus", "rasmin", "sezzek",
        "silfaraan", "tari", "trelanni", "ythedie",
    },
    # The Index lists six of these under Factions. Sylvan Sect is not on that
    # list, but it is a 6-word stub and the only description of it anywhere -
    # Aesc Wood's "members of the Sylvan Sect" - reads as an organisation.
    "faction": {
        "collegiate-oculatus", "haven-commerce", "imperial-mercenary",
        "sylvan-sect", "taelmythaal-archivists", "tamaas-trading",
        "titan-fall-pmc",
    },
    # Every one of these is linked from the cosmology page, except the Plane
    # of Faerie, which is a stub reached from Aesc Wood.
    "plane": {
        "astral-plane", "ethereal-plane", "plane-of-faerie", "plane-of-mirrors",
        "region-of-dreams", "true-afterlife", "void",
    },
    # Three are the legend of the world map. Aesc Wood is a forest.
    "region": {
        "aesc-wood", "antaeran-plains", "coastal-barrier-range", "sea-of-innas",
    },
    "settlement": {
        "aberystwyth", "athelney", "imperial-capital-of-new-haven",
    },
    # The Index, Homebrew: Items.
    "item": {
        "crystal-stabilization-fluid", "elven-climbers-gloves", "firearms",
        "planar-crystal", "poisoners-quiver",
    },
    # Action Points is under Variant Rules In Effect and Backgrounds under
    # Homebrew: Miscellaneous; Gestalt is a variant rule nothing links to.
    "rules": {"action-points", "backgrounds", "gestalt"},
}

PAGE_FOLDER = {s: f for f, slugs in LOOSE_PAGES.items() for s in slugs}

# Images kept in docs/img but not placed on any page. The file stays where it
# is, so putting one back is a matter of referencing it again.
#
# The under-construction sign marked pages that were still being written - it
# sat on 24 of them. work-in-progress.md records which, since that is the only
# place the information survives once the sign is off the pages.
#
# It reached the import named after the first page that used it, which is worth
# knowing: shared images take the name of whichever page referenced them first,
# and that name is misleading everywhere else.
DROP_IMAGES = {
    "shared_under_construction.png",
}

# Images swapped for a different file. The original stays in docs/img rather
# than being deleted, so it can be put back by editing this map.
REPLACE_IMAGES = {
    "start_header.png": "start_header_spelljammer.jpg",
}

# Where an image came from. Rendered under it as a credit line, matching how
# the wiki already credits the art it borrows.
IMAGE_CREDITS = {
    "start_header_spelljammer.jpg":
        "https://store.epicgames.com/news/neverwinter-s-developers-talk-"
        "spelljammer-space-and-intergalactic-travel?lang=en-US",
}

# Sections retired from the live wiki. Pages under these folders are flagged
# archived: kept and readable, but out of the glossary and out of search, so
# they cannot be mistaken for current material.
ARCHIVED_FOLDERS = {"wm"}

TODO = []


def target_path(slug):
    """Where a Wikidot slug lands under docs/."""
    if slug == "start":
        return "index.md"
    slug = slug.replace(":", "-")
    if slug in MERGE_PARTS:
        return MERGE_PARTS[slug][0] + ".md"
    if slug in PAGE_FOLDER:
        return PAGE_FOLDER[slug] + "/" + slug + ".md"
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

    # The items. None of these pages carried a name of its own, so the titles
    # were built from their slugs and lost the punctuation - "Poisoners
    # Quiver", "Elven Climbers Gloves". These are the names The Index gives
    # them, which is the wiki's own naming rather than a guess.
    "crystal-stabilization-fluid": "Crystal Stabilization Fluid",
    "elven-climbers-gloves": "Elven Climber's Gloves",
    "poisoners-quiver": "Poisoner's Quiver",
    "item-blessed-holy-symbol": "Profane/Blessed (Un)Holy Symbol",
    "item-dreaming-waking": "The Dreaming & Waking",
}

# Items whose page opens straight into the stat block, with the item's name
# nowhere on it. On Wikidot the name came from the page header above the body;
# here it has to be on the page. The title becomes the opening heading.
#
# "The Dreaming & Waking" is not in this list: its page already opens with the
# book's full in-world title, "The Book of Dreams, a Treatise on the Waking &
# Dreaming". The short name from The Index is the page title, the long one
# stays the heading.
NAME_HEADING = {
    "crystal-stabilization-fluid",
    "elven-climbers-gloves",
    "poisoners-quiver",
    "item-blessed-holy-symbol",
}


# Headings too generic to serve as a page title.
GENERIC_HEADINGS = {
    "overview", "introduction", "intro", "summary", "description",
    "background", "contents", "about",
}


def norm_slug(target):
    """Normalise a Wikidot link target the way Wikidot itself does.

    Links are written either as a slug ("deity-ukrol") or as a page title
    ("Ethereal Plane"), and Wikidot resolves both to the same page. Matching
    only the literal slug turned every title-form link into plain text.

    Accented letters transliterate rather than vanish - "Æsc Wood" is the page
    "aesc-wood", not "sc-wood" - and apostrophes are dropped rather than
    becoming a separator, so "Sil'Faraan" is "silfaraan".
    """
    t = target.strip().lstrip("/").lower()
    t = t.replace("æ", "ae").replace("œ", "oe").replace("ß", "ss").replace("ø", "o")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"['‘’]", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def title_from(slug):
    """Human title from a slug, minus any prefix that only classifies it."""
    m = re.match(r"^([a-z]+)-(.+)$", slug)
    if m and (m.group(1) in FOLDERS or m.group(1) in TITLE_PREFIXES):
        slug = m.group(2)
    return slug.replace(":", " ").replace("-", " ").replace("_", " ").strip().title()


def _cell_width(attrs):
    m = re.search(r"width:\s*([\d.]+)\s*%", attrs or "", re.I)
    return float(m.group(1)) if m else None


def _is_data_grid(rows):
    """True when a [[table]] holds tabular data rather than page layout.

    Wikidot used tables for both. A grid of short values is data; anything
    carrying a heading or a paragraph of prose is layout, and flattening it
    into a Markdown table would destroy the page's shape.
    """
    if len(rows) < 2:
        return False
    counts = {len(r) for r in rows}
    if len(counts) != 1 or counts.pop() < 2:
        return False
    for row in rows:
        for _, body in row:
            if re.search(r"^\s*\+", body, re.M):
                return False
            if len(body.strip()) > 200:
                return False
    return True


def tables_to_layout(s):
    """Wikidot tables become Markdown tables (data) or cards (layout).

    Layout cells keep their proportions: a 25%/75% row stays a sidebar beside
    its content on a wide screen and stacks on a narrow one.
    """

    def repl(m):
        # The table's own width, where it declared one. 107 of them ask for
        # 66.7%, which is how the wiki kept its cards off the full width of the
        # page; carrying it through is more faithful than guessing a cap.
        table_w = _cell_width(m.group(0)[:m.group(0).find("]]")])

        rows = []
        for rm in re.finditer(r"\[\[row[^\]]*\]\](.*?)\[\[/row\]\]", m.group(1), re.S | re.I):
            cells = [(cm.group(1), cm.group(2)) for cm in
                     re.finditer(r"\[\[cell([^\]]*)\]\](.*?)\[\[/cell\]\]", rm.group(1), re.S | re.I)]
            if cells:
                rows.append(cells)
        if not rows:
            return ""

        if _is_data_grid(rows):
            grid = [[" ".join(b.split()) for _, b in r] for r in rows]
            width = max(len(r) for r in grid)
            grid = [r + [""] * (width - len(r)) for r in grid]
            head = "| " + " | ".join(grid[0]) + " |"
            sep = "|" + "---|" * width
            body = "\n".join("| " + " | ".join(r) + " |" for r in grid[1:])
            return "\n\n" + head + "\n" + sep + "\n" + body + "\n\n"

        out = []
        for cells in rows:
            kept = [(a, b) for a, b in cells if b.strip()]
            if not kept:
                continue
            widths = [_cell_width(a) for a, _ in kept]
            # Wikidot rows often size only some cells - "width: 75%" on the
            # content, nothing on the sidebar beside it. Requiring every cell
            # to declare a width made those rows fall back to stacking, which
            # is exactly the layout the width was there to prevent. Share what
            # is left over among the cells that did not declare one.
            if len(kept) > 1 and any(w for w in widths) and not all(w for w in widths):
                known = sum(w for w in widths if w)
                blanks = [i for i, w in enumerate(widths) if not w]
                share = max((100.0 - known) / len(blanks), 5.0)
                for i in blanks:
                    widths[i] = share
            # A narrow column is a sidebar, and gets a smaller font so it reads
            # as an aside rather than a second column of equal weight.
            #
            # Its width is left at the source proportion. These were widened
            # once, to compensate for the content column being 621px against
            # Wikidot's 1402px; now that the page is its proper width, the same
            # widening makes a sidebar look like just another cell.
            classes = ["wd-cell"] * len(kept)
            total = sum(w for w in widths if w) or 100.0
            if len(kept) > 1:
                for i, w in enumerate(widths):
                    if w and (w / total) * 100 < 35:
                        classes[i] = "wd-cell wd-aside"

            props = []
            if len(kept) > 1 and all(w for w in widths):
                # A custom property, not grid-template-columns directly: the
                # stylesheet applies it only above the mobile breakpoint so the
                # columns still stack on a phone.
                props.append("--wd-cols: %s" % " ".join("%gfr" % w for w in widths))
            if table_w and table_w < 100:
                # Resolved against Wikidot's own 1402px page rather than left
                # as a percentage. A percentage is relative to whatever column
                # it lands in, so the same table came out a different size here
                # than it did there; the pixel width is what the reader saw.
                props.append("--wd-rw: %dpx" % round(table_w / 100.0 * 1402))
            style = ' style="%s"' % "; ".join(props) if props else ""
            out.append('<div class="wd-row"%s markdown>' % style)
            for idx, (_, body) in enumerate(kept):
                out.append('<div class="%s" markdown>' % classes[idx])
                out.append("")
                out.append(body.strip())
                out.append("")
                out.append("</div>")
            out.append("</div>")
        return "\n\n" + "\n".join(out) + "\n\n"

    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\[\[table[^\]]*\]\](.*?)\[\[/table\]\]", repl, s, flags=re.S | re.I)
    return s


_COL = re.compile(
    r'<div class="wd-col" style="--wd-w: ([\d.]+%)" markdown>\n(.*?)\n</div>\n',
    re.S,
)


def merge_column_runs(s):
    """Turn a run of equal-width floated divs into one balanced column flow.

    The wiki built columns by floating two or three divs side by side and
    splitting the content between them by hand. Separate boxes cannot balance
    against each other, so a long entry in the second column left the first
    ending halfway up the page.

    Merging a run into a single multi-column element lets the browser balance
    the heights, and because it fills the first column before the second, the
    weight falls to the left.
    """

    out, run, pos = [], [], 0

    def flush():
        if not run:
            return
        if len(run) == 1:
            width, body = run[0]
            out.append('<div class="wd-col" style="--wd-w: %s" markdown>\n%s\n</div>\n'
                       % (width, body))
        else:
            cols = max(2, min(4, int(round(100.0 / float(run[0][0].rstrip("%"))))))
            joined = "\n\n".join(b.strip() for _, b in run)
            out.append('<div class="wd-cols" style="--wd-n: %d" markdown>\n\n%s\n\n</div>\n'
                       % (cols, joined))
        del run[:]

    for m in _COL.finditer(s):
        gap = s[pos:m.start()]
        # Anything between two of these divs, or a change of width, ends the run.
        if gap.strip() or (run and run[0][0] != m.group(1)):
            flush()
        out.append(gap)
        run.append((m.group(1), m.group(2)))
        pos = m.end()

    flush()
    out.append(s[pos:])
    return "".join(out)


def unwrap_table_only_cards(s):
    """Strip the card box from a cell holding nothing but a table or image.

    The rules tables were screenshots sitting inside a layout cell. Now that
    they are real Markdown tables, the card would draw a border around
    something that already has one. The cell keeps its place in the row - it
    is often one column of a two-column layout - it just loses the box.
    Cells holding prose keep their card.
    """

    def repl(m):
        inner = m.group(1)
        if "<div" in inner:
            return m.group(0)
        lines = [l for l in inner.split("\n") if l.strip()]
        if not lines:
            return m.group(0)
        table_lines = [l for l in lines if l.lstrip().startswith("|")]
        image_lines = [l for l in lines if l.lstrip().startswith("![](")]
        # One spare line each way, so a caption still counts as media-only.
        table_only = len(table_lines) >= 2 and len(lines) - len(table_lines) <= 1
        image_only = len(image_lines) >= 1 and len(lines) - len(image_lines) <= 1
        if not (table_only or image_only):
            return m.group(0)
        return m.group(0).replace('class="wd-cell"', 'class="wd-cell wd-plain"', 1)

    return re.sub(r'<div class="wd-cell" markdown>(.*?)\n</div>', repl, s, flags=re.S)


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

    s = tables_to_layout(s)

    # Images: swap the imgur URL for the local file, or inline the transcribed
    # table when the picture was a picture of a table.
    def image(m):
        url = m.group(1)
        # A sourceless [[image  width="50%"]] is a placeholder for art that was
        # never added - 22 pages carry one, usually in a header table of its
        # own. Dropping it empties that cell, and the empty-cell pass below
        # then removes the table it sat in.
        if not url.lower().startswith("http"):
            return ""
        fn = img_by_url.get(url)
        if not fn:
            return ""
        # Kept in docs/img but deliberately not placed on any page.
        if fn in DROP_IMAGES:
            return ""
        fn = REPLACE_IMAGES.get(fn, fn)
        stem = os.path.splitext(fn)[0]
        if stem in tables:
            return "\n\n" + tables[stem].strip() + "\n\n"
        md = "![](" + BASE + "/img/" + fn + ")"
        credit = IMAGE_CREDITS.get(fn)
        if credit:
            md += "\n\n*[Credits](" + credit + ")*"
        return md

    s = re.sub(r"\[\[f?image\s+([^\s\]]+)[^\]]*\]\]", image, s, flags=re.I)

    # Cells are built before images are resolved, so a cell whose only content
    # was a dropped image is left as an empty box. Clear those, then any row
    # left holding nothing.
    s = re.sub(r'<div class="wd-cell[^"]*" markdown>\s*</div>\s*', "", s)
    s = re.sub(r'<div class="wd-row"[^>]*markdown>\s*</div>\s*', "", s)

    s = unwrap_table_only_cards(s)

    # Links back to the old Wikidot site are internal links written the long
    # way. Left alone they send readers off this wiki and break entirely if
    # that site is ever taken down, so resolve them like any other page
    # reference by rewriting them into Wikidot's own link syntax first.
    # The trailing group swallows any #fragment or ?query: those point at text
    # anchors that do not survive the move, and leaving them made the bare-URL
    # rule fire inside a link that was already bracketed.
    self_url = (r"https?://(?:www\.)?(?:antaera|legendsofantaera)\.wikidot\.com/"
                r"([A-Za-z0-9:_-]+)[^\s\]|]*")
    s = re.sub(r"\[\[\[\s*" + self_url + r"\s*\|([^\]]+)\]\]\]", r"[[[\1|\2]]]", s)
    s = re.sub(r"\[\[\[\s*" + self_url + r"\s*\]\]\]", r"[[[\1]]]", s)
    s = re.sub(r"\[\*?" + self_url + r"\s+([^\]]+)\]", r"[[[\1|\2]]]", s)
    s = re.sub(self_url, r"[[[\1]]]", s)

    # Hide URLs so the italic rule cannot eat the // in https://
    urls = []

    def hide(m):
        urls.append(m.group(0))
        return "\x00U%d\x00" % (len(urls) - 1)

    s = re.sub(r"https?://[^\s\)\]\"']+", hide, s)

    # [[div]] carried the column layouts inside cells - the three-across
    # indexes on The Index are floated 33% divs. Stripping them, as this used
    # to, collapsed those columns into one long list.
    def divopen(m):
        attrs = m.group(1) or ""
        width = re.search(r"width:\s*([\d.]+\s*%)", attrs, re.I)
        cls = ["wd-col"]
        if re.search(r"float:\s*right", attrs, re.I):
            cls.append("wd-col--right")
        if re.search(r"border\s*:", attrs, re.I):
            cls.append("wd-col--boxed")
        style = ' style="--wd-w: %s"' % width.group(1).replace(" ", "") if width else ""
        return '<div class="%s"%s markdown>\n' % (" ".join(cls), style)

    s = re.sub(r"\[\[div([^\]]*)\]\]", divopen, s, flags=re.I)
    s = re.sub(r"\[\[/div\]\]", "\n</div>\n", s, flags=re.I)
    # Only now do the column divs exist to be merged.
    s = merge_column_runs(s)
    # size and span carried no layout, only presentation.
    s = re.sub(r"\[\[/?(?:size|span)[^\]]*\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[note\]\](.*?)\[\[/note\]\]",
               lambda m: "!!! note\n" + "\n".join("    " + l for l in m.group(1).strip().split("\n")),
               s, flags=re.S | re.I)

    here = os.path.dirname(target_path(slug))

    def link(target, text):
        dest = linkmap.get(norm_slug(target))
        if not dest:
            return text
        # A merged page's entry carries the anchor of the half that was asked
        # for. Only the path part takes place in the relative-path maths.
        dest, _, anchor = dest.partition("#")
        rel = os.path.relpath(dest, here or ".").replace("\\", "/")
        if anchor:
            rel += "#" + anchor
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

    # Ordered lists BEFORE headings: Wikidot writes "# item" for a numbered
    # list, which Markdown reads as an H1. Converting headings first would
    # then turn those list items into headings and hide the collision.
    s = re.sub(r"^( *)#\s+(.+)$",
               lambda m: "    " * len(m.group(1)) + "1. " + m.group(2), s, flags=re.M)

    s = re.sub(r"^(\+{1,6})\s*(.+)$",
               lambda m: "#" * len(m.group(1)) + " " + m.group(2).strip(), s, flags=re.M)
    s = re.sub(r"(?<!\w)//(?=\S)(.+?)(?<=\S)//(?!\w)", r"*\1*", s, flags=re.S)
    s = re.sub(r"(?<!-)--(?=\S)(.+?)(?<=\S)--(?!-)", r"~~\1~~", s)
    s = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<u>\1</u>", s)
    # Bullets. Wikidot nests with a single space per level; Markdown needs four
    # to read an item as a sublist, so one space produced a flat list.
    s = re.sub(r"^( *)\*\s+", lambda m: "    " * len(m.group(1)) + "- ", s, flags=re.M)
    # An index written as "* 01: Something" is an ordered list wearing bullets.
    # Only the colon form qualifies: "01-95 Standard system" is a dice range,
    # not a sequence, and has to stay a bullet.
    numbered = re.compile(r"^(\s*)-\s+(\d{1,3}):\s+(.*)$")
    lines, rebuilt, i = s.split("\n"), [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and numbered.match(lines[j]):
            j += 1
        if j - i >= 2:
            for k in range(i, j):
                m = numbered.match(lines[k])
                rebuilt.append("%s%d. %s" % (m.group(1), int(m.group(2)), m.group(3)))
            i = j
        else:
            rebuilt.append(lines[i])
            i += 1
    s = "\n".join(rebuilt)

    s = re.sub(r"^-{4,}$", "---", s, flags=re.M)

    # Markdown needs a blank line before a list. Wikidot does not, and wrote
    # lists straight under the paragraph that introduces them - without this
    # the whole list is folded into that paragraph and renders as prose.
    item = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
    lines, spaced = s.split("\n"), []
    for ln in lines:
        if item.match(ln) and spaced and spaced[-1].strip() and not item.match(spaced[-1]):
            spaced.append("")
        spaced.append(ln)
    s = "\n".join(spaced)
    s = re.sub(r"\x00T(\d+)\x00", lambda m: blocks[int(m.group(1))], s)
    s = re.sub(r"\x00U(\d+)\x00", lambda m: urls[int(m.group(1))], s)
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = spell_cards(s)
    s = expand_item_blocks(s)
    s = stat_line_breaks(s)
    return s.strip() + "\n"


# ---------------------------------------------------------------------------
# Spell cards
#
# A spell or psionic power written as a stat block. The wiki has one house
# format for these; the pages disagreed with each other on nearly every point
# of it, so this normalises them all to:
#
#   title        the spell's name, bold, no italics
#   school       directly below, italic, no bold
#   stat block   after a blank line, one stat per line, "**Label**: value", in
#                the order Level, Components, Casting Time, Range, Target (or
#                Area/Effect), Duration, Saving Throw, Spell Resistance
#   flavour      after a blank line, one fully italic paragraph - where the
#                spell already has one. None are invented.
#   description  after a blank line, plain text, any number of paragraphs
#   component    a bold sub-header ("Material Component", "Focus") with its
#                description italicised on the line below
#
# The stat lines need explicit breaks. Wikidot renders a single newline inside
# a paragraph as <br> and Markdown does not, so every stat block on the site
# was running together into one paragraph of prose.
# ---------------------------------------------------------------------------

SPELL_HEAD = re.compile(r"^(?:(#{2,4})\s+(.+)|\*\*([^*]+)\*\*)\s*$")
STAT = re.compile(r"^\*\*([^*]+?)\*\*\s*:\s?(.*)$")

# The order stats are listed in. Alternatives share a rank because they fill
# the same slot: a power's Display is its Components, an Area is its Target.
STAT_ORDER = {
    "level": 0,
    "components": 1, "display": 1,
    "casting time": 2, "manifesting time": 2,
    "range": 3,
    "target": 4, "targets": 4, "area": 4, "area of effect": 4, "effect": 4,
    "duration": 5,
    "saving throw": 6,
    "spell resistance": 7,
}

# A stat block using any of these is a psionic power rather than a spell.
PSIONIC_STATS = {"display", "manifesting time", "power points"}

# The order a magic item lists its stats in.
ITEM_ORDER = {
    "price (item level)": 0,
    "body slot": 1,
    "caster level": 2,
    "aura": 3,
    "activation": 4,
    "weight": 5,
}

# Sub-headers that introduce a component. The wiki wrote these three different
# ways - bold, italic, and inline with a colon - for the same thing.
COMPONENT_HEAD = re.compile(
    r"^[*]{0,3}(Material Components?|Focus|Arcane Focus|Divine Focus|"
    r"XP Cost)[*]{0,3}\s*:?\s*(.*)$", re.I)


def _emphasise(text, marks):
    """Re-mark a line: strip any existing emphasis, then apply `marks`."""
    text = text.strip()
    text = re.sub(r"^[*_]+|[*_]+$", "", text).strip()
    return marks + text + marks if text else text


def normalise_spell(block):
    """One spell block, rewritten to the house format."""
    out = [block[0]]                                   # title, left as it is
    i = 1
    while i < len(block) and not block[i].strip():      # skip a blank after it
        i += 1

    # School: italic, never bold, directly under the title.
    if i < len(block) and not STAT.match(block[i]):
        out.append(_emphasise(block[i], "*"))
        i += 1

    # Stat block: gather the run, order it, one per line.
    stats = []
    while i < len(block):
        if not block[i].strip():
            i += 1
            continue
        m = STAT.match(block[i])
        if not m:
            break
        stats.append((m.group(1).strip(), m.group(2).strip()))
        i += 1

    if stats:
        stats.sort(key=lambda kv: STAT_ORDER.get(kv[0].lower(), 99))
        out.append("")
        for n, (k, v) in enumerate(stats):
            # <br> on every line but the last: Markdown would otherwise fold
            # the whole run into a single paragraph.
            out.append("**%s**: %s%s" % (k, v, "" if n == len(stats) - 1 else "<br>"))

    # The rest of the block, with component sub-headers put right.
    rest = block[i:]
    # Two pages ran the description straight on from the last stat, which
    # Markdown reads as more of the same paragraph.
    if stats and rest and rest[0].strip():
        out.append("")
    n = 0
    while n < len(rest):
        ln = rest[n]
        m = COMPONENT_HEAD.match(ln.strip()) if ln.strip() else None
        if m and not STAT.match(ln):
            while out and not out[-1].strip():
                out.pop()
            out.append("")
            # The description goes on the line below the sub-header, which
            # needs the same explicit break the stat lines do.
            out.append("**" + m.group(1) + "**<br>")
            trailing = m.group(2).strip()
            if trailing:                       # was written inline: "*Focus*: a mirror"
                out.append(_emphasise(trailing, "*"))
                n += 1
                continue
            n += 1
            while n < len(rest) and not rest[n].strip():
                n += 1
            if n < len(rest):
                out.append(_emphasise(rest[n], "*"))
                n += 1
            continue
        out.append(ln)
        n += 1

    kind = "Psionic Power" if any(k.lower() in PSIONIC_STATS for k, _ in stats) else "Spell"
    return out, kind


# The older, compressed way the wiki wrote a magic item: everything on one
# line, semicolon separated.
#
#   Moderate Transmutation; CL 9; Craft Wondrous Item, *create portal*;
#   Price 81,000 gp; Weight 5 lbs
#
# It carries four of the six fields. Body Slot and Activation were never
# written down for these items, so they get an em dash rather than a guess.
COMPRESSED_ITEM = re.compile(
    r"^(?P<aura>[^;]+); CL (?P<cl>\d+); (?P<prereq>.+); "
    r"Price (?P<price>[^;]+); Weight (?P<weight>.+?)\s*$")


def _ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def expand_item_blocks(s):
    """Rewrite the compressed item line as the wiki's six-field block.

    The block moves to the top of its section, under the item's name, which is
    where the other item pages put it. The crafting prerequisites are not one
    of the six fields, so they stay at the foot of the section in the same
    italic form those pages use for them.
    """
    lines = s.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        m = COMPRESSED_ITEM.match(lines[i])
        if not m:
            continue
        # Back up to the heading this item sits under.
        h = i
        while h >= 0 and not re.match(r"^#{2,4}\s+\S", lines[h]):
            h -= 1
        if h < 0:
            continue
        lines[i] = "*Prerequisites*: " + m.group("prereq").strip()
        block = [
            "",
            "**Price (Item Level)**: " + m.group("price").strip(),
            "**Body Slot**: —",
            "**Caster Level**: " + _ordinal(m.group("cl")),
            "**Aura**: " + m.group("aura").strip(),
            "**Activation**: —",
            "**Weight**: " + m.group("weight").strip(),
            "",          # or the description folds into the stat paragraph
        ]
        lines[h + 1:h + 1] = block
    return "\n".join(lines)


def stat_line_breaks(s):
    """Put the line breaks back into every run of labelled stat lines.

    Wikidot renders a single newline inside a paragraph as <br>; Markdown
    folds the lines into one paragraph instead. Every block written as

        **Price (Item Level)**: 2800 gp
        **Body Slot**: Neck

    was therefore reaching the page as one run-on line of prose. It is the
    same defect the spell blocks had, and it is not confined to them: items,
    backgrounds, feats, ship weapons and ammunition are all written this way.

    A run of two or more consecutive labelled lines gets its breaks back. One
    such line on its own is a sentence with a bold lead-in, not a stat block,
    and is left alone. Magic items are also put in the wiki's field order.
    """
    lines = s.split("\n")
    i = 0
    while i < len(lines):
        if not STAT.match(lines[i]) or lines[i].endswith("<br>"):
            i += 1
            continue
        j = i
        while j < len(lines) and STAT.match(lines[j]) and not lines[j].endswith("<br>"):
            j += 1
        if j - i >= 2:
            run = [STAT.match(l).groups() for l in lines[i:j]]
            if any(k.strip().lower() == "price (item level)" for k, _ in run):
                run.sort(key=lambda kv: ITEM_ORDER.get(kv[0].strip().lower(), 99))
            lines[i:j] = ["**%s**: %s%s" % (k.strip(), v.strip(),
                                            "" if n == len(run) - 1 else "<br>")
                          for n, (k, v) in enumerate(run)]
        i = j
    return "\n".join(lines)


def spell_cards(s):
    """Find the stat blocks, normalise them, and put each in a spell card."""
    lines = s.split("\n")
    found = []
    i = 0
    while i < len(lines):
        m = SPELL_HEAD.match(lines[i])
        if m and any(l.startswith("**Level**") for l in lines[i + 1:i + 4]):
            depth = len(m.group(1)) if m.group(1) else 99
            j = i + 1
            while j < len(lines):
                h = re.match(r"^(#{1,6})\s+", lines[j])
                if (h and len(h.group(1)) <= depth) or lines[j].startswith("</div>"):
                    break
                j += 1
            found.append((i, j))
            i = j
            continue
        i += 1

    for start, end in reversed(found):
        block, kind = normalise_spell(lines[start:end])
        while block and not block[-1].strip():
            block.pop()

        # A block that is the whole of its card becomes that card, rather than
        # a second box drawn inside the first.
        a = start - 1
        while a >= 0 and not lines[a].strip():
            a -= 1
        b = end
        while b < len(lines) and not lines[b].strip():
            b += 1
        whole_cell = (
            a >= 0 and 'class="wd-cell' in lines[a]
            and b < len(lines) and lines[b].startswith("</div>")
        )
        if whole_cell:
            lines[a] = lines[a].replace(
                ' markdown>', ' data-wd-kind="%s" markdown>' % kind).replace(
                'class="wd-cell', 'class="wd-cell wd-spell', 1)
            lines[start:end] = block + [""]
        else:
            lines[start:end] = (
                ['<div class="wd-spell" data-wd-kind="%s" markdown>' % kind, ""]
                + block + ["", "</div>", ""])
    return "\n".join(lines)


def main(backup):
    src_dir = os.path.join(backup, "source")
    slugs = [f[:-4] for f in sorted(os.listdir(src_dir))]
    keep = [s for s in slugs if not SKIP.match(s)]
    # Link targets are matched by several names, most specific first, because
    # Wikidot links reference pages by slug and by title interchangeably and
    # often omit the category prefix a slug carries ("House of Fabrication"
    # for the page "faction-house-of-fabrication").
    linkmap = {}
    for s in keep:
        linkmap[norm_slug(s)] = target_path(s)
    # A link to half of a merged page goes to that half's section, not to the
    # top of the page, so "the psionic power" still means the psionic power.
    for part, (merged, anchor) in MERGE_PARTS.items():
        linkmap[norm_slug(part)] = merged + ".md#" + anchor
    for s in keep:
        raw = open(os.path.join(src_dir, s + ".txt"), "rb").read().decode("utf-8", "replace")
        heading = re.search(r"^\+\s+(.+)$", raw, re.M)
        names = []
        if s in TITLES:
            names.append(TITLES[s])
        if heading:
            names.append(re.sub(r"[*_`~\[\]]", "", heading.group(1)).strip())
        m = re.match(r"^([a-z]+)[-_](.+)$", s)
        if m:
            names.append(m.group(2))
        for n in names:
            linkmap.setdefault(norm_slug(n), target_path(s))

    imgs = json.load(open(os.path.join(ROOT, "_migration", "images.json"), encoding="utf-8"))
    img_by_url = {e["url"]: e["final"] for e in imgs}

    # Resolved once so the wip flag can be derived from the page source.
    wip_url = next((e["url"] for e in imgs
                    if e["final"] == "shared_under_construction.png"), None)

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
    merged_bodies = {}
    for slug in keep:
        raw = open(os.path.join(src_dir, slug + ".txt"), "rb").read().decode("utf-8", "replace")
        body = convert(raw, slug, img_by_url, tables, linkmap)

        # Half of a merged page: keep the converted body and write nothing.
        # The whole page is assembled once every half has been converted.
        if slug in MERGE_PARTS:
            merged_bodies[slug] = body
            continue

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

        # A page whose first heading is "Overview" or "Description" opens with
        # that word where its name should be. On Wikidot the name was supplied
        # by the page header above the body, so the heading only ever had to
        # label the section; here there is no such header, and the heading is
        # the first thing on the page. Rename it to the page's own title.
        #
        # Only the leading heading is touched. "Overview" further down a page
        # is a section among others and is doing its job.
        m = re.search(r"^#\s+(.+)$", body, re.M)
        if m:
            plain = re.sub(r"[*_`~]", "", m.group(1)).strip().lower()
            if plain in GENERIC_HEADINGS:
                body = body[:m.start()] + "# " + title + body[m.end():]

        # A page that never names itself gets its title as an opening heading,
        # put inside the first card so it is the panel's title rather than a
        # line floating above the layout.
        if slug in NAME_HEADING:
            # A lambda, not a replacement string: these names carry slashes
            # and parentheses that re would otherwise have to be escaped for.
            body = re.sub(r'<div class="wd-cell[^"]*" markdown>\n\n',
                          lambda m: m.group(0) + "# " + title + "\n\n",
                          body, count=1)

        # The glossary was 26 ListPages queries. It is regenerated at build
        # time by hooks/glossary.py, so the page is just a marker.
        if slug == "glossary":
            title = "Glossary"
            body = (
                "An index of every page on the wiki, in alphabetical order.\n\n"
                "<!-- GLOSSARY -->\n"
            )

        # The Index is the hub for the wiki's own indexes, so Archived Pages
        # hangs off it rather than off the sidebar - the sidebar is a flat list
        # by design, and nesting an item under an entry turns that entry into a
        # section header with a duplicate child.
        if slug == "the-index":
            body += (
                "\n\n<div class=\"wd-row\" markdown>\n"
                "<div class=\"wd-cell\" markdown>\n\n"
                "# Archived Pages\n\n"
                "Sections retired from the current setting, kept for reference. "
                "They do not appear in the glossary or in search.\n\n"
                "[Browse archived pages](archived.md)\n\n"
                "</div>\n</div>\n"
            )

        rel = target_path(slug)

        # Flags are derived from the source, not a hand-kept list: a page is
        # work in progress if it carried the under-construction sign, and
        # archived if it sits in a retired section.
        meta = ['title: "' + title + '"']
        if wip_url and wip_url in raw:
            meta.append("wip: true")
        if rel.split("/")[0] in ARCHIVED_FOLDERS:
            meta.append("archived: true")
            # Honoured natively by Material's search plugin.
            meta.append("search:")
            meta.append("  exclude: true")

        out_abs = os.path.join(DOCS, rel)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        with open(out_abs, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("---\n" + "\n".join(meta) + "\n---\n\n" + body)
        written += 1

    # Merged pages, assembled from the halves collected above.
    for merged, spec in MERGES.items():
        rel = merged + ".md"
        here = os.path.dirname(rel)
        lead = re.sub(
            r"\[\[\[([^\]|]+)\|([^\]]+)\]\]\]",
            lambda m: "[%s](%s)" % (
                m.group(2),
                os.path.relpath(linkmap[norm_slug(m.group(1))], here or ".")
                  .replace("\\", "/")),
            spec["lead"])
        parts = ['<div class="wd-row" style="--wd-rw: 935px" markdown>',
                 '<div class="wd-cell" markdown>', "",
                 "# " + spec["title"], "", lead, "", "</div>", "</div>", ""]
        for label, part in spec["parts"]:
            half = merged_bodies[part]
            # The variants drop a level to sit under their form's heading. The
            # label gets a row of its own rather than going inside the first
            # card - those cards are spell cards, and a section heading is not
            # part of the spell.
            half = re.sub(r"^##(?=\s)", "###", half, flags=re.M)
            # No heading for the group: each card already says whether it is a
            # spell or a psionic power, and a divider saying it again is the
            # same label twice. The anchor moves onto the first card of the
            # group so the links that meant this half still land on it.
            anchor = label.lower().replace(" ", "-")
            half = half.replace('<div class="wd-row"',
                                '<div id="%s" class="wd-row"' % anchor, 1)
            parts.append(half.rstrip() + "\n")
        with open(os.path.join(DOCS, rel), "w", encoding="utf-8", newline="\n") as fh:
            fh.write('---\ntitle: "' + spec["title"] + '"\n---\n\n'
                     + "\n".join(parts))
        written += 1

    # Pages with no Wikidot source. They have to be written here because this
    # script clears docs/ on every run, so anything hand-placed there is lost.
    with open(os.path.join(DOCS, "archived.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            '---\ntitle: "Archived Pages"\n---\n\n'
            "Material kept for reference but no longer part of the current\n"
            "setting. Archived pages do not appear in the glossary or in search\n"
            "results.\n\n"
            "<!-- ARCHIVED-INDEX -->\n"
        )
    written += 1

    print("pages written : %d  (skipped %d system pages)" % (written, len(slugs) - len(keep)))
    print("TODO markers  : %d" % len(TODO))
    for what, n in Counter(w for _, w in TODO).most_common():
        print("    %3d  %s" % (n, what))


if __name__ == "__main__":
    main(sys.argv[1])
