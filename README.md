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
