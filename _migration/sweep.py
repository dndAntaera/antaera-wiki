# -*- coding: utf-8 -*-
"""Housekeeping sweep: is anything on the wiki broken?

Run from the repository root, after a build:

    .venv/Scripts/python.exe _migration/sweep.py

Every check either prints "OK" or lists what is wrong. A clean run is silent
apart from the OK lines and the summary; anything printed under a check is
something to look at.

This exists because a green `mkdocs build --strict` proves almost nothing about
the pages. Broken lists, headings that should have been lists, sidebars that
stacked, table separators eaten by a strikethrough rule and stat blocks
rendering as run-on prose were all, at various points, perfectly valid Markdown
that built without a warning. The checks here look at what the pages actually
say and how they are actually put together.
"""
import collections
import glob
import io
import os
import re
import sys

DOCS = "docs"
SITE = "site"

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


def md_pages():
    for f in sorted(glob.glob(os.path.join(DOCS, "**", "*.md"), recursive=True)):
        yield f.replace("\\", "/"), io.open(f, encoding="utf-8").read()


def body_of(text):
    return text[text.find("\n---", 3) + 4:] if text.startswith("---") else text


def main():
    pages = dict(md_pages())
    print("\nHOUSEKEEPING SWEEP  -  %d pages\n" % len(pages))

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

    check("units are ft and lbs",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r"\d\s*(?:feet|foot|pounds)\b|(?<![A-Za-z])(?:ft|lbs)\.(?!\s+[A-Z])", t)])

    # Every god's page follows Format A (see deity_format in convert.py): all
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
        if re.search(r"^- \*\*Rank\*\*: (?!(Greater|Intermediate|Lesser) God$)", b, re.M):
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
    check("every sidebar entry has a page",
          [m.group(1) for m in re.finditer(r"^\s+- .*: (\S+\.md)\s*$", nav, re.M)
           if not os.path.exists(os.path.join(DOCS, m.group(1)))])

    print("\n%s\n%d checks, %d need attention\n" % ("-" * 58, checks, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
