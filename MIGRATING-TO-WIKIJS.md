# If this wiki outgrows Pages CMS

Written 2026-09-06, when Pages CMS was chosen over Wiki.js. Kept so the reasoning
is available later rather than reconstructed.

## Why we did not start here

Wiki.js is a real wiki: edits save instantly, pages have history, and it does not
need a build step. It also needs a server that is always on, which this project
does not have - the PC that holds the files sleeps, and that was the constraint
that ruled out self-hosting from the start.

Pages CMS gave browser editing without a server, at the cost of a ~40 second
delay between save and publish.

## Signals it is time to move

Any one of these is a reasonable trigger:

- The 40-second publish delay stops being acceptable, e.g. editing live at the
  table during a session.
- More than one person is writing, and commits to `main` start colliding.
- You want talk pages, page-level permissions, or per-page comments.
- You want templates and transclusion - reusable statblocks or infoboxes that
  update everywhere at once. This is the strongest reason; MkDocs has no real
  equivalent.
- Search across a few hundred pages starts feeling slow client-side. MkDocs
  ships the whole index to the browser; at 500 pages it was already 816 KB.

## What carries over cleanly

- **The Markdown itself.** Wiki.js stores Markdown and can sync a Git repo
  bidirectionally, so `docs/` can remain the source of truth and this repository
  can stay exactly as it is.
- **Images**, though paths need rewriting - see below.
- **Git history.** Nothing is thrown away; Wiki.js commits alongside it.

## What does not

- **`mkdocs.yml`** - theme, nav, and plugin config have no Wiki.js equivalent.
  Navigation is rebuilt in its UI.
- **Material-specific Markdown** - admonitions (`!!! note`), content tabs, and
  the `.infobox` CSS pattern. Wiki.js has its own syntax for the first two;
  the third becomes a template.
- **`.pages.yml`**, which is Pages CMS only.
- **The pre-push hook and `mkdocs build --strict`.** Wiki.js has no build to
  fail, so broken links stop being caught automatically. Worth replacing with a
  link checker.

## Rough shape of the move

1. Stand up Wiki.js somewhere always-on. Hetzner CX22 is about EUR 4/month;
   Oracle Cloud's always-free ARM tier costs nothing but takes longer to set up.
2. Point its Git storage module at this repository, `docs/` as the content path,
   with a deploy key. Let it do the initial import.
3. Rewrite image paths from `/antaera-wiki/img/...` to whatever Wiki.js serves
   assets at. A find-and-replace, but do it in a branch.
4. Convert Material-specific syntax. Admonitions are the bulk of it.
5. Keep GitHub Pages running until Wiki.js is proven. They can coexist - Pages
   builds from the same Markdown Wiki.js is writing, so the static copy keeps
   working as a read-only mirror and, usefully, as a fallback if Wiki.js is down.
6. Only then point the domain at Wiki.js.

Step 5 is the point of this whole arrangement: because the content stays as
Markdown in Git, the migration is reversible and can be abandoned partway
without losing anything.

## What to preserve regardless

`serve-backup.ps1` and the local clone. Wiki.js puts a database in the path
between you and your words; the Git mirror is what keeps that from mattering.
