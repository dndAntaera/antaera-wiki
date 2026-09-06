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

---

# Walkthrough: Wiki.js with Google sign-in

Written 2026-09-06 in response to "add Google auth so I can add users".

## Why this is not a change to the current site

GitHub Pages serves static files. There is no server, no session, and no user
database, so there is nothing for a Google login to authenticate *against*.
Editing means writing to the Git repository, and repository write access is a
GitHub permission - a Google identity has no relationship to it.

So Google sign-in is not a feature that can be added to the wiki as it stands.
It is a property of running a wiki application, which is what follows.

## The cheaper alternative, first

If the goal is only to let a few people edit, add them as **collaborators** on
`dndAntaera/antaera-wiki`. They sign in to Pages CMS with GitHub and can edit
immediately. No server, no cost, no maintenance.

The trade-offs:

- Everyone needs a GitHub account. Free and quick, but a real barrier for
  people who have no other reason to have one.
- Collaborators get write access to the whole repository. There is no
  read-only role and no per-page permission.

For a handful of trusted co-authors this is enough. For players who should read
but not edit, or edit only their own character pages, it is not.

## What Wiki.js adds

- Google (and Discord, Microsoft, or plain email) sign-in
- Groups with per-path permissions - e.g. Players read everything but write
  only under `/characters/`
- Instant saves, page history, comments
- Git sync, so this repository stays the source of truth

## Steps

### 1. A server

Any always-on Linux host. Hetzner CX22 is about EUR 4/month; Oracle Cloud's
always-free ARM tier is genuinely free but slower to provision. Ubuntu 24.04.

### 2. Wiki.js and a database

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: wiki
      POSTGRES_USER: wiki
      POSTGRES_PASSWORD: CHANGE_ME
    volumes:
      - db:/var/lib/postgresql/data
    restart: unless-stopped

  wiki:
    image: requarks/wiki:2
    depends_on:
      - db
    environment:
      DB_TYPE: postgres
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: wiki
      DB_USER: wiki
      DB_PASS: CHANGE_ME
    ports:
      - "3000:3000"
    restart: unless-stopped

volumes:
  db:
```

`docker compose up -d`, then open port 3000 and complete the setup wizard.

### 3. A domain and HTTPS

Google will not accept a bare IP as an OAuth redirect target, so a hostname is
required before auth can be configured. Point a subdomain at the server and put
Caddy in front - it obtains a certificate automatically:

```
wiki.yourdomain.com {
    reverse_proxy localhost:3000
}
```

### 4. Google OAuth credentials

1. [console.cloud.google.com](https://console.cloud.google.com) - create a project.
2. **APIs & Services -> OAuth consent screen**. Choose **External**. Fill in the
   app name and support email. While the app is in *Testing* only accounts you
   list as test users can sign in, which is a reasonable way to start; publish
   it when you want to stop maintaining that list.
3. **Credentials -> Create credentials -> OAuth client ID -> Web application**.
4. Leave the redirect URI blank for now - Wiki.js generates the exact value in
   the next step. Guessing it is the usual cause of `redirect_uri_mismatch`.
5. Copy the **Client ID** and **Client secret**.

### 5. Wire it into Wiki.js

1. **Administration -> Auth -> Add strategy -> Google**.
2. Paste the client ID and secret.
3. Copy the **Callback URL / Redirect URI** that Wiki.js displays, and paste it
   back into the Google credential from step 4. This is the step people get
   wrong.
4. Set **Assign to group** so new sign-ins land somewhere sensible.
5. Decide on **Allow self-registration**:
   - Off: you invite each person. Best for a private campaign.
   - On, with a domain limit: anyone on a given email domain can join.
   - On, unrestricted: anyone with a Google account. Rarely what you want.
6. Save, sign out, and confirm the Google button appears on the login page.

### 6. Groups and permissions

**Administration -> Groups**. A workable starting split:

| Group | Permissions | Page rules |
|---|---|---|
| Players | `read:pages`, `read:comments`, `write:comments` | Allow read on `/` |
| Editors | adds `write:pages`, `manage:pages` | Allow write on `/` |
| Admins | full | - |

Page rules match by path prefix, so scoping a group to `/characters/` is a rule
rather than a structural change.

### 7. Point Git storage at this repository

**Administration -> Storage -> Git**. Repository URL, branch `main`, a deploy
key with write access, local path `docs`. Set the mode to bidirectional.

This is the step that keeps the arrangement reversible: pages stay Markdown in
this repository, GitHub Pages keeps building from them, and
`serve-backup.ps1` keeps working. If Wiki.js is a mistake, the content is not
trapped in its database.

### 8. Cut over only when it is proven

Run both for a while. Pages keeps serving the static copy from the same
Markdown Wiki.js is writing, so it doubles as a read-only fallback while
Wiki.js earns trust. Move the domain last.

## Cost summary

| | |
|---|---|
| Server | ~EUR 4/month, or free on Oracle's always-free tier |
| Domain | ~USD 10/year, if you do not already have one |
| Google OAuth | Free |
| Wiki.js | Free, open source |
