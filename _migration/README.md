# Migration working files

Assets for importing the Wikidot wiki (`antaera.wikidot.com`) into this
repository. Not part of the published site.

## `tables/`

37 Markdown tables transcribed from screenshots. The Wikidot wiki stored its
rules tables as PNG images, which are not searchable, do not reflow on a phone,
and cannot be edited without remaking the picture. Each file here is named for
the image it came from, so `rules_taint_table_5.md` corresponds to
`docs/img/rules_taint_table_5.png`.

These were read visually rather than by OCR software, which handles the coloured
headers and merged cells better but means **the numbers deserve a spot-check**
before anyone relies on them at a table. The source images stay in `docs/img/`
precisely so that check is possible.

309 data rows across 37 tables.

### Known fidelity losses

- **Grouped rows.** Some originals used blank rows to separate blocks - the
  planar crystal skill table divides Knowledge, Craft and Appraise that way.
  Markdown tables cannot express a blank row, so those are flattened. The data
  is complete; the visual grouping is not.
- **Merged header cells.** `spelljamming_helms_hulls_table` had a two-level
  header spanning "Base Saving Throw" and "Bonus" groups. Markdown has no
  colspan, so that is flattened to one header row with a note beneath.
