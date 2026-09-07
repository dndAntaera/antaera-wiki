# -*- coding: utf-8 -*-
"""Render the page flags set by the importer.

Two flags, both set in front matter so they can be toggled per page:

    wip: true        the page is still being written
    archived: true   the page belongs to a retired section

`wip` puts the wiki's own under-construction sign back on the page. It is a
toggle rather than an image pasted into the body, so finishing a page means
deleting one line of front matter, and the sign can never be left behind on a
page that is done.

`archived` shows a banner saying so. Archived pages are also kept out of the
glossary (see glossary.py) and out of search (Material honours
`search: exclude` in front matter, which the importer sets alongside).
"""

WIP_BANNER = """<div class="wd-flag wd-flag--wip" markdown>

![Under construction](/antaera-wiki/img/shared_under_construction.png)

**This page is still being written.** Some sections may be missing or
incomplete.

</div>

"""

ARCHIVED_BANNER = """<div class="wd-flag wd-flag--archived" markdown>

**Archived.** This page belongs to a retired section of the wiki. It is kept
for reference and is not part of the current setting. It does not appear in
search or in the glossary.

</div>

"""


def on_page_markdown(markdown, page, config, files, **kwargs):
    meta = page.meta or {}
    banners = ""
    if meta.get("archived"):
        banners += ARCHIVED_BANNER
    if meta.get("wip"):
        banners += WIP_BANNER
    return banners + markdown if banners else markdown
