# -*- coding: utf-8 -*-
"""Break the line after a bold label that stands on a line of its own.

A god's page is written in Format A: a section's label in bold on one line and
its prose starting on the very next, with no blank line between -

    **Origins**
    Aezhera was once a mortal disciple of a forgotten sky god...

That is how Wikidot read it, and how the wiki's authors write it: a new line is
a new line. Markdown reads the two lines as one paragraph and runs them
together, "Origins Aezhera was once...". The break is added here, at build
time, so the page source keeps exactly the shape the schema gives it and the
page still reads the way it is meant to.

Only a bold label alone on its line is touched, and only when prose follows
directly. A label followed by a list, a table, a heading, markup or a blank
line is left as it is.
"""
import re

LABEL = re.compile(r"^\*\*[^*\n]+\*\*[ \t]*$")
NOT_PROSE = re.compile(r"^\s*($|[-*+] |\d+\. |\||#|<|!\[|```)")


def on_page_markdown(markdown, page, config, files, **kwargs):
    lines = markdown.split("\n")
    for i in range(len(lines) - 1):
        if LABEL.match(lines[i]) and not NOT_PROSE.match(lines[i + 1]):
            lines[i] = lines[i].rstrip() + "<br>"
    return "\n".join(lines)
