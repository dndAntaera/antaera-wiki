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

1. Create a Markdown file under `docs/` (e.g. `docs/characters/veyra.md`).
2. Add it to the `nav:` list in `mkdocs.yml`.
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

Images live in `docs/img/`, mirroring the `docs/` layout, and **are committed** —
the live site has to be able to serve them on its own.

Reference them with a path relative to the page, never a leading slash and
never a drive letter:

```markdown
![Map of Antaera](../img/world/antaera-map.png)
```

MkDocs rewrites that to account for the `/antaera-wiki/` base path. A
root-relative `/img/...` path skips the base path and 404s on the live site.

If the image library ever grows past roughly 1 GB, GitHub Pages limits start to
bite and images should move to object storage. Well beyond current needs.

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
