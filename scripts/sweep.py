# -*- coding: utf-8 -*-
"""Housekeeping sweep: is anything on the wiki broken, stale or unsafe?

Run from the repository root, after a build:

    .venv/Scripts/python.exe scripts/sweep.py [built site]

Every check prints "OK" or lists what is wrong, and the run exits non-zero if
any check fails. The pre-push hook runs it on the site it has just built, and
CI on the site it is about to publish, so a page that would ship broken is
stopped before it goes out. It needs nothing but Python and PyYAML.

Three parts:

  THE PAGES    what the pages say and how they are put together - links,
               images, cards, house style, the build itself - read from docs/
               as git has them, and from the site built from them.
  THE CODE     the hooks, the announcer and the workflows: they compile, they
               parse, and what mkdocs.yml names exists.
  SAFETY       nothing that should be a secret is committed: no Discord
               webhook or bot token, no personal email address, and the
               workflows take their secrets from GitHub, never from a file.
"""
import collections
import glob
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = 0
checks = 0


def check(name, bad, note="", limit=12):
    """Report one check. `bad` is a list of things wrong; empty means OK."""
    global failures, checks
    checks += 1
    if not bad:
        print("  OK    %s" % name)
        return
    failures += 1
    print("  FAIL  %s  (%d)" % (name, len(bad)))
    if note:
        print("        %s" % note)
    for b in bad[:limit]:
        print("        - %s" % b)
    if len(bad) > limit:
        print("        ... and %d more" % (len(bad) - limit))


def tracked():
    """The files git keeps: what is actually published, nothing local."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def read(path):
    with io.open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
#   The pages
# ---------------------------------------------------------------------------

DOCS = "docs"
SITE = "site"     # the built site; the command line can name another

# How wide things are on the rendered pages, measured there: sidebar tables
# set at 11.5px, where a character averages about 6px, and each cell adds 29px
# of padding. A card takes 1.1rem of padding off each side, and the gap
# between cells is 1rem.
ASIDE_CHAR_PX = 6.0
ASIDE_CELL_PAD_PX = 29.0
CARD_PAD_PX = 2 * 1.1 * 16
ROW_GAP_PX = 16.0
DEFAULT_ROW_PX = 52 * 16.0


def _table_px(block):
    """Roughly how wide a table wants to be, from the text in its columns."""
    widest = {}
    for line in block.split(chr(10)):
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        for i, cell in enumerate(line.strip("|").split("|")):
            text = re.sub(r"[*`\\]|\[\[|\]\]|\([^)]*\)", "", cell).strip()
            widest[i] = max(widest.get(i, 0), len(text))
    if not widest:
        return 0.0
    return sum(n * ASIDE_CHAR_PX + ASIDE_CELL_PAD_PX for n in widest.values())


def _blocks(text):
    """A cell's content as blocks, a table carrying its caption and notes."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        note = para.strip().endswith("{: .wd-table-note }")
        if out and note and out[-1].lstrip().startswith("|"):
            out[-1] = out[-1] + "\n\n" + para
        else:
            out.append(para)
    return out


def _div_span(text, start):
    """Where the div opening at `start` ends, divs counted rather than guessed."""
    depth = 0
    for m in re.finditer(r"<div\b|</div>", text[start:]):
        depth += 1 if m.group(0)[1] != "/" else -1
        if depth == 0:
            return start + m.end()
    return len(text)


def md_pages():
    for f in sorted(glob.glob(os.path.join(DOCS, "**", "*.md"), recursive=True)):
        yield f.replace("\\", "/"), io.open(f, encoding="utf-8").read()


def body_of(text):
    return text[text.find("\n---", 3) + 4:] if text.startswith("---") else text


def sweep_pages():
    """What the pages say and how they are put together, and the built site."""
    pages = dict(md_pages())
    print("THE PAGES  -  %d pages" % len(pages))
    pages = dict(md_pages())

    # --- structure ---------------------------------------------------------
    print("STRUCTURE")

    bad = []
    for f, t in pages.items():
        opens = len(re.findall(r"<div\b", t))
        closes = len(re.findall(r"</div>", t))
        if opens != closes:
            bad.append("%s  %d <div> vs %d </div>" % (f, opens, closes))
    check("every card and row is closed", bad)

    bad = []
    for f, t in pages.items():
        # A URL contains "//" and a Markdown link contains "]]" only by
        # accident, so both are taken out before looking for Wikidot's markup.
        probe = re.sub(r"https?://\S+", "", body_of(t))
        if re.search(r"\[\[\[|\]\]\]|^\+{1,4}\s|//[A-Za-z][^/\n]*//", probe, re.M):
            bad.append(f)
    check("no Wikidot markup left", bad,
          "[[[links]]], + headings, //italics//")

    bad = []
    for f, t in pages.items():
        for m in re.finditer(r'<div class="wd-cell[^"]*" markdown>\s*\n\s*\n\s*</div>', t):
            bad.append(f)
    check("no empty cards", bad)

    bad = []
    for f, t in pages.items():
        lv = sorted({len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", t, re.M)})
        for a, b in zip(lv, lv[1:]):
            if b - a > 1:
                bad.append("%s  %s" % (f, lv))
                break
    check("no page skips a heading level", bad)

    bad = [f for f, t in pages.items()
           if not re.search(r"^#\s", body_of(t), re.M) and len(body_of(t).split()) > 30]
    check("every page with a body names itself", bad)

    # A page's content should be on a card, not loose on the background.
    bad = []
    for f in sorted(glob.glob(os.path.join(SITE, "**", "index.html"), recursive=True)):
        h = io.open(f, encoding="utf-8").read()
        m = re.search(r'<article[^>]*md-content__inner[^>]*>(.*)</article>', h, re.S)
        if not m:
            continue
        loose = re.sub(r'<div class="wd-row.*?(?=<div class="wd-row|<aside|$)', "",
                       m.group(1), flags=re.S)
        loose = re.sub(r'<aside.*', "", loose, flags=re.S)
        loose = re.sub(r'<div class="wd-(flag|wip)[^"]*".*?</div>', "", loose, flags=re.S)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", loose)).strip()
        if len(txt) > 40:
            bad.append("%s  %r" % (f.replace("\\", "/"), txt[:48]))
    check("no body text off a card", bad)

    # The wiki has no code. A line indented four spaces after a blank line is
    # a code block to Markdown, so a list written that way prints as grey
    # monospace with a copy button. Paxaeterna's primary body did exactly that.
    check("no page prints a code block",
          [f.replace("\\", "/")
           for f in sorted(glob.glob(os.path.join(SITE, "**", "index.html"), recursive=True))
           if "<pre" in io.open(f, encoding="utf-8").read()],
          "an indented line after a blank line is read as code")

    # --- links and images --------------------------------------------------
    print("\nLINKS AND IMAGES")

    targets = {f[len(DOCS) + 1:] for f in pages}
    bad = []
    for f, t in pages.items():
        here = os.path.dirname(f[len(DOCS) + 1:])
        for m in re.finditer(r"\]\(([^)#][^)]*\.md)(#[^)]*)?\)", t):
            dest = os.path.normpath(os.path.join(here, m.group(1))).replace("\\", "/")
            if dest not in targets:
                bad.append("%s -> %s" % (f, m.group(1)))
    check("every internal link resolves", bad)

    anchors = {}
    for f, t in pages.items():
        ids = set(re.findall(r'id="([^"]+)"', t))
        for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", t, re.M):
            h = re.sub(r"[*_`~]", "", m.group(1)).strip().lower()
            ids.add(re.sub(r"[^a-z0-9]+", "-", h).strip("-"))
        anchors[f[len(DOCS) + 1:]] = ids
    bad = []
    for f, t in pages.items():
        here = os.path.dirname(f[len(DOCS) + 1:])
        for m in re.finditer(r"\]\(([^)#]*\.md)#([^)]+)\)", t):
            dest = os.path.normpath(os.path.join(here, m.group(1))).replace("\\", "/")
            if dest in anchors and m.group(2) not in anchors[dest]:
                bad.append("%s -> %s#%s" % (f, m.group(1), m.group(2)))
        # A link with nothing in front of the "#" points into its own page, and
        # goes stale the moment the heading it names is reworded.
        for m in re.finditer(r"\]\(#([^)]+)\)", t):
            if m.group(1) not in anchors[f[len(DOCS) + 1:]]:
                bad.append("%s -> #%s" % (f, m.group(1)))
    check("every link anchor exists", bad)

    have = {os.path.basename(p) for p in glob.glob(os.path.join(DOCS, "img", "*"))}
    bad = []
    for f, t in pages.items():
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", t):
            if os.path.basename(m.group(1)) not in have:
                bad.append("%s -> %s" % (f, m.group(1)))
    check("every image file exists", bad)

    # An A-Z index is three columns of letters, nine, nine and eight, split in
    # the page itself rather than by the browser balancing column heights.
    bad = []
    for f, t in pages.items():
        if re.search(r'<div class="wd-cols"[^>]*>(?:(?!</div>).)*?^#{1,6} [A-Za-z](?: \{: \.wd-empty \})?$',
                     t, re.S | re.M):
            bad.append("%s  an alphabet left to CSS columns" % f)
        for m in re.finditer(r'<div class="wd-index" markdown>', t):
            # Divs counted rather than guessed at: the columns are divs inside
            # a div, and a pattern that stops at the first close stops a
            # column early.
            block = t[m.start():_div_span(t, m.start())]
            counts, i = [], len("<div class=\"wd-index\" markdown>")
            while True:
                c = block.find("<div markdown>", i)
                if c < 0:
                    break
                e = _div_span(block, c)
                counts.append(len(re.findall(r"^#{1,6} [A-Za-z](?: \{: \.wd-empty \})?$", block[c:e], re.M)))
                i = e
            if len(counts) != 3 or max(counts) - min(counts) > 1:
                bad.append("%s  columns hold %s letters" % (f, counts))
    check("an A-Z index splits evenly into three columns", bad)

    # A table in a narrow column of a split row. One that does not fit belongs
    # in a card of its own on the next line; this says so if one is squeezed
    # into the column. A spell card keeps its tables: they are lines of the
    # stat block, not a table beside it.
    bad = []
    for f, t in pages.items():
        for rm in re.finditer(r'<div class="wd-row"[^>]*>', t):
            row = t[rm.start():_div_span(t, rm.start())]
            cols = re.search(r'--wd-cols:\s*([^;"]+)', row)
            if not cols:
                continue
            shares = [float(c.rstrip("fr")) for c in cols.group(1).split()]
            total = sum(shares) or 1.0
            rw = re.search(r"--wd-rw:\s*([\d.]+)px", row)
            width = float(rw.group(1)) if rw else DEFAULT_ROW_PX
            inner = width - ROW_GAP_PX * (len(shares) - 1)
            i, n = 0, 0
            while n < len(shares):
                c = row.find('<div class="wd-cell', i)
                if c < 0:
                    break
                e = _div_span(row, c)
                cell, i, n = row[c:e], e, n + 1
                if "wd-spell" in cell.split(chr(10), 1)[0]:
                    continue
                fits = inner * shares[n - 1] / total - CARD_PAD_PX
                for block in _blocks(cell):
                    if block.lstrip().startswith("|") and _table_px(block) > fits:
                        head = block.split(chr(10), 1)[0][:50]
                        bad.append("%s  %s  wants %dpx in %dpx"
                                   % (f, head, _table_px(block), fits))
    check("no table is squeezed into a sidebar", bad)

    used = {os.path.basename(m.group(1))
            for t in pages.values()
            for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", t)}
    # Three kinds of image are on no page on purpose: the work-in-progress
    # sign, which the flag hook places; the original main-page header, kept so
    # it can be put back; and the 37 screenshots of tables, which were
    # transcribed into real Markdown tables and are kept as the source those
    # were read from.
    keep = {"shared_under_construction.png", "start_header.png"}
    stray = sorted(n for n in (have - used - keep) if "_table" not in n)
    check("no image is unaccounted for", stray,
          "kept in docs/img but on no page and not a transcribed table")

    bad = [f for f, t in pages.items() if "imgur.com" in t]
    check("nothing still points at imgur", bad)

    # --- house style -------------------------------------------------------
    print("\nHOUSE STYLE")

    check("the world's name carries its ligature",
          ["%s x%d" % (f, len(re.findall(r"\bAntaera", t)))
           for f, t in pages.items() if re.search(r"\bAntaera", t)])

    check("no underline tags",
          ["%s x%d" % (f, t.count("<u>")) for f, t in pages.items() if "<u>" in t])

    check("labels are bold, not italic",
          ["%s  %s" % (f, m.group(0)[:34])
           for f, t in pages.items()
           for m in re.finditer(r"^\*[A-Za-z][^*\n]{1,38}\*\s*:", t, re.M)])

    check("no heading ends in a colon",
          ["%s  %s" % (f, m.group(0)[:40])
           for f, t in pages.items()
           for m in re.finditer(r"^#{1,6} .*:$", t, re.M)])

    bad = []
    for f, t in pages.items():
        for l in t.split("\n"):
            if not l.lstrip().startswith("|"):
                continue
            for cell in (c.strip() for c in l.split("|")):
                if re.fullmatch(r"[-–](\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+)?", cell):
                    bad.append("%s  %r" % (f, cell))
    check("a blank table cell is an em dash", bad)

    # A z-index on one of Material's own containers makes it a stacking
    # context, and everything inside it is then trapped at that container's
    # level however high its own z-index is. That is not visible in a build or
    # on a desktop screen: it is what put the navigation drawer on a phone
    # underneath the dark overlay meant to sit behind it, so the menu opened,
    # the screen went dark, and nothing could be tapped. The site's own sheets
    # should leave Material's layering alone and put the sky below the page.
    bad = []
    for sheet in sorted(glob.glob(os.path.join(DOCS, "stylesheets", "*.css"))):
        css = io.open(sheet, encoding="utf-8").read()
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            sel, body = m.group(1).strip().split("\n")[-1], m.group(2)
            if ".md-" in sel and re.search(r"\bz-index\s*:", body):
                bad.append("%s  %s" % (os.path.basename(sheet), sel[:48]))
    check("no z-index on a Material container", bad,
          "it becomes a stacking context and traps the drawer under the overlay")

    check("alignments are abbreviated",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r"\b(?:lawful|chaotic|neutral|true) (?:good|evil|neutral)\b"
                                r"|\((?:Neutral|TN)\)", body_of(t), re.I)])

    # The wiki says deities, not gods, except where a name says otherwise.
    keep = re.compile(r"(?:Patron )?God(?:dess)? of [A-Z]\w+"
                      r"|(?:Living|Primal) Gods"
                      r"|Graveyard of the Gods|the Lost God")
    bad = []
    for f, t in pages.items():
        b = keep.sub(" ", re.sub(r"\]\([^)]*\)|<[^>]+>|https?://\S+", " ", body_of(t)))
        for m in re.finditer(r"\b[Gg]ods?\b", b):
            bad.append("%s  %s" % (f, re.sub(r"\s+", " ", b[max(0, m.start() - 34):m.end() + 20])))
    check("the wiki says deities, not gods", bad)

    check("a sphere labels its ranks like every other sphere",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items() if re.match(r"docs/spelljamming/sphere-", f)
           for m in re.finditer(r"^\*\*(?:Lesser|Intermediate|Greater)\*\*:?[ \t]*$"
                                r"|^\*\*[A-Za-z][^*\n]*\*\*:[ \t]*$", body_of(t), re.M)])

    # The licence has to be whole to be a licence: all fifteen sections, its
    # own copyright notice, and the line that ends it.
    lic = body_of(pages.get("docs/disclaimer-legal.md", ""))
    bad = []
    nums = re.findall(r"(?m)^(\d{1,2})\\\. ", lic)
    if nums != [str(i) for i in range(1, 16)]:
        bad.append("sections present: %s" % nums)
    if "END OF LICENSE" not in lic:
        bad.append("no END OF LICENSE")
    if "Open Game License v 1.0a Copyright 2000, Wizards of the Coast, Inc." not in lic:
        bad.append("section 15 does not carry the licence's own notice")
    if "System Reference Document Copyright 2000-2003" not in lic:
        bad.append("section 15 does not carry the SRD notice")
    check("the Open Game License is whole", bad)

    # Every page's footnote carries the author's note. Every page but the legal
    # one carries the fan content notice too; the legal page has that as a
    # card, where the footnote would be the same words twice. And the note is
    # said once, in the footnote, not again in a page's own text.
    bad = []
    for f in sorted(glob.glob(os.path.join(SITE, "**", "index.html"), recursive=True)):
        h = io.open(f, encoding="utf-8").read()
        rel = f.replace(chr(92), "/")
        legal = "/disclaimer-legal/" in rel
        foot = re.search(r'<div class="wd-footnote">(.*?)</div>', h, re.S)
        if not foot:
            bad.append("%s  has no footnote" % rel)
            continue
        if "wd-footnote__note" not in foot.group(1):
            bad.append("%s  footnote has no author's note" % rel)
        has_policy = "wd-footnote__policy" in foot.group(1)
        if legal and has_policy:
            bad.append("%s  repeats the fan content card in its footnote" % rel)
        if not legal and not has_policy:
            bad.append("%s  footnote has no fan content notice" % rel)
    lic = body_of(pages.get("docs/disclaimer-legal.md", ""))
    if "Fan Content Policy" not in lic:
        bad.append("the legal page has no fan content card")
    bad += ["%s  says the author's note in its own text as well" % f
            for f, t in pages.items() if "As a note from the author" in body_of(t)]
    check("the footnote carries what it should, everywhere", bad)

    # A paragraph that belongs to a list item has to be indented four spaces.
    # Indented fewer, Markdown ends the list and prints it as the next
    # paragraph of the page instead.
    # A bold label on the line straight after a list item is read as more of
    # that item, so it ends the item's sentence instead of heading the next
    # group: the Calendar's Summer, Autumn and Winter all did.
    check("a label after a list starts a line of its own",
          ["%s  %s" % (f, m.group(1))
           for f, t in pages.items()
           for m in re.finditer(r"^[ \t]*(?:[-*+]|\d+\.) .*\n(\*\*[^*\n]+\*\*:?)[ \t]*$",
                                body_of(t), re.M)])

    check("a list item's later paragraphs stay in the item",
          ["%s  %s" % (f, m.group(1)[:50])
           for f, t in pages.items()
           for m in re.finditer(r"\n\n {1,3}([A-Za-z].*)", body_of(t))])

    check("the campaign is not called by its old name",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r".{0,40}Legends of Ant\w+.{0,30}", body_of(t))])

    check("the fey plane is called the Feywild",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r"Plane [Oo]f Faerie|Sidhe Wilderness|Feywilds\b", body_of(t))])

    check("units are ft and lbs",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r"\d\s*(?:feet|foot|pounds)\b|(?<![A-Za-z])(?:ft|lbs)\.(?!\s+[A-Z])", t)])

    # Every god's page follows Format A (the layout every god's page shares): all
    # eight facts in order, the four required sections under bold labels with
    # the prose on the next line, no sub-headings, no symbol section, and a
    # sidebar only where there is a picture to put in it. Stubs follow the stub
    # template. A new god is usually made by copying an old one, and this is
    # what drifts when that happens.
    fields = ["Rank", "Symbol", "Home Plane", "Alignment", "Portfolio", "Worshipers",
              "Cleric Alignments", "Domains", "Favored Weapon"]
    axes = {"LG": (0, 0), "LN": (0, 1), "LE": (0, 2), "NG": (1, 0), "N": (1, 1),
            "NE": (1, 2), "CG": (2, 0), "CN": (2, 1), "CE": (2, 2)}

    def clerics(code):
        # One step on one axis, and no N cleric unless the god is N.
        lc, ge = axes[code]
        near = {(lc, ge)} | {(lc + d, ge) for d in (-1, 1) if 0 <= lc + d <= 2} \
            | {(lc, ge + d) for d in (-1, 1) if 0 <= ge + d <= 2}
        if code != "N":
            near.discard((1, 1))
        return ", ".join(sorted(c for c, a in axes.items() if a in near))
    bad = []
    for f, t in pages.items():
        if not re.match(r"docs/(deity|pantheon)/", f):
            continue
        b = body_of(t)
        if "used for disambiguation" in t:
            if not re.search(r'<div class="wd-row" style="--wd-rw: 935px" markdown>\s*'
                             r'<div class="wd-cell" markdown>\s*# [^\n]+\n\n'
                             r'\*This page is currently used for disambiguation\.\*', b):
                bad.append("%s  stub is not in the stub template" % f)
            continue
        got = re.findall(r"^- \*\*([^*]+)\*\*: ", b, re.M)
        if got[:9] != fields:
            bad.append("%s  facts are %s" % (f, got[:9]))
        al = re.search(r"^- \*\*Alignment\*\*: (\S+)$", b, re.M)
        ca = re.search(r"^- \*\*Cleric Alignments\*\*: (.+)$", b, re.M)
        if not al or al.group(1) not in axes:
            bad.append("%s  alignment is not an abbreviation" % f)
        elif not ca or ca.group(1) != clerics(al.group(1)):
            bad.append("%s  cleric alignments %s, should be %s" % (
                f, ca.group(1) if ca else None, clerics(al.group(1))))
        if re.search(r"^- \*\*Rank\*\*: (?!(Greater|Intermediate|Lesser) Deity$)", b, re.M):
            bad.append("%s  no rank" % f)
        if "*TBD*" in b:
            bad.append("%s  says TBD where it should be an em dash" % f)
        sym = re.search(r"^- \*\*Symbol\*\*: (.+)$", b, re.M)
        if sym and re.search(r"symboli[sz]|represent|signif|\bsymbols? of\b|\bthis symbol\b", sym.group(1), re.I):
            bad.append("%s  symbol describes itself: %s" % (f, sym.group(1)[:40]))
        if re.search(r"^(The symbol of|This symbol)\b", b, re.M):
            bad.append("%s  prose about the symbol that talks about itself" % f)
        for sec in ("Origins", "Description", "Dogma", "Home Sphere"):
            if not re.search(r"^\*\*%s\*\*$" % re.escape(sec), b, re.M):
                bad.append("%s  no %s" % (f, sec))
        if re.search(r"^#{2,6} ", b, re.M):
            bad.append("%s  has a sub-heading" % f)
        if re.search(r"^# \*\*", b, re.M):
            bad.append("%s  a label inside a heading" % f)
        if re.search(r"^\*\*(Holy|Unholy) Symbol\*\*", b, re.M):
            bad.append("%s  a symbol section" % f)
        for m in re.finditer(r'<div class="wd-cell wd-aside" markdown>(.*?)</div>', b, re.S):
            if "![](" not in m.group(1):
                bad.append("%s  a sidebar with no picture" % f)
    check("every god's page follows Format A", bad)

    # The Pantheons lists the weapon beside the alignment, portfolio and
    # symbol, and takes it from the god's own page - finish_site() writes it
    # there. A god listed without one, or with a different one, has drifted.
    pan = pages.get("docs/pantheons.md", "")
    bad = []
    for m in re.finditer(r"^- \[(?P<name>[^\]]+)\]\((?P<href>[^)]+)\)(?P<rest>.*)$",
                         body_of(pan), re.M):
        page = pages.get("docs/" + m.group("href").split("#")[0])
        if page is None:
            continue
        w = re.search(r"^- \*\*Favored Weapon\*\*: (.+)$", body_of(page), re.M)
        if not w or w.group(1) == "\u2014":
            continue
        after = body_of(pan)[m.end():].split("\n- ")[0]
        listed = re.search(r"^\s+- Favored Weapon: (.+)$", after, re.M)
        if not listed:
            bad.append("%s  is listed without a weapon" % m.group("name"))
        elif listed.group(1).strip() != w.group(1).strip():
            bad.append("%s  listed as %s, his page says %s"
                       % (m.group("name"), listed.group(1), w.group(1)))
    check("The Pantheons gives each god the weapon his page does", bad)

    # A god on The Pantheons is listed on a sphere under the rank and with the
    # alignment The Pantheons gives. The spheres are copied from it by hand,
    # and drifted: four gods under the wrong rank on Antaera, one under the
    # wrong alignment.
    gods, tier, last = {}, None, None
    for line in pages.get("docs/pantheons.md", "").split("\n"):
        m = re.match(r"^##[ \t]+(\w+)", line)
        if m:
            tier = m.group(1) if m.group(1) in ("Greater", "Intermediate", "Lesser") else None
            last = None
            continue
        if re.match(r"^#[ \t]", line):
            tier = last = None
            continue
        m = re.match(r"^- \[?([^\],\n]+)", line)
        if m and tier:
            last = m.group(1).strip().lower()
            gods[last] = [tier, None]
            continue
        a = re.match(r"^\s+- Alignment:[ \t]*(\S+)", line)
        if a and last:
            gods[last][1] = a.group(1)
    bad = []
    for f, t in pages.items():
        if not re.match(r"docs/spelljamming/sphere-", f):
            continue
        sec = re.search(r"^# Recognized Pantheon[ \t]*\n(.*?)(?=\n</div>|\n# |\Z)", t, re.M | re.S)
        if not sec:
            continue
        label = ""
        for line in sec.group(1).split("\n"):
            g = re.match(r"^\*\*(.+?)\*\*", line)
            if g:
                label = g.group(1)
                continue
            m = re.match(r"^- (.+?) \(([^)]+)\)[ \t]*$", line)
            if not m:
                continue
            key = re.split(r",| —", m.group(1))[0].strip().lower()
            if key in gods:
                want_tier, want_al = gods[key]
                if want_tier.lower() not in label.lower() or (want_al and m.group(2) != want_al):
                    bad.append("%s  %s under %r (%s); The Pantheons: %s (%s)" % (
                        f, key, label, m.group(2), want_tier, want_al))
    check("sphere pantheons agree with The Pantheons", bad)

    # --- content -----------------------------------------------------------
    print("\nCONTENT")

    titles = collections.defaultdict(list)
    for f, t in pages.items():
        m = re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M)
        if m:
            titles[m.group(1)].append(f)
    dupes = []
    for name, fs in sorted(titles.items()):
        if len(fs) > 1:
            # A disambiguation stub shares its name with the article it points
            # at; that is the whole job of one.
            live = [f for f in fs
                    if "\narchived: true" not in pages[f][:400]
                    and "used for disambiguation" not in pages[f]]
            if len(live) > 1:
                dupes.append("%s  %s" % (name, ", ".join(live)))
    check("no two live pages share a title", dupes)

    check("no page is nearly empty",
          ["%s  %d words" % (f, len(body_of(t).split()))
           for f, t in pages.items()
           if len(body_of(t).split()) < 12 and "GLOSSARY" not in t
           and "ARCHIVED-INDEX" not in t])

    orphans = set(pages) - {os.path.normpath(os.path.join(
        os.path.dirname(f), m.group(1))).replace("\\", "/")
        for f in pages for m in re.finditer(r"\]\(([^)#][^)]*\.md)", pages[f])}
    nav = io.open("mkdocs.yml", encoding="utf-8").read()
    orphans = {o for o in orphans
               if o[len(DOCS) + 1:] not in nav and o != "docs/index.md"}
    # links were resolved relative to the file, so re-resolve properly
    linked = set()
    for f, t in pages.items():
        here = os.path.dirname(f)
        for m in re.finditer(r"\]\(([^)#][^)]*\.md)", t):
            linked.add(os.path.normpath(os.path.join(here, m.group(1))).replace("\\", "/"))
    # The archived index is generated at build time, so the pages it lists are
    # reachable even though no Markdown file links to them.
    generated = set()
    idx = os.path.join(SITE, "archived", "index.html")
    if os.path.exists(idx):
        for m in re.finditer(r'href="\.\./([^"]+)/"', io.open(idx, encoding="utf-8").read()):
            generated.add("%s/%s.md" % (DOCS, m.group(1).rstrip("/") or "index"))
            generated.add("%s/%s/index.md" % (DOCS, m.group(1).rstrip("/")))
    orphans = sorted(o for o in (set(pages) - linked - generated)
                     if o[len(DOCS) + 1:] not in nav and o != "docs/index.md")
    check("no page is unreachable", orphans,
          "not linked from anywhere, not in the sidebar, not in a generated index")

    # --- build -------------------------------------------------------------
    print("\nBUILD")
    check("the site has been built", []
          if os.path.isdir(SITE) else ["site/ is missing - run mkdocs build"])
    # The wiki's icons, on every page. The header and the phone menu's title
    # bar are the same purple as the logo's flames, so the logo there is the
    # one on its white disc; the transparent one would lose its flames.
    brand = os.path.join(DOCS, "assets", "brand")
    bad = ["%s is missing" % n for n in ("logo.png", "favicon.png", "apple-touch-icon.png")
           if not os.path.isfile(os.path.join(brand, n))]
    for f in sorted(glob.glob(os.path.join(SITE, "**", "index.html"), recursive=True)):
        h = io.open(f, encoding="utf-8").read()
        rel = f.replace(chr(92), "/")
        if not re.search(r'<link rel="icon" href="[^"]*assets/brand/favicon\.png"', h):
            bad.append("%s  has no tab icon" % rel)
        if not re.search(r'<link rel="apple-touch-icon" href="[^"]*assets/brand/apple-touch-icon\.png"', h):
            bad.append("%s  has no home-screen icon" % rel)
        logos = re.findall(r'md-logo"[^>]*>\s*<img src="([^"]*)"', h)
        if not logos or any(not l.endswith("assets/brand/logo.png") for l in logos):
            bad.append("%s  header logo is not the disc logo: %s" % (rel, logos))
    check("the wiki's icons and logo are in place", bad)

    # A link preview on every page, and the sidebar's links to other sites
    # opening in a tab of their own.
    bad = [] if os.path.isfile(os.path.join(brand, "social.png")) else ["social.png is missing"]
    for f in sorted(glob.glob(os.path.join(SITE, "**", "index.html"), recursive=True)):
        h = io.open(f, encoding="utf-8").read()
        rel = f.replace(chr(92), "/")
        for tag in ("og:title", "og:url", "og:image", "twitter:card"):
            if h.count('"%s"' % tag) != 1:
                bad.append("%s  has %d %s tags" % (rel, h.count('"%s"' % tag), tag))
        for m in re.finditer(r'<a href="https?://[^"]+" class="md-nav__link"[^>]*>', h):
            if 'target="_blank"' not in m.group(0) or "noopener" not in m.group(0):
                bad.append("%s  %s opens in the same tab" % (rel, m.group(0)[:60]))
    check("every page has a link preview; sidebar links out open a new tab", bad)

    check("every sidebar entry has a page",
          [m.group(1) for m in re.finditer(r"^\s+- .*: (\S+\.md)\s*$", nav, re.M)
           if not os.path.exists(os.path.join(DOCS, m.group(1)))])



# ---------------------------------------------------------------------------
#   The code
# ---------------------------------------------------------------------------

def sweep_code():
    print("\nTHE CODE")
    files = tracked()

    bad = []
    for path in files:
        # The hooks and scripts. _migration/ is the old Wikidot importer, which
        # the wiki no longer uses.
        if path.endswith(".py") and not path.startswith("_migration/"):
            try:
                compile(read(path), path, "exec")
            except SyntaxError as e:
                bad.append("%s:%s  %s" % (path, e.lineno, e.msg))
    check("every Python file compiles", bad)

    bad = []
    try:
        import yaml
    except ImportError:
        bad.append("PyYAML is not installed: pip install -r requirements.txt")
    else:
        for path in files:
            if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")) \
                    or path == ".pages.yml":
                try:
                    yaml.safe_load(read(path))
                except yaml.YAMLError as e:
                    bad.append("%s  %s" % (path, str(e).splitlines()[0]))
    check("every workflow and .pages.yml parses", bad)

    config = read("mkdocs.yml")
    hooks = re.findall(r"^\s*-\s*(hooks/\S+\.py)\s*$", config, re.M)
    check("every hook mkdocs.yml names exists",
          [h for h in hooks if not os.path.isfile(os.path.join(ROOT, h))])
    check("every hook in hooks/ is one mkdocs.yml runs",
          [p for p in files if re.match(r"hooks/[^/]+\.py$", p) and p not in hooks],
          "A hook not in mkdocs.yml never runs: list it there, or take it out.")

    # The announcer is a script of its own and is only run by CI; a mistake in
    # it shows up after a deploy, as a red job. Building one message from the
    # latest page change here finds that first.
    announcer = os.path.join(ROOT, ".github", "scripts", "announce.py")
    run = subprocess.run([sys.executable, announcer, "--test", "--dry-run"], cwd=ROOT,
                         capture_output=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = run.stdout.decode("utf-8", "replace") + run.stderr.decode("utf-8", "replace")
    ok = run.returncode == 0 and "Test message, showing" in out
    check("the Discord announcer builds a message", [] if ok else
          [line for line in out.strip().splitlines()[-4:]] or ["exit %d" % run.returncode])


# ---------------------------------------------------------------------------
#   Safety
# ---------------------------------------------------------------------------

WEBHOOK = re.compile(r"discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]{20,}")
BOT_TOKEN = re.compile(r"\b[MNO][\w-]{23,27}\.[\w-]{6}\.[\w-]{27,}\b")
EMAIL = re.compile(r"[\w.+-]+@(gmail|yahoo|outlook|hotmail|icloud|proton)\.\w+", re.I)
# Addresses meant to be read: the Open Game License's Section 15 carries the
# authors' notices word for word.
PUBLISHED = ("andargor@yahoo.com",)


def sweep_safety():
    print("\nSAFETY")
    hooks, tokens, emails = [], [], []
    for path in tracked():
        if re.search(r"\.(png|jpe?g|gif|webp|ico|woff2?|pdf)$", path, re.I):
            continue
        try:
            text = read(path)
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if WEBHOOK.search(line):
                hooks.append("%s:%d" % (path, i))
            if BOT_TOKEN.search(line):
                tokens.append("%s:%d" % (path, i))
            found = EMAIL.search(line)
            if found and found.group(0).lower() not in PUBLISHED:
                emails.append("%s:%d" % (path, i))
    check("no Discord webhook URL is committed", hooks,
          "Anyone holding one can post to the channel: it belongs in the DISCORD_WEBHOOK_URL secret.")
    check("no Discord bot token is committed", tokens,
          "Reset it in the Developer Portal at once, and keep it in the DISCORD_BOT_TOKEN secret.")
    check("no personal email address is committed", emails)

    bad = []
    for path in tracked():
        if path.startswith(".github/workflows/"):
            for i, line in enumerate(read(path).splitlines(), 1):
                m = re.match(r"\s*(\w*(TOKEN|WEBHOOK|SECRET|KEY)\w*)\s*:\s*(\S.*)$", line)
                if m and "${{" not in m.group(3):
                    bad.append("%s:%d  %s" % (path, i, m.group(1)))
    check("the workflows take their secrets from GitHub", bad,
          "A token or webhook in a workflow must be ${{ secrets.NAME }}, never written in.")


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "site"
    os.chdir(ROOT)
    global SITE
    SITE = site
    print("\nHOUSEKEEPING SWEEP  -  %d files tracked\n" % len(tracked()))
    sweep_pages()
    sweep_code()
    sweep_safety()
    print("\n%d checks, %d failing\n" % (checks, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
