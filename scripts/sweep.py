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
               images, cards, house style, the build itself. These are the
               checks in _migration/sweep.py, which reads the pages the way
               the importer built them.
  THE CODE     the hooks, the announcer and the workflows: they compile, they
               parse, and what mkdocs.yml names exists.
  SAFETY       nothing that should be a secret is committed: no Discord
               webhook or bot token, no personal email address, and the
               workflows take their secrets from GitHub, never from a file.
"""
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

def sweep_pages(site):
    """The page checks, from _migration/sweep.py, against the built site given."""
    sys.path.insert(0, os.path.join(ROOT, "_migration"))
    import sweep as pages
    pages.SITE = site
    code = pages.main()
    return pages.checks, pages.failures if code else 0


# ---------------------------------------------------------------------------
#   The code
# ---------------------------------------------------------------------------

def sweep_code():
    print("\nTHE CODE")
    files = tracked()

    bad = []
    for path in files:
        if path.endswith(".py"):
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
    page_checks, page_failures = sweep_pages(site)
    sweep_code()
    sweep_safety()
    total, failing = page_checks + checks, page_failures + failures
    print("\n%s\nHOUSEKEEPING: %d checks, %d failing\n" % ("=" * 58, total, failing))
    return 1 if failing else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
