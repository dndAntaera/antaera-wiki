# -*- coding: utf-8 -*-
"""Give the wiki a home-screen icon.

Material sets the browser-tab icon from theme.favicon, but has no setting for
the icon a phone uses when the wiki is saved to its home screen. That is one
<link> in the page head, so it is added here rather than by overriding the
theme's whole base template.

The icon is the logo on its white disc, flattened onto white: iOS fills any
transparency in a home-screen icon with black.
"""
import posixpath

ICON = "assets/brand/apple-touch-icon.png"


def on_post_page(output, page, config):
    here = posixpath.dirname((page.url.rstrip("/") + "/x").lstrip("/")) or "."
    href = posixpath.relpath(ICON, here)
    link = '<link rel="apple-touch-icon" href="%s">' % href
    return output.replace("</head>", link + "</head>", 1)
