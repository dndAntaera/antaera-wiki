# -*- coding: utf-8 -*-
"""Render the page flags set by the importer.

Two flags, both set in front matter so they can be toggled per page:

    wip: true        the page is still being written
    archived: true   the page belongs to a retired section

`wip` hangs the wiki's own under-construction sign at the foot of the page, on
its own and with no card around it. It is a toggle rather than an image pasted
into the body, so finishing a page means deleting one line of front matter, and
the sign can never be left behind on a page that is done.

`archived` shows a banner saying so, and takes precedence over `wip`: a retired
page is not also under construction, and hanging the sign on one said that
nobody had finished it rather than that it had been set aside. Archived pages
are kept out of search as well (Material honours `search: exclude` in front
matter, which the importer sets alongside) and gathered on the Archived Pages
index, which is the only place on the site that links to them.
"""

WIP_SIGN = """

<div class="wd-wip" markdown>

![Under construction](/antaera-wiki/img/shared_under_construction.png)

</div>
"""

ARCHIVED_BANNER = """<div class="wd-flag wd-flag--archived" markdown>

**Archived.** This page belongs to a retired section of the wiki. It is kept
for reference and is not part of the current setting. It does not appear in
search, and it is reached from the [Archived Pages](/antaera-wiki/archived/)
index rather than from the menu.

</div>

"""


def on_page_markdown(markdown, page, config, files, **kwargs):
    meta = page.meta or {}
    if meta.get("archived"):
        markdown = ARCHIVED_BANNER + markdown
    # The sign goes at the foot of the page, on its own, with no card around
    # it. It is a note left by the author about the state of the page, not part
    # of the article, and it should not be the first thing a reader meets.
    #
    # Not on an archived page. All three West Marches pages carry both flags,
    # and the sign there claimed the page was still being worked on when the
    # banner above it had just said the section was retired.
    if meta.get("wip") and not meta.get("archived"):
        markdown = markdown + WIP_SIGN
    return markdown
