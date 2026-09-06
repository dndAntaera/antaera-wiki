# Image originals

This directory is the **source of truth** for every image on the wiki. It is
deliberately **not committed to git** — binaries bloat the repo and GitHub Pages
caps repo size.

## How images are referenced

In Markdown, always use a root-relative `/img/` path:

```markdown
![Map of Antaera](/img/world/antaera-map.jpg)
```

That path resolves differently depending on who is answering the request:

| Serving layer | `/img/world/antaera-map.jpg` resolves to |
|---|---|
| Local PC (awake) | `F:\! Antaera Wiki\images\world\antaera-map.jpg` |
| Cloudflare (PC asleep) | the same object synced into the R2 bucket |

Because the Markdown never names a machine or a bucket, nothing has to be
rewritten when the serving layer changes.

## Rules

- Put originals here, in subfolders mirroring `docs/` (`world/`, `characters/`).
- Never reference an image by a `F:\` path or a full URL.
- Run the sync after adding images, or they will be missing when the PC sleeps.
