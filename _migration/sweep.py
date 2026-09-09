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

    check("units are ft and lbs",
          ["%s  %s" % (f, m.group(0))
           for f, t in pages.items()
           for m in re.finditer(r"\d\s*(?:feet|foot|pounds)\b|(?<![A-Za-z])(?:ft|lbs)\.(?!\s+[A-Z])", t)])

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
