# -*- coding: utf-8 -*-
"""Version custom CSS and JS URLs so browsers pick up changes.

Material's own stylesheet is content-hashed (main.<hash>.min.css), but files
listed in extra_css and extra_javascript keep a stable URL. A browser that has
cached stylesheets/extra.css will keep using it after a deploy, so a change to
the site's typography or layout appears to do nothing - which is exactly what
happened when the type scale was reduced twice with no visible effect.

Appending a hash of the file contents makes the URL change whenever the file
does, and stay identical when it does not.
"""
import hashlib
import os


def _versioned(entries, docs_dir):
    out = []
    for href in entries:
        if not isinstance(href, str) or href.startswith(("http://", "https://", "//")):
            out.append(href)
            continue
        bare = href.split("?")[0]
        path = os.path.join(docs_dir, bare.replace("/", os.sep))
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()[:10]
            out.append(bare + "?v=" + digest)
        else:
            out.append(href)
    return out


def on_config(config, **kwargs):
    docs_dir = config["docs_dir"]
    if config.get("extra_css"):
        config["extra_css"] = _versioned(config["extra_css"], docs_dir)
    if config.get("extra_javascript"):
        config["extra_javascript"] = _versioned(config["extra_javascript"], docs_dir)
    return config
