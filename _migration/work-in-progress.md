# Pages marked as work in progress

`docs/img/shared_under_construction.png` is the "UNDER CONSTRUCTION" sign from
the Wikidot wiki. It was never decoration: it marked pages that were still
being written, and it appeared on 24 of them.

The sign is **not placed on any page** — it is listed in `DROP_IMAGES` in
`convert.py`. The file stays in `docs/img/`, so putting it back on a page is a
matter of referencing it again:

```markdown
![](/antaera-wiki/img/shared_under_construction.png)
```

This file records which pages carried it, because that information lives
nowhere else once the image is off the pages. These are the pages that were
incomplete at the time of the import.

## The 24 pages

| Page | |
|---|---|
| `anthropology/dragons.md` | `anthropology/warforged.md` |
| `city-shegrove.md` | `cosmology.md` |
| `faction-house-of-fabrication.md` | `item-dreaming-waking.md` |
| `nation/new-haven-imperium.md` | `pantheons.md` |
| `poi-darkastle.md` | `settlement-darkastle.md` |
| `spelljamming/combat-movement.md` | `spelljamming/known-spheres.md` |
| `spelljamming/races.md` | `spelljamming/sphere-custodae.md` |
| `spelljamming/sphere-template.md` | `wm/backgrounds.md` |
| `wm/creation-houserules.md` | `wm/index.md` |
| `wm/items.md` | `wm/lore-main.md` |
| `wm/questing-progression.md` | `wm/races.md` |
| `wm/rules-spelljammer.md` | `wm/taint-exaltation.md` |

The Stellar Marches section (`wm/`) accounts for nine of them, and the
Spelljamming section five.

## A lighter alternative

A Material admonition does the same job as the sign in text rather than a
592 KB image, which means it is searchable, readable on a phone, and does not
have to be hunted for in a folder:

```markdown
!!! warning "Work in progress"
    This page is still being written.
```

## Image placeholders

Separately, 22 pages carried a sourceless `[[image  width="50%"]]` - a slot
held open for art that was never added, usually inside a header table of its
own. Those are dropped on import, and the empty table around them with it.
They are listed here only so the removal is not mistaken for content loss:

`enigma`, `pantheon-mortal-vortressa`, `pantheon-mortal-zarakth`,
`spelljamming-combat-movement`, `spelljamming-known-spheres`,
`spelljamming-races`, and every `spelljamming-sphere-*` page.
