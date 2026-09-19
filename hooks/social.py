# -*- coding: utf-8 -*-
"""Give every page a link preview.

When a wiki link is pasted into Discord or anywhere else that unfurls links,
the preview is built from Open Graph tags in the page head. Material only sets
those through its social plugin, which draws a card for every page and needs
Cairo installed; this wiki wants one image, the same on every page, so the tags
are written here instead.

The image is the transparent logo on the page's own night sky. The theme colour
is the header's purple, which Discord uses for the stripe down the side of the
preview.
"""
import html

IMAGE = "assets/brand/social.png"
THEME = "#bf00ff"


def on_post_page(output, page, config):
    site = config["site_name"]
    base = config["site_url"].rstrip("/") + "/"
    title = site if page.is_homepage else "%s - %s" % (page.title, site)
    desc = page.meta.get("description") or config["site_description"]
    url = page.canonical_url or base
    tags = [
        ('property', 'og:type', "website"),
        ('property', 'og:site_name', site),
        ('property', 'og:title', title),
        ('property', 'og:description', desc),
        ('property', 'og:url', url),
        ('property', 'og:image', base + IMAGE),
        ('property', 'og:image:width', "1200"),
        ('property', 'og:image:height', "630"),
        ('property', 'og:image:alt', "The Antæra logo: a d20 marked Æ in a ring of purple flame"),
        ('name', 'twitter:card', "summary_large_image"),
        ('name', 'theme-color', THEME),
    ]
    head = "".join('<meta %s="%s" content="%s">' % (k, n, html.escape(v, quote=True))
                   for k, n, v in tags)
    return output.replace("</head>", head + "</head>", 1)
