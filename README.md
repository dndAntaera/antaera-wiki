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

`F:\! Antaera Wiki` is the source of truth. Nothing else holds anything this
directory does not.

```
   F:\! Antaera Wiki
          |
          +-- git push -------> GitHub Pages    (always-on HTML fallback)
          +-- sync -----------> Cloudflare R2   (always-on image delivery)
          +-- cloudflared ----> Tunnel          (live while this PC is awake)
```

Traffic reaches Cloudflare first. While the PC is awake the tunnel serves the
site; when the PC sleeps Cloudflare falls back to GitHub Pages. Because images
are served from R2 in both states, sleeping the PC does not break them.

### Images

Originals live in `images/` (git-ignored) and are referenced from Markdown as
`/img/<path>`. See [images/README.md](images/README.md) for the full rule — the
short version is that no Markdown file may ever name a drive letter or a bucket
URL.
