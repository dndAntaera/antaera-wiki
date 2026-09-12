# -*- coding: utf-8 -*-
"""Put the page's footnote at the foot of every page.

The footnote is what the page is, rather than what it says: when it was last
touched and when it was made, the author's note on the state of the setting,
and the notice that this is fan content. Material already prints the two dates
in an <aside> at the end of the article; this gathers that aside and the notes
into one block, in that order, so they read as one run of small print.

The legal page gets the footnote without the fan content notice. That notice
is a card of its own there, and printing it twice on one page says nothing the
once did not.
"""
import re

AUTHOR_NOTE = (
    "As a note from the author, the setting is currently under revision to "
    "accommodate the inclusion of the Spelljammer setting."
)

POLICY = (
    "Antæra is unofficial Fan Content permitted under the Fan Content Policy. "
    "Not approved/endorsed by Wizards. Portions of the materials used are "
    "property of Wizards of the Coast. ©Wizards of the Coast LLC. "
    "For more information on the Fan Content Policy, visit the link "
    '<a href="https://company.wizards.com/en/legal/fancontentpolicy">here</a>.'
)

LEGAL_PAGE = "disclaimer-legal.md"

DATES = re.compile(r'<aside class="md-source-file">.*?</aside>', re.S)


def on_post_page(output, page, config):
    notes = '<p class="wd-footnote__note">%s</p>' % AUTHOR_NOTE
    if page.file.src_uri != LEGAL_PAGE:
        notes += '<p class="wd-footnote__policy">%s</p>' % POLICY

    m = DATES.search(output)
    if m:
        block = '<div class="wd-footnote">%s%s</div>' % (m.group(0), notes)
        return output[:m.start()] + block + output[m.end():]

    # A page with no dates - one git has never seen - still gets the notes, at
    # the foot of the article where the dates would have been.
    block = '<div class="wd-footnote">%s</div>' % notes
    return output.replace("</article>", block + "</article>", 1)
