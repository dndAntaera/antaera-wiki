# -*- coding: utf-8 -*-
"""Audit the converted wiki against the Wikidot source.

Every fault found so far produced valid Markdown and passed a strict build
while rendering wrongly, so this checks the things a build cannot: whether
content survived, whether constructs were translated, and whether the
Markdown will actually parse as the structure it looks like.

    .venv/Scripts/python.exe _migration/audit.py <path-to-extracted-backup>
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

sys.path.insert(0, os.path.join(ROOT, "_migration"))
import convert as C  # noqa: E402


def say(s=""):
    sys.stdout.write(str(s).encode("ascii", "replace").decode() + "\n")


def load_docs():
    out = {}
    for root, _, files in os.walk(DOCS):
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, DOCS).replace("\\", "/")
                out[rel] = open(p, encoding="utf-8").read()
    return out


def body_of(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def main(backup):
    src_dir = os.path.join(backup, "source")
    sources = {}
    for f in os.listdir(src_dir):
        slug = f[:-4]
        if C.SKIP.match(slug):
            continue
        sources[slug] = open(os.path.join(src_dir, f), "rb").read().decode("utf-8", "replace")
    docs = load_docs()
    findings = []

    # ---------------------------------------------------------------- content
    say("=" * 74)
    say("1. CONTENT RETENTION  (source words vs converted words)")
    say("=" * 74)
    lost = []
    for slug, raw in sources.items():
        rel = C.target_path(slug)
        if rel not in docs:
            lost.append((slug, "PAGE MISSING", 0, 0))
            continue
        sw = len(re.sub(r"\[\[[^\]]*\]\]", " ", raw).split())
        dw = len(body_of(docs[rel]).split())
        if sw > 30 and dw < sw * 0.75:
            lost.append((slug, rel, sw, dw))
    if lost:
        for slug, rel, sw, dw in sorted(lost, key=lambda x: x[2] - x[3], reverse=True)[:12]:
            say("  %-38s %5d -> %-5d words" % (slug, sw, dw))
        findings.append("%d pages lost >25%% of their words" % len(lost))
    else:
        say("  OK - no page lost more than 25% of its words")

    # ------------------------------------------------------------- constructs
    say()
    say("=" * 74)
    say("2. UNTRANSLATED WIKIDOT CONSTRUCTS still in the output")
    say("=" * 74)
    pat = {
        "[[...]] block": r"\[\[[a-zA-Z/]",
        "[[[link]]]": r"\[\[\[",
        "[/slug text]": r"\[/[a-z]",
        "// italics //": r"(?<!:)//(?=[A-Za-z])",
        "-- strike --": r"(?<![-<:])--(?![a-z-]*:)(?=[A-Za-z])",
        "@@literal@@": r"@@",
        "%%variable%%": r"%%",
        "++ heading": r"^\+{1,6} ",
    }
    hits = 0
    for name, p in pat.items():
        n = sum(len(re.findall(p, t, re.M)) for t in docs.values())
        if n:
            where = [r for r, t in docs.items() if re.search(p, t, re.M)][:3]
            say("  %-16s %4d   e.g. %s" % (name, n, ", ".join(where)))
            hits += n
    if not hits:
        say("  OK - no Wikidot markup remains")
    else:
        findings.append("%d untranslated construct instances" % hits)

    # -------------------------------------------------- markdown that misfires
    say()
    say("=" * 74)
    say("3. MARKDOWN THAT WILL NOT PARSE AS IT LOOKS")
    say("=" * 74)
    problems = {
        "list glued to paragraph": 0,
        "table glued to paragraph": 0,
        "blockquote glued to paragraph": 0,
        "list item indented 1-3 spaces": 0,
    }
    examples = {k: [] for k in problems}
    item = re.compile(r"^(\s*)(?:[-*+]|\d+\.)\s+")
    for rel, text in docs.items():
        lines = body_of(text).split("\n")
        for i, ln in enumerate(lines):
            prev = lines[i - 1] if i else ""
            prev_blank = (not prev.strip())
            m = item.match(ln)
            if m:
                if not prev_blank and not item.match(prev) and not prev.strip().startswith(("<div", "<")):
                    problems["list glued to paragraph"] += 1
                    if len(examples["list glued to paragraph"]) < 3:
                        examples["list glued to paragraph"].append(rel)
                ind = len(m.group(1))
                if ind and ind % 4:
                    problems["list item indented 1-3 spaces"] += 1
                    if len(examples["list item indented 1-3 spaces"]) < 3:
                        examples["list item indented 1-3 spaces"].append(rel)
            if ln.lstrip().startswith("|") and not prev_blank and not prev.lstrip().startswith("|") \
                    and not prev.strip().startswith("<"):
                problems["table glued to paragraph"] += 1
                if len(examples["table glued to paragraph"]) < 3:
                    examples["table glued to paragraph"].append(rel)
            if ln.lstrip().startswith(">") and not prev_blank and not prev.lstrip().startswith(">") \
                    and not prev.strip().startswith("<"):
                problems["blockquote glued to paragraph"] += 1
                if len(examples["blockquote glued to paragraph"]) < 3:
                    examples["blockquote glued to paragraph"].append(rel)
    clean = True
    for k, v in problems.items():
        if v:
            clean = False
            say("  %-34s %4d   e.g. %s" % (k, v, ", ".join(examples[k])))
            findings.append("%d x %s" % (v, k))
    if clean:
        say("  OK - no structural Markdown hazards")

    # ------------------------------------------------------------------ links
    say()
    say("=" * 74)
    say("4. LINKS AND IMAGES")
    say("=" * 74)
    src_links = sum(len(re.findall(r"\[\[\[", t)) for t in sources.values())
    out_links = sum(len(re.findall(r"\]\([^)]*\.md\)", t)) for t in docs.values())
    src_imgs = sum(len(re.findall(r"\[\[f?image\s", t, re.I)) for t in sources.values())
    out_imgs = sum(len(re.findall(r"!\[\]\(", t)) for t in docs.values())
    tables_inlined = sum(1 for t in docs.values() for _ in re.finditer(r"^\|", t, re.M))
    say("  source [[[links]]]      : %d" % src_links)
    say("  output .md links        : %d" % out_links)
    say("  source [[image]]        : %d" % src_imgs)
    say("  output ![](...)         : %d   (+37 became inline tables)" % out_imgs)
    say("  markdown table rows     : %d" % tables_inlined)
    imgdir = {f for f in os.listdir(os.path.join(DOCS, "img")) if not f.startswith(".")}
    refs = set()
    for t in docs.values():
        refs |= set(re.findall(r"!\[\]\(/antaera-wiki/img/([^)]+)\)", t))
    missing = refs - imgdir
    if missing:
        say("  MISSING IMAGE FILES     : %d  %s" % (len(missing), list(missing)[:3]))
        findings.append("%d image references with no file" % len(missing))
    else:
        say("  every image reference resolves to a file")

    # ------------------------------------------------------------ empty pages
    say()
    say("=" * 74)
    say("5. THIN OR EMPTY PAGES")
    say("=" * 74)
    thin = [(r, len(body_of(t).split())) for r, t in docs.items() if len(body_of(t).split()) < 8]
    if thin:
        for r, n in sorted(thin, key=lambda x: x[1])[:10]:
            say("  %-46s %d words" % (r, n))
        findings.append("%d pages under 8 words" % len(thin))
    else:
        say("  OK - no near-empty pages")

    say()
    say("=" * 74)
    if findings:
        say("FINDINGS: " + "; ".join(findings))
    else:
        say("CLEAN - no findings")
    say("=" * 74)


if __name__ == "__main__":
    main(sys.argv[1])
