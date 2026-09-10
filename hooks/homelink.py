# -*- coding: utf-8 -*-
"""Make the wiki's name in the header a link to the main page.

Material links the little book icon home and leaves the name beside it as plain
text. On a phone that name is most of what the header shows, and on any screen
it is the most obvious thing on the page to click - so it goes home too, which
is what a reader expects of the title of a wiki.

The address is not worked out again here. It is read off the icon's own link on
the same page, so however deep the page sits the two always agree, and if
Material ever changes how it builds that address this follows it.

There is no template override for this because it is one element. Overriding
the header would mean copying Material's whole header partial into the
repository and keeping it in step with the theme; this depends only on the two
class names below, and says so loudly if either of them changes.
"""
import logging
import re

log = logging.getLogger("mkdocs.hooks.homelink")

# The site name is the first of the two topics in the header title: the second
# is the current page's own name, which scrolls up into view on a phone and
# should not be a link to somewhere else.
TITLE = re.compile(
    r'(<div class="md-header__title"[^>]*>\s*'
    r'<div class="md-header__ellipsis">\s*'
    r'<div class="md-header__topic">\s*)'
    r'(<span class="md-ellipsis">.*?</span>)',
    re.S,
)

LOGO = re.compile(r'<a\s+href="([^"]*)"[^>]*class="[^"]*\bmd-logo\b')


def on_post_page(output, page, config):
    logo = LOGO.search(output)
    if not logo:
        log.warning("homelink: no logo link on %s, header title left as text",
                    page.file.src_uri)
        return output

    href = logo.group(1)
    name = config["site_name"]

    def link(m):
        return '%s<a class="wd-home" href="%s" title="%s">%s</a>' % (
            m.group(1), href, name, m.group(2))

    output, n = TITLE.subn(link, output, count=1)
    if n != 1:
        log.warning("homelink: header title not found on %s", page.file.src_uri)
    return output
