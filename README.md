# Antaera Wiki

Source for the Antaera Wiki, built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), deployed to
GitHub Pages.

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
mkdocs serve
```

Then open <http://127.0.0.1:8000/antaera-wiki/> — note the base path, which
matches the live project-site URL. The dev server live-reloads on save.

## Adding a page

Normally: create it in Pages CMS (see [Editing](#editing)). New pages appear in
their section automatically.

Directly in the repo, if you prefer:

1. Create a Markdown file under `docs/` (e.g. `docs/characters/veyra.md`) with a
   `title:` in frontmatter.
2. Add it to the `nav:` list in `mkdocs.yml` if it should appear in the sidebar
   in a specific position.
3. Commit and push to `main` — GitHub Actions builds and deploys automatically.

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`, which builds the site
and publishes it to GitHub Pages.

## Hosting architecture

GitHub Pages is the live site. This machine is the disaster-recovery copy.

```
   GitHub Pages  ->  live site, always on, serves every visitor
        ^
        | git push
        |
   F:\! Antaera Wiki  ->  complete standalone copy; can serve the wiki
                          by itself if the live site becomes unreachable
```

Everything the live site needs is committed to this repository, so a working
tree plus `serve-backup.ps1` reconstitutes the whole wiki with no network.

### Restoring service

If the live site is down, deleted, or otherwise unreachable:

```powershell
.\serve-backup.ps1
```

It bootstraps Python if needed, rebuilds from the Markdown here, and serves on
the local network so phones and tablets can reach it too. Add `-LocalOnly` to
keep it on this machine, or `-Port 9000` to change the port.

This depends on nothing external. It is worth running once now, while the live
site is healthy, so the first time you use it is not during an outage.

### Images

Images live in `docs/img/` and **are committed** - the live site has to be able
to serve them on its own.

Reference them with an absolute path that includes the site's base path:

```markdown
![Map of Antaera](/antaera-wiki/img/world/antaera-map.png)
```

Pages CMS writes this form when you insert an image, because it cannot know how
deep the page using it will sit. `serve-backup.ps1` mounts the built site under
the same `/antaera-wiki/` prefix so these paths resolve locally too.

If the wiki ever moves to a custom domain at the root, this prefix has to be
dropped from `media.output` in `.pages.yml`, from existing Markdown, and from
`serve-backup.ps1`. It is a find-and-replace, but it is not automatic.

If the image library grows past roughly 1 GB, GitHub Pages limits start to bite
and images should move to object storage. Well beyond current needs.

## Editing

### In the browser (Pages CMS)

Day-to-day editing happens at [app.pagescms.org](https://app.pagescms.org),
which works on desktop and mobile. Saving commits to `main`; CI rebuilds and
the change is live in roughly 40 seconds.

`.pages.yml` defines what is editable. Adding a new section means adding a
collection there as well as a `nav:` entry in `mkdocs.yml`.

Two things to know:

- Only fields declared in `.pages.yml` survive a save. Frontmatter keys that
  are not declared get dropped when the CMS rewrites a file.
- CMS edits do not run the pre-push hook, since they never touch this machine.
  CI still runs `mkdocs build --strict`, so a broken edit fails the build and
  the previous version stays live - but it fails *after* the commit, not before.

### Page titles

Titles live in frontmatter, not as a body heading:

```markdown
---
title: Geography
---

Body starts here, with no `# Geography` line.
```

MkDocs renders the frontmatter title as the page heading. If a body `# H1` is
also present the two can drift - the body wins the page, the frontmatter wins
the browser tab - so pick one, and it should be frontmatter.

## Safeguards

GitHub Pages publishes whatever reaches `main`, so a bad commit becomes the
live site within about a minute. Three things stand in the way.

### 1. Pre-push guard

`.githooks/pre-push` runs before anything leaves this machine and refuses the
push if either check fails:

- the number of files under `docs/` would drop below 70% of what is currently
  published (catches an accidental mass delete)
- `mkdocs build --strict` does not succeed (catches broken links and bad config
  before they deploy, not after)

Deliberate large changes get through with an explicit override:

```bash
ALLOW_DESTRUCTIVE=1 git push
```

Hooks are not carried by `git clone`, so on a fresh copy enable them once:

```bash
git config --local core.hooksPath .githooks
```

### 2. Branch protection

`main` rejects force-pushes and branch deletion, including from the repository
owner. History cannot be silently rewritten or discarded.

### 3. Rolling back a bad deploy

History is the backstop, so recovery is a revert rather than a repair:

```bash
git revert --no-edit <bad-sha>
git push
```

The deploy workflow republishes within roughly a minute. To find the commit
that introduced the problem, `git log --oneline` and compare against the last
run that was known good.

If the working tree itself is damaged, discard it and take the published
history instead:

```bash
git fetch origin
git reset --hard origin/main
```
