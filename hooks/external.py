# -*- coding: utf-8 -*-
"""Open the sidebar's links to other sites in a new tab.

The sidebar is the wiki's own contents, so a link in it that leaves the wiki -
the Sheet Tracker 3.5e - opens beside it rather than in its place, and the page
the reader was on is still there when they come back.
"""
import re

EXTERNAL = re.compile(r'<a href="(https?://[^"]+)" class="md-nav__link">')


def on_post_page(output, page, config):
    return EXTERNAL.sub(
        r'<a href="\1" class="md-nav__link" target="_blank" rel="noopener">', output)
