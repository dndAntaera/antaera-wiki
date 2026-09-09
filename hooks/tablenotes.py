# -*- coding: utf-8 -*-
"""Move a table's note into the table, as a cell across its foot.

The wiki writes a table's notes as a paragraph under it - "* Blunderbuss shot
consists of 1 pound of scrap metal", the numbered footnotes on the material
saving throw table, the captions on the commander rating tables. Rendered as
Markdown those became loose text below a bordered table with nothing tying the
two together, and on this site they then sat on the sky rather than on the
table's own surface.

The converter marks them (`{: .wd-table-note }`, see table_notes in
convert.py). This runs after Markdown has produced the HTML and moves each
marked paragraph into a <tfoot> row of the table above it, spanning every
column - which is what makes it a cell of the table rather than something
placed to look like one.

Markdown has no syntax for a footer row, so this is the point at which it can
be done: the table exists as HTML, and its column count can be counted rather
than guessed.
"""
import re

# The marked paragraphs, immediately after a table's close. A note can run to
# several paragraphs - a caption and then the numbered footnotes - and they all
# belong in the same cell, so the whole run is taken at once.
NOTE = re.compile(
    r"</table>\s*((?:<p class=\"wd-table-note\">.*?</p>\s*)+)",
    re.S,
)
PARA = re.compile(r"<p class=\"wd-table-note\">(.*?)</p>", re.S)


def _columns(table_html):
    """How many columns the table has, from its widest row."""
    widest = 0
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        widest = max(widest, len(re.findall(r"<t[hd][ >]", row)))
    return widest or 1


def on_page_content(html, page, config, files, **kwargs):
    if 'class="wd-table-note"' not in html:
        return html

    out = []
    pos = 0
    for m in NOTE.finditer(html):
        # The table this note belongs to is the one that just closed.
        start = html.rfind("<table", 0, m.start())
        if start == -1:
            continue
        table = html[start:m.start() + len("</table>")]
        cols = _columns(table)
        body = "".join("<p>%s</p>" % p.strip() for p in PARA.findall(m.group(1)))
        out.append(html[pos:m.start()])
        out.append(
            '<tfoot><tr><td class="wd-table-note" colspan="%d">%s</td></tr>'
            "</tfoot></table>" % (cols, body)
        )
        pos = m.end()
    out.append(html[pos:])
    return "".join(out)
