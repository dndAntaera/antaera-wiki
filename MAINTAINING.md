# Maintaining the wiki

Everything about how this repository builds and deploys. For what the wiki is,
see [README.md](README.md).

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
mkdocs serve
```

Then open <http://127.0.0.1:8000/antaera-wiki/> — note the base path, which
matches the live project-site URL. The dev server live-reloads on save.

## Structure

`docs/` is empty apart from the home page. There is no imposed hierarchy -
create whatever folders and pages suit the material.

Navigation is generated from the file tree, so a new page or folder appears in
the sidebar on its own. Nothing in `mkdocs.yml` or `.pages.yml` needs editing
when the wiki grows. Folders are titled from their directory name; add an
`index.md` to a folder to give it a landing page and control its title.

Ordering is alphabetical by default. If a section ever needs a specific order,
add a `nav:` block to `mkdocs.yml` - but note that doing so makes navigation
explicit, and pages created afterwards will not appear until they are listed.

## Writing toolkit

Everything below is enabled and ready to use.

### Page frontmatter

```markdown
---
title: Salt Reach
tags:
  - geography
  - settlement
---

Body starts here. Do not add a `# Heading` - the title above becomes it.
```

Tags are collected into a browsable index automatically.

### Callouts

```markdown
!!! note "Optional title"
    Indented content.

??? tip "Collapsed by default"
    Click to expand.
```

Types include `note`, `tip`, `warning`, `danger`, `example`, `quote`.

### Infobox

A floating summary panel, right-aligned on wide screens and full-width on
mobile:

```markdown
<div class="infobox" markdown>

| | |
|---|---|
| **Type** | City-state |
| **Region** | Salt Reach |

</div>
```

### Images

```markdown
![Map of Antaera](/antaera-wiki/img/antaera-map.png)
```

Files live in `docs/img/`. Pages CMS writes this path form when you insert one.

### Tabs

```markdown
=== "Common"
    Content for the first tab.

=== "Draconic"
    Content for the second.
```

### Also available

Footnotes (`[^1]`), definition lists, abbreviations, `~~strikethrough~~`,
`==highlight==`, tables, and fenced code blocks with syntax highlighting and a
copy button.

### Linking between pages

Use a path relative to the current page, ending in `.md`:

```markdown
[Salt Reach](../geography/salt-reach.md)
```

These are checked at build time - a link to a page that does not exist fails
the build instead of shipping broken. Image paths are *not* checked, because
they are absolute.

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

### Image storage

Images live in `docs/img/` and are committed - the live site has to serve them
on its own. Syntax is in the [Writing toolkit](#images) above.

The absolute `/antaera-wiki/` prefix is the site's base path. `serve-backup.ps1`
mounts the built site under the same prefix so those paths resolve locally too.
If the wiki ever moves to a custom domain at the root, the prefix must be
dropped from `media.output` in `.pages.yml`, from existing Markdown, and from
`serve-backup.ps1` - a find-and-replace, but not an automatic one.

Past roughly 1 GB, GitHub Pages limits start to bite and images should move to
object storage. Well beyond current needs.

## Editing

### In the browser (Pages CMS)

Day-to-day editing happens at [app.pagescms.org](https://app.pagescms.org),
which works on desktop and mobile. Saving commits to `main`; CI rebuilds and
the change is live in roughly 40 seconds.

`.pages.yml` defines what is editable. It is a single collection covering the
whole `docs/` tree, so new pages and folders need no configuration change.

Two things to know:

- Only fields declared in `.pages.yml` survive a save. Frontmatter keys that
  are not declared get dropped when the CMS rewrites a file.
- CMS edits do not run the pre-push hook, since they never touch this machine.
  CI still runs `mkdocs build --strict`, so a broken edit fails the build and
  the previous version stays live - but it fails *after* the commit, not before.

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
