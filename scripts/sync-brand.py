"""Bring the wiki's brand images and work-in-progress sign in from the shared folder.

    .venv/Scripts/python.exe scripts/sync-brand.py [path/to/antaera_Shared_Images]

The Antæra projects keep their images in one folder beside the repositories
(default: ../antaera_Shared_Images). The wiki takes from it:

    logo_Antaera.png     the logo on its white disc - the header logo (96),
                         the tab icon (48) and the home-screen icon (172 on
                         a 180 square of white, as iOS rounds the corners and
                         fills any transparency with black)
    banner_Antaera.png   the link-preview image, as it is
    sign_WIP.png         the work-in-progress sign, as it is

Rerun it when an image in the shared folder changes, then commit what it
wrote. The sweep says when the wiki's copies have fallen out of step.
"""

import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT.parent / "antaera_Shared_Images"
BRAND = ROOT / "docs" / "assets" / "brand"
IMG = ROOT / "docs" / "img"

# Copied as they are: the wiki's file, from the shared one.
COPIED = {
    BRAND / "social.png": "banner_Antaera.png",
    IMG / "sign_WIP.png": "sign_WIP.png",
}

# Made from the logo on its white disc: the wiki's file, the logo's size, and
# the white square it is centred on, if any.
SIZED = {
    BRAND / "logo.png": (96, None),
    BRAND / "favicon.png": (48, None),
    BRAND / "apple-touch-icon.png": (172, 180),
}
LOGO = "logo_Antaera.png"


def sized(logo, size, square):
    """The logo at a size, as the wiki shows it."""
    img = logo.resize((size, size), Image.LANCZOS)
    if square:
        white = Image.new("RGB", (square, square), "white")
        at = (square - size) // 2
        white.paste(img, (at, at), img.getchannel("A"))
        img = white
    return img


def stale():
    """The wiki's copies that no longer match the shared folder.

    Empty when the folder isn't there to compare with, as on GitHub's runners.
    """
    if not SOURCE.is_dir():
        return []
    out = [str(dest.relative_to(ROOT)) for dest, name in COPIED.items()
           if not dest.is_file() or dest.read_bytes() != (SOURCE / name).read_bytes()]
    logo = Image.open(SOURCE / LOGO).convert("RGBA")
    for dest, (size, square) in SIZED.items():
        made = sized(logo, size, square).convert("RGBA")
        if not dest.is_file() or Image.open(dest).convert("RGBA").tobytes() != made.tobytes():
            out.append(str(dest.relative_to(ROOT)))
    return out


def main():
    # Read here, not at the top: the sweep loads this file with its own
    # arguments.
    global SOURCE
    if len(sys.argv) > 1:
        SOURCE = Path(sys.argv[1])
    if not SOURCE.is_dir():
        sys.exit("No shared images folder at %s" % SOURCE)
    for dest, name in COPIED.items():
        shutil.copyfile(SOURCE / name, dest)
        print("%s  from %s" % (dest.relative_to(ROOT), name))
    logo = Image.open(SOURCE / LOGO).convert("RGBA")
    for dest, (size, square) in SIZED.items():
        sized(logo, size, square).save(dest, optimize=True)
        print("%s  from %s at %d" % (dest.relative_to(ROOT), LOGO, size))


if __name__ == "__main__":
    main()
