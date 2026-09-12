# -*- coding: utf-8 -*-
"""Put the page's footnote at the foot of every page.

The footnote is what the page is, rather than what it says: when it was last
touched, when it was made, and the notice that this is fan content. Material
already prints the two dates in an <aside> at the end of the article; this
gathers that aside and the notice into one block so they read as one line of
small print, the dates above the notice.

The legal page does not get it. The same notice is a card of its own there, and
printing it twice on one page says nothing the once did not.
"""
import re

POLICY = (
    "Antæra is unofficial Fan Content permitted under the Fan Content Policy. "
    "Not approved/endorsed by Wizards. Portions of the materials used are "
    "property of Wizards of the Coast. ©Wizards of the Coast LLC. "
    '<a href="https://company.wizards.com/en/legal/fancontentpolicy">'
    "For more information</a>"
)

LEGAL_PAGE = "disclaimer-legal.md"

DATES = re.compile(r'<aside class="md-source-file">.*?</aside>', re.S)


def on_post_page(output, page, config):
    if page.file.src_uri == LEGAL_PAGE:
        return output

    notice = '<p class="wd-footnote__policy">%s</p>' % POLICY

    m = DATES.search(output)
    if m:
        block = '<div class="wd-footnote">%s%s</div>' % (m.group(0), notice)
        return output[:m.start()] + block + output[m.end():]

    # A page with no dates - one git has never seen - still gets the notice, at
    # the foot of the article where the dates would have been.
    block = '<div class="wd-footnote">%s</div>' % notice
    return output.replace("</article>", block + "</article>", 1)
