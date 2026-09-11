# -*- coding: utf-8 -*-
"""Convert the Wikidot backup into the MkDocs site.

Run from the repository root:
    .venv/Scripts/python.exe _migration/convert.py <path-to-extracted-backup>

Rerunnable: it rewrites docs/ from the backup each time, so fixing a rule here
and re-running is the way to iterate rather than hand-editing the output.
"""
import json
import os
import re
import sys
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
TABLES = os.path.join(ROOT, "_migration", "tables")
BASE = "/antaera-wiki"

# Wikidot furniture, not this wiki's content.
#
# Wikidot category slugs use a colon ("system:members") but the backup writes
# them with an underscore ("system_members.txt"), so both forms are matched -
# the colon form alone silently let 26 system pages through.
SKIP = re.compile(
    r"^(admin_|chatter|nav[:_]|forum_|featured|talk_|inc_|template|glossary_|_"
    r"|wiki[:_]|snippet[:_]|system[:_]|legal[:_]|theme[:_]|search[:_])"
    r"|^(1234|amadeus-mozart|help|new-wiki-help|main_about|random|wiki|contact"
    r"|about|donate|spelljamming-sphere-template|glossary)$"
)

# Pages that are the site's page template and nothing else. Six of the eight
# chapters the West Marches index lists were made from the template and never
# written: the whole of each one is "Title / Body / Sidebar Body", the words the
# template ships with, twice over. They are not stubs of an article; they are
# the template wearing a name, and they are the only pages on the wiki whose
# heading says "Title". The index still lists them, as plain text rather than
# as links, so the outline of what the campaign meant to cover survives.
#
# Take a line out of here to publish one the moment it has something in it.
TEMPLATE_ONLY = {
    "wm-items",
    "wm-lore-main",
    "wm-questing-progression",
    "wm-races",
    "wm-rules-spelljammer",
    "wm-taint-exaltation",
}

# Corrections to a page made since the import, as exact replacements applied to
# the finished page. A rewrite replaces a section and a recard rebuilds a card;
# this is for the smaller thing, a line or a word, where naming the surrounding
# section would say far more than the change does.
#
# Each one must match exactly once. A replacement that stops matching is a sign
# the page it edits has changed underneath it, and it says so rather than
# quietly doing nothing.
EDITS = {
    "the-index": [
        # The index lists the variant rules in effect from A to Z, and Gestalt,
        # which the houserules above it lean on twice, was not among them. The
        # section has to be named: The Index runs the alphabet four times over,
        # once for the rules and again for the homebrew items, feats and
        # spells, so "## G" on its own names four places on the page.
        ("# Variant Rules In Effect", "## G\n## H",
         "## G\n\n- [Gestalt](rules/gestalt.md)\n\n## H"),
        # And the houserule that leans on it now points at it.
        (None, "- Gestalt Only",
         "- [Gestalt Only](rules/gestalt.md)"),
    ],
}
# Pages taken off the wiki since the import. Frymrit's was a disambiguation
# stub - "This page is currently used for disambiguation" and nothing else -
# with nothing to disambiguate: no other page carries the name, and nothing in
# the whole Wikidot backup mentions it outside that stub.
REMOVED = {
    "frymrit",
}

# Slug prefixes with enough pages to be worth a folder.
FOLDERS = {
    "pantheon": "pantheon",
    "spelljamming": "spelljamming",
    "deity": "deity",
    "wm": "wm",
    "anthropology": "anthropology",
    "rules": "rules",
    "nation": "nation",
    "race": "race",
    "item": "item",
    "faction": "faction",
    # Wikidot had three prefixes for one idea - a city, a settlement and a
    # point of interest are all places people live. They share a folder.
    "city": "settlement",
    "settlement": "settlement",
}

# Prefixes that classify a page but are not worth a folder of their own. They
# are stripped from the title, so "events-crucible-of-valor" is "Crucible of
# Valor" rather than "Events Crucible Of Valor" - the slug says what kind of
# thing it is, the title should say which thing.
TITLE_PREFIXES = {
    "poi", "events", "taxonomy",
}

# Pages that are two halves of one thing. Wikidot filed the arcane and the
# psionic version of a spell as separate pages, which split one rules entry
# across two URLs and gave both the same name. The wiki's own spelljamming
# magic page already keeps such pairs together - "Create Major Helm" and
# "Create Major Helm, psionic" sit side by side there - so this follows the
# convention the wiki set for itself.
#
# Each part keeps its own section and its own anchor, so a link that meant the
# psionic version still lands on the psionic version.
MERGES = {
    "stabilize-crystal": {
        "title": "Stabilize Crystal",
        "lead": "Stabilizing a [[[planar-crystal|Planar Crystal]]] can be done "
                "with magic or with psionics. Both forms are below.",
        "parts": [
            ("Spell", "spell-stabilize-crystal"),
            ("Psionic Power", "power-stabilize-crystal"),
        ],
    },
}

# Pages whose content belongs at the foot of another page rather than on one
# of its own. The source page is not written; links to it follow the content.
APPEND_TO = {
    "map-antaera": "spelljamming-sphere-antaera",
}

# Sections rewritten since the import, keyed by slug and by the heading the
# section sits under. The converter rebuilds docs/ from the backup on every
# run, so a section edited in docs/ is overwritten the next time it runs; a
# rewrite has to live here to survive one.
REWRITES = {
    "anthropology-warforged": {
        "Origin Story": """\
When the [House of Fabrication](../faction/house-of-fabrication.md) first began to develop the world of [Crucibulum](../spelljamming/sphere-forgehome.md), they found that the conditions there were too inhospitable to living workers. None of their existing constructs could survive the heat, and their joints were continuously clogged by the volcanic ash ever-present in the atmosphere. Their only solution was to turn to the Ancient Antaeran relic discovered nested within [Probatio](../spelljamming/sphere-forgehome.md), which House Scholars could only determine was an ancient construct forge of some kind.

Out of necessity, the House redoubled their efforts into discovering the purpose behind this strange artifact. After several years of dedicated research and experimentation, it was discovered that it was in fact a Forge of War, a thing of legend that no mortal has been able to find previously. They discovered the means to begin its operation: by binding elemental spirits to frames of metal and wood, they brought forth the living constructs known as Warforged.

They did not discover this alone, however. There was a guardian of the forge that guided their hand as they woke the forge again after an untold amount of time. Why it helped them, no one knows, however they named this creature Alpha and designed the future models of Warforged after it. It stayed and guided the newly created Warforged and eventually gained both their admiration and worship. The strength of the Warforged souls, however, was not anticipated by the house and Alpha ascended to divinity. It is said that the creation of Warforged is still guided by their hand to this day.

These new souls proved themselves to be useful on the new world of Crucibulum, though this newfound sentient would prove to be a thorn in the House's side. This eventually created a deep philosophical debate between the House and the rest of the [Known Spheres](../spelljamming/known-spheres.md): the House believed Warforged to be mindless automatons that simply had the capability of understanding and performing complex tasks, while the rest of the Known Spheres believed the Warforged to exhibit signs of sentience. This debate would eventually lead to the event known as the [Warforged Civil War](../faction/house-of-fabrication.md#warforged-civil-war).""",
    },
}

# Cards rewritten since the import, keyed by slug and by the heading the card
# opens with. A rewrite that changes the shape of a section rather than its
# wording - one card of running prose becoming five, one to a subject - cannot
# be done by swapping the text under a heading. The card is matched whole and
# rebuilt as the sections listed here, one card each.
RECARDS = {
    "anthropology-warforged": {
        "General Culture": [
            ("General Culture", """\
Warforged are living constructs, each one an elemental spirit bound into a frame of metal and wood. The element bound into a given frame is not chosen and cannot be predicted before waking, which produces a people with a common origin and almost nothing in common temperamentally. A Warforged is not shaped by upbringing or region the way most peoples are. It is shaped by which plane its spirit was drawn from.

Whatever their element, all Warforged express what they feel the same way, and to living observers that way looks like nothing at all. A Warforged registers its state as a fact rather than a pressure: it knows that a situation is dangerous, that a decision was poor, that an absence is regrettable, and it reports each of these in the same even register it would use for a tonnage figure. Grief does not fade because nothing in a Warforged wears the memory down, and anger does not cool on its own, but neither shows on the outside. The living read this as cold and calculating, and the reputation follows the race everywhere it goes. Two Warforged of opposite elements, one furious and one indifferent, are difficult to tell apart by anyone who is not Warforged themselves.

Communities are organized around work rather than element, and around the common problem of what to do with the temperament you were issued. A Warforged does not eat or sleep, and its day is bounded by the shift rather than by the sun. They age as anything does, though the years show in scoring and repair rather than in the body slowing: mismatched plate, runework redrawn by a hand that was not the original, joints replaced with whatever was available at the time. Among Warforged this is read the way other peoples read a face, and a frame kept running a long while carries more standing than one still in factory condition."""),
            ("Names", """\
Warforged names are short and descriptive, taken from a function, a trait, or an incident. Most are given rather than chosen, conferred by whoever a Warforged worked alongside first, and most are kept for life. A Warforged who changes its name is announcing something, and everyone present will understand that.

**Sample names**: Anvil, Ballast, Cinder, Draft, Fathom, Kiln, Lintel, Reed, Sill, Slag, Squall, Tallow, Keel, Ash."""),
            ("Elemental Personalities", """\
A fire-souled Warforged runs hot and fast. Quick to commit, quick to act, comfortable with risk, and poor at waiting. An earth-souled Warforged is stubborn and patient in equal measure: slow to be moved to a position and slower to be moved off one, willing to wait out a problem or an opponent for as long as it takes. Air-souled Warforged are restless, curious, and aloof, drawn to whatever they have not yet examined and rarely attached to any of it. Water-souled Warforged are mercurial and adaptive, changing approach without warning and fitting themselves to whatever shape a situation demands.

The correspondence is neat, and its neatness is the standing objection to it. Every Warforged learns these four categories from the moment it wakes and hears them applied to itself constantly. Whether the element produces the temperament or merely names it is not a settled question. It is also invisible from outside, since all four express themselves in the same flat manner, and outsiders who have dealt with Warforged for years often cannot say which element they are dealing with."""),
            ("Spiritual Beliefs and Practices", """\
Warforged faith centers on Alpha, the guardian of the Forge who guided the House to its operation and stayed to guide the Warforged it made. Alpha ascended on the strength of Warforged worship, and it is said that every Warforged made since has been shaped by their hand. A clergy has grown around this, holding that the [House of Fabrication](../faction/house-of-fabrication.md) was the tool Alpha used to bring them into being, chosen for its skill and its reach, and that a tool has no claim on what it makes. The House lost its way when it turned from making to abusing what it had made. The distinction matters to the faithful, as it allows a Warforged to hold the House in contempt without holding its own existence in contempt.

The clergy is almost entirely contained to [Forgehome](../spelljamming/sphere-forgehome.md), concentrated on Peculium and in the working levels of the inner worlds, and it does not proselytize outward. Warforged who leave the sphere rarely find others of their faith and rarely look. Most who keep it keep it privately, without shrine or observance, in the manner of a thing carried rather than practiced.

Beyond Alpha, worship follows the element, and most Warforged are drawn to the elemental lord matching their own bound spirit. This produces a devotional relationship with few parallels elsewhere: a fire-souled Warforged before the lord of flame is not petitioning a distant power but standing in front of the pure form of the thing it is partly made of. Such observance is private and unstructured, with no clergy and no calendar, and what exists instead is architecture. Shrines are built into the working levels of every world and cut into the rocks of [Peculium](../spelljamming/sphere-forgehome.md), raised to the element rather than to any doctrine, so that a sanctuary to the lord of the seas is flowing line and water motif while a shrine to the lord of flame is organized around a fire never permitted to go out."""),
            ("Community and Contributions", """\
[Peculium](../spelljamming/sphere-forgehome.md) is the closest thing the Warforged have to a homeland. The rocks hold no atmosphere, which is why they remain Warforged in practice: nothing that breathes can live there in any number. Warforged quarter in bored-out workings and in hulls salvaged from the yards, strung together by lines and gantries. Those who have settled the [Life Debt](#the-life-debt) keep shops there, registered with the House and held under its title, dealing in scrap, salvage, repair, and parts pulled from decommissioned stock.

Outside [Forgehome](../spelljamming/sphere-forgehome.md), Warforged integrate with less friction than their origins would predict. Part of it is temperamental fit — fire-souled where drive is short, water-souled in mediation, often by default. The broader reason is that a Warforged arrives at a problem without the assumptions everyone else in the room grew up inside. Not being born into a culture is an advantage in seeing it clearly and a liability in every exchange that depends on knowing what goes without saying.

They are aware of the curiosity they attract and largely untroubled by it. What they resist is being a curiosity permanently — a demonstration of something rather than a participant in it."""),
        ],
    },
}

# Cards written since the import, listed under the card they follow. A card
# added here goes in after that one, so the page keeps the order it is meant to
# read in rather than collecting new material at the foot.
NEWCARDS = {
    "anthropology-warforged": [
        ("Origin Story", "The Life Debt", """\
After the resolution of the [Warforged Civil War](../faction/house-of-fabrication.md#warforged-civil-war), Warforged gained their personhood in the eyes of the House. However, this caused the creation of the Life Debt: the sum total of the materials used in its creation. In practice, it is used as a way for the House to keep the Warforged in their service in exchange for freeing them from slavery. While a Warforged has a Life Debt, they cannot hold any property nor can they refuse an order by the House. Their wages are used to reduce the Debt, yet their repairs are used to increase it, keeping them in a perpetual juggling act for their livelihood.

Opinions are split among the [Known Spheres](../spelljamming/known-spheres.md) as to whether this is a justified exchange for their creation, and whether it is just slavery by another name. Those in favor see it as a way for the Warforged to earn their place in a world that made them, since they cannot naturally be born. The opposition to the Debt see it as a cheap and abusive way for the House to maintain their slave labor under the guise of paying off your own existence, which they were not able to consent to. The Debt has caused a state of destitute and disrepair among its Populace: Warforged refuse repairs for months at a time as a way to pay off their Debt faster, causing lifelong complications.

Those who are able to pay off their Life Debt are given a ceremony where they are offered a choice: join the [Artisan Caste](../faction/house-of-fabrication.md#caste-system) and work for the company as a citizen, or free yourself of the company and the sphere by leaving and never returning. Most Warforged join the Artisan Caste and take ownership of their personal affects and living quarters, continuing their work but making a wage. Others start businesses in [Peculium](../spelljamming/sphere-forgehome.md) helping other Warforged with makeshift repairs and other services. Fewer still decide to leave the sphere, whereupon they are given their personal affects and equipment to survive in the Known Spheres, then delivered to a sphere and planet of their choice."""),
    ],
}


# Disambiguation stubs, and the page each one is disambiguating. The stub said
# only "This page is currently used for disambiguation" and gave the reader no
# way to reach the article it was pointing at - a dead end where a signpost was
# meant to be.
DISAMBIGUATION = {
    "poi-darkastle": "settlement-darkastle",
}

# part slug -> (merged slug, anchor of its section)
MERGE_PARTS = {}
for _merged, _spec in MERGES.items():
    for _label, _part in _spec["parts"]:
        MERGE_PARTS[_part] = (_merged, _label.lower().replace(" ", "-"))


# Pages whose slug never got a prefix, listed under the folder they belong to.
#
# Wikidot's prefixes were applied by hand and inconsistently: twelve gods were
# filed under "deity-" and eighteen were not, six of the seven factions were
# left loose, and no plane or region ever got one. The pages are the same
# shape either way, so this is authoring drift rather than a distinction.
#
# Membership is deliberately a list rather than a rule. "Void" and "Plane of
# Faerie" are stubs of the same shape as the deity stubs and are not gods;
# nothing in the page itself separates them. Each name below was checked
# against what the wiki says about it - the pantheon index for the gods, The
# Index's own Factions and Homebrew: Items sections, cosmology for the planes,
# and the world map's legend for the regions.
LOOSE_PAGES = {
    "deity": {
        "asmodeus", "cavri", "droma", "enigma", "fink", "fronir", "frymrit",
        "ithlwick", "leshrac", "nessa", "orion", "ornus", "rasmin", "sezzek",
        "silfaraan", "tari", "trelanni", "ythedie",
    },
    # The Index lists six of these under Factions. Sylvan Sect is not on that
    # list, but it is a 6-word stub and the only description of it anywhere -
    # Aesc Wood's "members of the Sylvan Sect" - reads as an organisation.
    "faction": {
        "collegiate-oculatus", "haven-commerce", "imperial-mercenary",
        "sylvan-sect", "taelmythaal-archivists", "tamaas-trading",
        "titan-fall-pmc",
    },
    # Every one of these is linked from the cosmology page, except the Plane
    # of Faerie, which is a stub reached from Aesc Wood.
    "plane": {
        "astral-plane", "ethereal-plane", "plane-of-faerie", "plane-of-mirrors",
        "region-of-dreams", "true-afterlife", "void",
    },
    # Three are the legend of the world map. Aesc Wood is a forest.
    "region": {
        "aesc-wood", "antaeran-plains", "coastal-barrier-range", "sea-of-innas",
    },
    "settlement": {
        "aberystwyth", "athelney", "imperial-capital-of-new-haven",
    },
    # The Index, Homebrew: Items.
    "item": {
        "crystal-stabilization-fluid", "elven-climbers-gloves", "firearms",
        "planar-crystal", "poisoners-quiver",
    },
    # Action Points is under Variant Rules In Effect and Backgrounds under
    # Homebrew: Miscellaneous; Gestalt is a variant rule nothing links to.
    "rules": {"action-points", "backgrounds", "gestalt"},
}

PAGE_FOLDER = {s: f for f, slugs in LOOSE_PAGES.items() for s in slugs}

# Images kept in docs/img but not placed on any page. The file stays where it
# is, so putting one back is a matter of referencing it again.
#
# The under-construction sign marked pages that were still being written - it
# sat on 24 of them. work-in-progress.md records which, since that is the only
# place the information survives once the sign is off the pages.
#
# It reached the import named after the first page that used it, which is worth
# knowing: shared images take the name of whichever page referenced them first,
# and that name is misleading everywhere else.
DROP_IMAGES = {
    "shared_under_construction.png",
}

# Images swapped for a different file. The original stays in docs/img rather
# than being deleted, so it can be put back by editing this map.
REPLACE_IMAGES = {
    "start_header.png": "start_header_spelljammer.jpg",
}

# Where an image came from. Rendered under it as a credit line, matching how
# the wiki already credits the art it borrows.
IMAGE_CREDITS = {
    "start_header_spelljammer.jpg":
        "https://store.epicgames.com/news/neverwinter-s-developers-talk-"
        "spelljammer-space-and-intergalactic-travel?lang=en-US",
}

# Sections retired from the live wiki. Pages under these folders are flagged
# archived: kept and readable, but kept out of search, so
# they cannot be mistaken for current material.
ARCHIVED_FOLDERS = {"wm"}

# Folders holding a page per god. Their titles are read off the page rather
# than built from the slug - see the title block in main().
DEITY_FOLDERS = {"deity", "pantheon"}

# What a god's page is made of. Every one, whichever template it was written
# from, opens with a few short facts and then runs through sections of prose;
# the pages differed only in how they wrote that down. A stat is one of the
# short facts and goes in the list at the top. A section is prose and gets a
# heading of its own. "Origins" is both: a line of fact on Enigma's page, a
# paragraph on the pantheon's, and which it is depends on how it was written.
DEITY_STATS = {
    "Name", "Symbol", "Home Plane", "Alignment", "Portfolio", "Worshipers",
    "Cleric Alignments", "Domain", "Domains", "Favored Weapon", "Origins",
}
DEITY_SECTIONS = {
    "Appearance", "Backstory", "Description", "Origins", "Dogma", "Home Sphere",
    "Divine Realm", "Infernal Dominion", "Abyssal Dominion",
    "Holy Symbol", "Unholy Symbol", "Clergy and Temples", "Cult and Temples",
    "Rivalries", "The Wandering Mystery", "Reverence and Speculation",
    "Gifts of Enigma",
}

TODO = []


def target_path(slug):
    """Where a Wikidot slug lands under docs/."""
    if slug == "start":
        return "index.md"
    slug = slug.replace(":", "-")
    if slug in MERGE_PARTS:
        return MERGE_PARTS[slug][0] + ".md"
    if slug in APPEND_TO:
        return target_path(APPEND_TO[slug])
    if slug in PAGE_FOLDER:
        return PAGE_FOLDER[slug] + "/" + slug + ".md"
    m = re.match(r"^([a-z]+)-(.+)$", slug)
    if m and m.group(1) in FOLDERS:
        return FOLDERS[m.group(1)] + "/" + m.group(2) + ".md"
    return slug + ".md"


# Titles a slug cannot produce. Set here rather than in the nav so the browser
# tab, the search results and the sidebar all agree.
TITLES = {
    "start": "Main Page",
    "pantheons": "The Pantheons",
    "cosmology": "The Cosmology",
    "spelljamming-known-spheres": "The Known Spheres",
    "map-antaera": "Antæra World Map",
    "taxonomy-main": "Taxonomies",
    "calendar": "Antæran Calendar",
    "spelljamming-main": "Spelljamming",
    "wm-index": "Stellar Marches (5e: 2014)",

    # The items. None of these pages carried a name of its own, so the titles
    # were built from their slugs and lost the punctuation - "Poisoners
    # Quiver", "Elven Climbers Gloves". These are the names The Index gives
    # them, which is the wiki's own naming rather than a guess.
    "crystal-stabilization-fluid": "Crystal Stabilization Fluid",
    "elven-climbers-gloves": "Elven Climber's Gloves",
    "poisoners-quiver": "Poisoner's Quiver",
    "item-blessed-holy-symbol": "Profane/Blessed (Un)Holy Symbol",
    "item-dreaming-waking": "The Dreaming & Waking",

    # The one god of fifty-nine whose page writes the epithet in lower case.
    # Every other one is "Patron of", "Lord of", "Herald of"; this is the only
    # place the wiki disagrees with itself about it.
    "orion": "Orion, Patron of Smallfolk",
}

# Pages whose opening heading should be replaced by the page's title, because
# the two disagreed. Filled in at run time - see the sphere names in main().
#
# There was a second list beside this one, of the six pages that never named
# themselves at all - they opened on a stat block, on a run of sub-headings, or
# straight into prose - and had their title inserted as an opening heading. It
# is gone: every page carries its name on a card of its own now, so there is
# nothing left for that list to fix.
TITLE_HEADING = set()


# Headings too generic to serve as a page title.
GENERIC_HEADINGS = {
    "overview", "introduction", "intro", "summary", "description",
    "background", "contents", "about",
}


def norm_slug(target):
    """Normalise a Wikidot link target the way Wikidot itself does.

    Links are written either as a slug ("deity-ukrol") or as a page title
    ("Ethereal Plane"), and Wikidot resolves both to the same page. Matching
    only the literal slug turned every title-form link into plain text.

    Accented letters transliterate rather than vanish - "Æsc Wood" is the page
    "aesc-wood", not "sc-wood" - and apostrophes are dropped rather than
    becoming a separator, so "Sil'Faraan" is "silfaraan".
    """
    t = target.strip().lstrip("/").lower()
    t = t.replace("æ", "ae").replace("œ", "oe").replace("ß", "ss").replace("ø", "o")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"['‘’]", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def slug_keys(target):
    """Every name a link might be using for this page.

    The apostrophe is the awkward one, because Wikidot's own page names
    disagree about it. The page for Sil'Faraan is "silfaraan", with the
    apostrophe dropped; the page for Vrog'thul is "vrog-thul", with it turned
    into a hyphen the way any other punctuation would be. A link written one
    way has to find a page named the other, so both spellings are offered and
    the first one that names a real page wins.

    This is not hypothetical: the pantheon lists all eleven Heralds, and
    Vrog'thul was the only one whose name was not a link, because
    "pantheon-deity-Vrog'thul" resolved to "pantheon-deity-vrogthul" and the
    page is "pantheon-deity-vrog-thul". It left the page reachable from nowhere
    on the site.
    """
    keys = [norm_slug(target)]
    alt = norm_slug(re.sub(r"['‘’]", "-", target))
    if alt and alt not in keys:
        keys.append(alt)
    return keys


def title_from(slug):
    """Human title from a slug, minus any prefix that only classifies it."""
    m = re.match(r"^([a-z]+)-(.+)$", slug)
    if m and (m.group(1) in FOLDERS or m.group(1) in TITLE_PREFIXES):
        slug = m.group(2)
    return slug.replace(":", " ").replace("-", " ").replace("_", " ").strip().title()


def _cell_width(attrs):
    m = re.search(r"width:\s*([\d.]+)\s*%", attrs or "", re.I)
    return float(m.group(1)) if m else None


def _is_data_grid(rows):
    """True when a [[table]] holds tabular data rather than page layout.

    Wikidot used tables for both. A grid of short values is data; anything
    carrying a heading or a paragraph of prose is layout, and flattening it
    into a Markdown table would destroy the page's shape.
    """
    if len(rows) < 2:
        return False
    counts = {len(r) for r in rows}
    if len(counts) != 1 or counts.pop() < 2:
        return False
    for row in rows:
        for _, body in row:
            if re.search(r"^\s*\+", body, re.M):
                return False
            if len(body.strip()) > 200:
                return False
    return True


def tables_to_layout(s):
    """Wikidot tables become Markdown tables (data) or cards (layout).

    Layout cells keep their proportions: a 25%/75% row stays a sidebar beside
    its content on a wide screen and stacks on a narrow one.
    """

    def repl(m):
        # The table's own width, where it declared one. 107 of them ask for
        # 66.7%, which is how the wiki kept its cards off the full width of the
        # page; carrying it through is more faithful than guessing a cap.
        table_w = _cell_width(m.group(0)[:m.group(0).find("]]")])

        rows = []
        for rm in re.finditer(r"\[\[row[^\]]*\]\](.*?)\[\[/row\]\]", m.group(1), re.S | re.I):
            cells = [(cm.group(1), cm.group(2)) for cm in
                     re.finditer(r"\[\[cell([^\]]*)\]\](.*?)\[\[/cell\]\]", rm.group(1), re.S | re.I)]
            if cells:
                rows.append(cells)
        if not rows:
            return ""

        if _is_data_grid(rows):
            grid = [[" ".join(b.split()) for _, b in r] for r in rows]
            width = max(len(r) for r in grid)
            grid = [r + [""] * (width - len(r)) for r in grid]
            head = "| " + " | ".join(grid[0]) + " |"
            sep = "|" + "---|" * width
            body = "\n".join("| " + " | ".join(r) + " |" for r in grid[1:])
            return "\n\n" + head + "\n" + sep + "\n" + body + "\n\n"

        out = []
        for cells in rows:
            kept = [(a, b) for a, b in cells if b.strip()]
            if not kept:
                continue
            widths = [_cell_width(a) for a, _ in kept]
            # Two cells that both claim 75% do not describe a split - there is
            # no room for it. Four rows are written that way. A browser drops
            # to auto table layout there and sizes by content, which is how
            # they were read: measured, 69% against 22%. That is this wiki's
            # ordinary sidebar, so use it, with the fuller cell taking the
            # larger share. Taken literally the row came out as two columns of
            # equal weight and the sidebar was as wide as the article.
            if len(kept) == 2 and all(widths) and sum(widths) > 100:
                big = 0 if len(kept[0][1]) >= len(kept[1][1]) else 1
                widths = [75.0, 25.0] if big == 0 else [25.0, 75.0]
            # Wikidot rows often size only some cells - "width: 75%" on the
            # content, nothing on the sidebar beside it. Requiring every cell
            # to declare a width made those rows fall back to stacking, which
            # is exactly the layout the width was there to prevent. Share what
            # is left over among the cells that did not declare one.
            # A row where no cell declares a width and one of them holds only a
            # picture: the picture is an illustration beside the article, not a
            # second column of it. Nothing in the markup said so - the original
            # sized these by content and came out at 76/23 - so with no widths
            # at all the row collapsed to one column and the picture was drawn
            # full width underneath the text it belonged next to.
            media = [i for i, (_, b) in enumerate(kept) if _media_only(b)]
            if len(kept) == 2 and not any(widths) and len(media) == 1:
                widths = [25.0 if i == media[0] else 75.0 for i in range(2)]
            if len(kept) > 1 and any(w for w in widths) and not all(w for w in widths):
                known = sum(w for w in widths if w)
                blanks = [i for i, w in enumerate(widths) if not w]
                share = max((100.0 - known) / len(blanks), 5.0)
                for i in blanks:
                    widths[i] = share
            # A narrow column is a sidebar, and gets a smaller font so it reads
            # as an aside rather than a second column of equal weight.
            #
            # Its width is left at the source proportion. These were widened
            # once, to compensate for the content column being 621px against
            # Wikidot's 1402px; now that the page is its proper width, the same
            # widening makes a sidebar look like just another cell.
            classes = ["wd-cell"] * len(kept)
            total = sum(w for w in widths if w) or 100.0
            if len(kept) > 1:
                for i, w in enumerate(widths):
                    # A picture is not a text aside and does not want the
                    # smaller type; it wants the box taken off, which the
                    # media-cell pass below gives it.
                    if w and (w / total) * 100 < 35 and i not in media:
                        classes[i] = "wd-cell wd-aside"

            props = []
            if len(kept) > 1 and all(w for w in widths):
                # A custom property, not grid-template-columns directly: the
                # stylesheet applies it only above the mobile breakpoint so the
                # columns still stack on a phone.
                props.append("--wd-cols: %s" % " ".join("%gfr" % w for w in widths))
            if table_w and table_w < 100:
                # Resolved against Wikidot's own 1402px page rather than left
                # as a percentage. A percentage is relative to whatever column
                # it lands in, so the same table came out a different size here
                # than it did there; the pixel width is what the reader saw.
                props.append("--wd-rw: %dpx" % round(table_w / 100.0 * 1402))
            style = ' style="%s"' % "; ".join(props) if props else ""
            out.append('<div class="wd-row"%s markdown>' % style)
            for idx, (_, body) in enumerate(kept):
                out.append('<div class="%s" markdown>' % classes[idx])
                out.append("")
                out.append(body.strip())
                out.append("")
                out.append("</div>")
            out.append("</div>")
        return "\n\n" + "\n".join(out) + "\n\n"

    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\[\[table[^\]]*\]\](.*?)\[\[/table\]\]", repl, s, flags=re.S | re.I)
    return s


_COL = re.compile(
    r'<div class="wd-col" style="--wd-w: ([\d.]+%)" markdown>\n(.*?)\n</div>\n',
    re.S,
)


def merge_column_runs(s):
    """Turn a run of equal-width floated divs into one balanced column flow.

    The wiki built columns by floating two or three divs side by side and
    splitting the content between them by hand. Separate boxes cannot balance
    against each other, so a long entry in the second column left the first
    ending halfway up the page.

    Merging a run into a single multi-column element lets the browser balance
    the heights, and because it fills the first column before the second, the
    weight falls to the left.
    """

    out, run, pos = [], [], 0

    def flush():
        if not run:
            return
        if len(run) == 1:
            width, body = run[0]
            out.append('<div class="wd-col" style="--wd-w: %s" markdown>\n%s\n</div>\n'
                       % (width, body))
        else:
            cols = max(2, min(4, int(round(100.0 / float(run[0][0].rstrip("%"))))))
            joined = "\n\n".join(b.strip() for _, b in run)
            out.append('<div class="wd-cols" style="--wd-n: %d" markdown>\n\n%s\n\n</div>\n'
                       % (cols, joined))
        del run[:]

    for m in _COL.finditer(s):
        gap = s[pos:m.start()]
        # Anything between two of these divs, or a change of width, ends the run.
        if gap.strip() or (run and run[0][0] != m.group(1)):
            flush()
        out.append(gap)
        run.append((m.group(1), m.group(2)))
        pos = m.end()

    flush()
    out.append(s[pos:])
    return "".join(out)


def unwrap_table_only_cards(s):
    """Strip the card box from a cell holding nothing but a table or image.

    The rules tables were screenshots sitting inside a layout cell. Now that
    they are real Markdown tables, the card would draw a border around
    something that already has one. The cell keeps its place in the row - it
    is often one column of a two-column layout - it just loses the box.
    Cells holding prose keep their card.
    """

    def repl(m):
        inner = m.group(1)
        if "<div" in inner:
            return m.group(0)
        lines = [l for l in inner.split("\n") if l.strip()]
        if not lines:
            return m.group(0)
        table_lines = [l for l in lines if l.lstrip().startswith("|")]
        image_lines = [l for l in lines if l.lstrip().startswith("![](")]
        # One spare line each way, so a caption still counts as media-only.
        table_only = len(table_lines) >= 2 and len(lines) - len(table_lines) <= 1
        image_only = len(image_lines) >= 1 and len(lines) - len(image_lines) <= 1
        if not (table_only or image_only):
            return m.group(0)
        return m.group(0).replace('class="wd-cell"', 'class="wd-cell wd-plain"', 1)

    return re.sub(r'<div class="wd-cell" markdown>(.*?)\n</div>', repl, s, flags=re.S)


def _media_only(body):
    """True when a cell holds a picture, or a table, and nothing but a caption.

    Both spellings of a picture are matched. This is called from the layout
    pass, which runs before Wikidot's [[image]] becomes Markdown, so testing
    only for the Markdown form found nothing and every picture-beside-text row
    on the site stacked instead of sitting side by side.
    """
    lines = [l for l in body.strip().split("\n") if l.strip()]
    if not lines:
        return False
    images = [l for l in lines
              if l.lstrip().startswith("![](")
              or re.match(r"^\s*\[\[f?image\b", l, re.I)]
    rows = [l for l in lines if l.lstrip().startswith("|")]
    # One spare line each way, so a caption still counts as media-only.
    return ((len(images) >= 1 and len(lines) - len(images) <= 1)
            or (len(rows) >= 2 and len(lines) - len(rows) <= 1))


def convert(src, slug, img_by_url, tables, linkmap):
    s = src.replace("\r\n", "\n")
    s = re.sub(r"\[!--.*?--\]", "", s, flags=re.S)
    s = re.sub(r"\[\[toc[^\]]*\]\]", "", s, flags=re.I)

    def todo(what):
        TODO.append((slug, what))
        return "\n<!-- TODO(" + what + ") -->\n"

    # [[code]] blocks become fenced code before anything else touches them.
    s = re.sub(r"\[\[code[^\]]*\]\](.*?)\[\[/code\]\]",
               lambda m: "\n```\n" + m.group(1).strip() + "\n```\n", s, flags=re.S | re.I)

    s = re.sub(r"\[\[module\s+(\w+).*?(?:\[\[/module\]\]|\]\])",
               lambda m: todo("module " + m.group(1)), s, flags=re.S | re.I)
    # Orphaned closers left when the opener matched its own ]] first.
    s = re.sub(r"\[\[/module\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[user\s+([^\]]+)\]\]", r"\1", s, flags=re.I)
    s = re.sub(r"\[\[/?button[^\]]*\]\]", "", s, flags=re.I)
    # Manual anchors and back-to-top links: Material generates heading anchors
    # and shows a back-to-top button, so both are redundant scaffolding.
    s = re.sub(r"\[\[#[^\]]*\]\]", "", s)
    s = re.sub(r"\[/#[^\s\]]*\s*\([^)]*\)\]", "", s)
    s = re.sub(r"\[\[include\s+([^\s\]]+).*?\]\]",
               lambda m: todo("include " + m.group(1)), s, flags=re.S | re.I)
    s = re.sub(r"\[\[iframe.*?\]\]", lambda m: todo("iframe"), s, flags=re.S | re.I)

    # A placeholder for art that was never added, together with the caption
    # written under it. The two are one thing: the caption describes a picture
    # that does not exist. Dropping the image and keeping the caption left a
    # card holding nothing but a label for a missing header - which is what was
    # on The Known Spheres.
    #
    # Two shapes. Most pages hold the slot open with a sourceless [[image]];
    # the unfilled templates just write the words out.
    s = re.sub(r"^[ \t]*\[\[f?image\s+(?!https?)[^\]]*\]\][ \t]*\n"
               r"(?://[^\n]*//[ \t]*\n)?", "", s, flags=re.I | re.M)
    s = re.sub(r"^[ \t]*Header Image[ \t]*\n"
               r"(?://[^\n]*//[ \t]*\n)?", "", s, flags=re.I | re.M)

    s = tables_to_layout(s)

    # Images: swap the imgur URL for the local file, or inline the transcribed
    # table when the picture was a picture of a table.
    def image(m):
        url = m.group(1)
        # A sourceless [[image  width="50%"]] is a placeholder for art that was
        # never added - 22 pages carry one, usually in a header table of its
        # own. Dropping it empties that cell, and the empty-cell pass below
        # then removes the table it sat in.
        if not url.lower().startswith("http"):
            return ""
        fn = img_by_url.get(url)
        if not fn:
            return ""
        # Kept in docs/img but deliberately not placed on any page.
        if fn in DROP_IMAGES:
            return ""
        fn = REPLACE_IMAGES.get(fn, fn)
        stem = os.path.splitext(fn)[0]
        if stem in tables:
            return "\n\n" + tables[stem].strip() + "\n\n"
        md = "![](" + BASE + "/img/" + fn + ")"
        credit = IMAGE_CREDITS.get(fn)
        if credit:
            md += "\n\n*[Credits](" + credit + ")*"
        return md

    s = re.sub(r"\[\[f?image\s+([^\s\]]+)[^\]]*\]\]", image, s, flags=re.I)

    # Cells are built before images are resolved, so a cell whose only content
    # was a dropped image is left as an empty box. Clear those, then any row
    # left holding nothing.
    s = re.sub(r'<div class="wd-cell[^"]*" markdown>\s*</div>\s*', "", s)
    s = re.sub(r'<div class="wd-row"[^>]*markdown>\s*</div>\s*', "", s)

    s = unwrap_table_only_cards(s)

    # Links back to the old Wikidot site are internal links written the long
    # way. Left alone they send readers off this wiki and break entirely if
    # that site is ever taken down, so resolve them like any other page
    # reference by rewriting them into Wikidot's own link syntax first.
    # The trailing group swallows any #fragment or ?query: those point at text
    # anchors that do not survive the move, and leaving them made the bare-URL
    # rule fire inside a link that was already bracketed.
    self_url = (r"https?://(?:www\.)?(?:antaera|legendsofantaera)\.wikidot\.com/"
                r"([A-Za-z0-9:_-]+)[^\s\]|]*")
    s = re.sub(r"\[\[\[\s*" + self_url + r"\s*\|([^\]]+)\]\]\]", r"[[[\1|\2]]]", s)
    s = re.sub(r"\[\[\[\s*" + self_url + r"\s*\]\]\]", r"[[[\1]]]", s)
    s = re.sub(r"\[\*?" + self_url + r"\s+([^\]]+)\]", r"[[[\1|\2]]]", s)
    s = re.sub(self_url, r"[[[\1]]]", s)

    # Hide URLs so the italic rule cannot eat the // in https://
    urls = []

    def hide(m):
        urls.append(m.group(0))
        return "\x00U%d\x00" % (len(urls) - 1)

    s = re.sub(r"https?://[^\s\)\]\"']+", hide, s)

    # [[div]] carried the column layouts inside cells - the three-across
    # indexes on The Index are floated 33% divs. Stripping them, as this used
    # to, collapsed those columns into one long list.
    def divopen(m):
        attrs = m.group(1) or ""
        width = re.search(r"width:\s*([\d.]+\s*%)", attrs, re.I)
        cls = ["wd-col"]
        if re.search(r"float:\s*right", attrs, re.I):
            cls.append("wd-col--right")
        if re.search(r"border\s*:", attrs, re.I):
            cls.append("wd-col--boxed")
        style = ' style="--wd-w: %s"' % width.group(1).replace(" ", "") if width else ""
        return '<div class="%s"%s markdown>\n' % (" ".join(cls), style)

    s = re.sub(r"\[\[div([^\]]*)\]\]", divopen, s, flags=re.I)
    s = re.sub(r"\[\[/div\]\]", "\n</div>\n", s, flags=re.I)
    # Only now do the column divs exist to be merged.
    s = merge_column_runs(s)
    # size and span carried no layout, only presentation.
    s = re.sub(r"\[\[/?(?:size|span)[^\]]*\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[note\]\](.*?)\[\[/note\]\]",
               lambda m: "!!! note\n" + "\n".join("    " + l for l in m.group(1).strip().split("\n")),
               s, flags=re.S | re.I)

    here = os.path.dirname(target_path(slug))

    def link(target, text):
        dest = next((linkmap[k] for k in slug_keys(target) if k in linkmap), None)
        if not dest:
            return text
        # A merged page's entry carries the anchor of the half that was asked
        # for. Only the path part takes place in the relative-path maths.
        dest, _, anchor = dest.partition("#")
        rel = os.path.relpath(dest, here or ".").replace("\\", "/")
        if anchor:
            rel += "#" + anchor
        return "[" + text + "](" + rel + ")"

    s = re.sub(r"\[\[\[([^\]|]+)\|([^\]]+)\]\]\]", lambda m: link(m.group(1), m.group(2).strip()), s)
    s = re.sub(r"\[\[\[([^\]|]+)\]\]\]", lambda m: link(m.group(1), m.group(1).strip()), s)

    # Wikidot internal links of the form [/some-slug link text]
    s = re.sub(r"\[/([a-z0-9:_/-]+)\s+([^\]]+)\]",
               lambda m: link(m.group(1).split("/")[0], m.group(2).strip()), s, flags=re.I)

    # External links. Wikidot writes [url text], and [*url text] when the link
    # should open in a new window - the asterisk sits between the bracket and
    # the URL, so it has to be allowed for or the link never converts. Image
    # credit lines all use the starred form.
    s = re.sub(r"\[\*?(\x00U\d+\x00)\s+([^\]]+)\]", r"[\2](\1)", s)

    # Protect finished Markdown tables. The strikethrough rule below turns
    # "--x--" into "~~x~~", which would otherwise chew through a "|---|---|"
    # separator row and silently stop the table being a table.
    blocks = []

    def stash(m):
        blocks.append(m.group(0))
        return "\x00T%d\x00" % (len(blocks) - 1)

    s = re.sub(r"(?:^\|.*\|[ \t]*\n)+", stash, s, flags=re.M)

    # Ordered lists BEFORE headings: Wikidot writes "# item" for a numbered
    # list, which Markdown reads as an H1. Converting headings first would
    # then turn those list items into headings and hide the collision.
    s = re.sub(r"^( *)#\s+(.+)$",
               lambda m: "    " * len(m.group(1)) + "1. " + m.group(2), s, flags=re.M)

    s = re.sub(r"^(\+{1,6})\s*(.+)$",
               lambda m: "#" * len(m.group(1)) + " " + m.group(2).strip(), s, flags=re.M)
    s = re.sub(r"(?<!\w)//(?=\S)(.+?)(?<=\S)//(?!\w)", r"*\1*", s, flags=re.S)
    s = re.sub(r"(?<!-)--(?=\S)(.+?)(?<=\S)--(?!-)", r"~~\1~~", s)
    s = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<u>\1</u>", s)
    # Bullets. Wikidot nests with a single space per level; Markdown needs four
    # to read an item as a sublist, so one space produced a flat list.
    s = re.sub(r"^( *)\*\s+", lambda m: "    " * len(m.group(1)) + "- ", s, flags=re.M)
    # An index written as "* 01: Something" is an ordered list wearing bullets.
    # Only the colon form qualifies: "01-95 Standard system" is a dice range,
    # not a sequence, and has to stay a bullet.
    numbered = re.compile(r"^(\s*)-\s+(\d{1,3}):\s+(.*)$")
    lines, rebuilt, i = s.split("\n"), [], 0
    while i < len(lines):
        j = i
        while j < len(lines) and numbered.match(lines[j]):
            j += 1
        if j - i >= 2:
            for k in range(i, j):
                m = numbered.match(lines[k])
                rebuilt.append("%s%d. %s" % (m.group(1), int(m.group(2)), m.group(3)))
            i = j
        else:
            rebuilt.append(lines[i])
            i += 1
    s = "\n".join(rebuilt)

    s = re.sub(r"^-{4,}$", "---", s, flags=re.M)

    # Markdown needs a blank line before a list. Wikidot does not, and wrote
    # lists straight under the paragraph that introduces them - without this
    # the whole list is folded into that paragraph and renders as prose.
    item = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
    lines, spaced = s.split("\n"), []
    for ln in lines:
        if item.match(ln) and spaced and spaced[-1].strip() and not item.match(spaced[-1]):
            spaced.append("")
        spaced.append(ln)
    s = "\n".join(spaced)
    s = re.sub(r"\x00T(\d+)\x00", lambda m: blocks[int(m.group(1))], s)
    s = re.sub(r"\x00U(\d+)\x00", lambda m: urls[int(m.group(1))], s)
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    # A lone underscore is Wikidot's spacer, used to force a blank line. It is
    # not content, and left in place it prints as a stray "_" - or, since every
    # adjacent line now gets a break, tacks one onto the caption above it.
    s = re.sub(r"^[ \t]*_[ \t]*$", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = spell_cards(s)
    s = expand_item_blocks(s)
    s = stat_line_breaks(s)
    s = house_style(s)
    s = heading_levels(s)
    s = table_notes(s)
    # One race, two names. "Mercane" is the name in use - the passage device is
    # "a creation of the Mercane" and the planetary locator comes with "a
    # Mercane hull" - while sixteen other mentions still said "Arcane", one of
    # them in the same sentence as a Mercane. They are one people; the wiki now
    # calls them one thing.
    #
    # Arcane Space is a region and Arcane Talent is a feat. Neither is the
    # race, so both are left as they are.
    s = re.sub(r"\bArcane\b(?!\s+(?:Space|Talent))", "Mercane", s)
    return s.strip() + "\n"


# ---------------------------------------------------------------------------
# Spell cards
#
# A spell or psionic power written as a stat block. The wiki has one house
# format for these; the pages disagreed with each other on nearly every point
# of it, so this normalises them all to:
#
#   title        the spell's name, bold, no italics
#   school       directly below, italic, no bold
#   stat block   after a blank line, one stat per line, "**Label**: value", in
#                the order Level, Components, Casting Time, Range, Target (or
#                Area/Effect), Duration, Saving Throw, Spell Resistance
#   flavour      after a blank line, one fully italic paragraph - where the
#                spell already has one. None are invented.
#   description  after a blank line, plain text, any number of paragraphs
#   component    a bold sub-header ("Material Component", "Focus") with its
#                description italicised on the line below
#
# The stat lines need explicit breaks. Wikidot renders a single newline inside
# a paragraph as <br> and Markdown does not, so every stat block on the site
# was running together into one paragraph of prose.
# ---------------------------------------------------------------------------

SPELL_HEAD = re.compile(r"^(?:(#{2,4})\s+(.+)|\*\*([^*]+)\*\*)\s*$")
STAT = re.compile(r"^\*\*([^*]+?)\*\*\s*:\s?(.*)$")

# The order stats are listed in. Alternatives share a rank because they fill
# the same slot: a power's Display is its Components, an Area is its Target.
STAT_ORDER = {
    "level": 0,
    "components": 1, "display": 1,
    "casting time": 2, "manifesting time": 2,
    "range": 3,
    "target": 4, "targets": 4, "area": 4, "area of effect": 4, "effect": 4,
    "duration": 5,
    "saving throw": 6,
    "spell resistance": 7,
}

# A stat block using any of these is a psionic power rather than a spell.
PSIONIC_STATS = {"display", "manifesting time", "power points"}

# The order a magic item lists its stats in.
ITEM_ORDER = {
    "price (item level)": 0,
    "body slot": 1,
    "caster level": 2,
    "aura": 3,
    "activation": 4,
    "weight": 5,
}

# Sub-headers that introduce a component. The wiki wrote these three different
# ways - bold, italic, and inline with a colon - for the same thing.
COMPONENT_HEAD = re.compile(
    r"^[*]{0,3}(Material Components?|Focus|Arcane Focus|Divine Focus|"
    r"XP Cost)[*]{0,3}\s*:?\s*(.*)$", re.I)


def _emphasise(text, marks):
    """Re-mark a line: strip any existing emphasis, then apply `marks`."""
    text = text.strip()
    text = re.sub(r"^[*_]+|[*_]+$", "", text).strip()
    return marks + text + marks if text else text


def normalise_spell(block):
    """One spell block, rewritten to the house format."""
    out = [block[0]]                                   # title, left as it is
    i = 1
    while i < len(block) and not block[i].strip():      # skip a blank after it
        i += 1

    # School: italic, never bold, directly under the title.
    if i < len(block) and not STAT.match(block[i]):
        out.append(_emphasise(block[i], "*"))
        i += 1

    # Stat block: gather the run, order it, one per line.
    stats = []
    while i < len(block):
        if not block[i].strip():
            i += 1
            continue
        m = STAT.match(block[i])
        if not m:
            break
        stats.append((m.group(1).strip(), m.group(2).strip()))
        i += 1

    if stats:
        stats.sort(key=lambda kv: STAT_ORDER.get(kv[0].lower(), 99))
        out.append("")
        for n, (k, v) in enumerate(stats):
            # <br> on every line but the last: Markdown would otherwise fold
            # the whole run into a single paragraph.
            out.append("**%s**: %s%s" % (k, v, "" if n == len(stats) - 1 else "<br>"))

    # The rest of the block, with component sub-headers put right.
    rest = block[i:]
    # Two pages ran the description straight on from the last stat, which
    # Markdown reads as more of the same paragraph.
    if stats and rest and rest[0].strip():
        out.append("")
    n = 0
    while n < len(rest):
        ln = rest[n]
        m = COMPONENT_HEAD.match(ln.strip()) if ln.strip() else None
        if m and not STAT.match(ln):
            while out and not out[-1].strip():
                out.pop()
            out.append("")
            # The description goes on the line below the sub-header, which
            # needs the same explicit break the stat lines do.
            out.append("**" + m.group(1) + "**<br>")
            trailing = m.group(2).strip()
            if trailing:                       # was written inline: "*Focus*: a mirror"
                out.append(_emphasise(trailing, "*"))
                n += 1
                continue
            n += 1
            while n < len(rest) and not rest[n].strip():
                n += 1
            if n < len(rest):
                out.append(_emphasise(rest[n], "*"))
                n += 1
            continue
        out.append(ln)
        n += 1

    kind = "Psionic Power" if any(k.lower() in PSIONIC_STATS for k, _ in stats) else "Spell"
    return out, kind


# The older, compressed way the wiki wrote a magic item: everything on one
# line, semicolon separated.
#
#   Moderate Transmutation; CL 9; Craft Wondrous Item, *create portal*;
#   Price 81,000 gp; Weight 5 lbs
#
# It carries four of the six fields. Body Slot and Activation were never
# written down for these items, so they get an em dash rather than a guess.
COMPRESSED_ITEM = re.compile(
    r"^(?P<aura>[^;]+); CL (?P<cl>\d+); (?P<prereq>.+); "
    r"Price (?P<price>[^;]+); Weight (?P<weight>.+?)\s*$")


def _ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def expand_item_blocks(s):
    """Rewrite the compressed item line as the wiki's six-field block.

    The block moves to the top of its section, under the item's name, which is
    where the other item pages put it. The crafting prerequisites are not one
    of the six fields, so they stay at the foot of the section in the same
    italic form those pages use for them.
    """
    lines = s.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        m = COMPRESSED_ITEM.match(lines[i])
        if not m:
            continue
        # Back up to the heading this item sits under.
        h = i
        while h >= 0 and not re.match(r"^#{2,4}\s+\S", lines[h]):
            h -= 1
        if h < 0:
            continue
        lines[i] = "*Prerequisites*: " + m.group("prereq").strip()
        block = [
            "",
            "**Price (Item Level)**: " + m.group("price").strip(),
            "**Body Slot**: —",
            "**Caster Level**: " + _ordinal(m.group("cl")),
            "**Aura**: " + m.group("aura").strip(),
            "**Activation**: —",
            "**Weight**: " + m.group("weight").strip(),
            "",          # or the description folds into the stat paragraph
        ]
        lines[h + 1:h + 1] = block
    return "\n".join(lines)


# Lines that are their own block. A newline next to one of these is a break
# between blocks, not a break inside a paragraph.
BLOCK_LINE = re.compile(
    r"^\s*$|^#{1,6}\s|^<|^\||^\s*[-*+]\s|^\s*\d+\.\s|^>|^!\[|^\s*```|^!!!|^\?\?\?|^\s{4}")


def house_style(s):
    """Bring the page into the wiki's house style.

    Six inconsistencies, each of them the same idea written two or three ways
    because the wiki was authored by hand over a long time.
    """
    # 1. The world's name carries the ligature. Only the capitalised forms are
    #    touched, so the ASCII in slugs and link targets is left alone - a URL
    #    has no business carrying an æ.
    s = re.sub(r"\bAntaera(n?)\b", r"Antæra\1", s)

    # 2 and 3. A label at the start of a line is bold. It was bold on most
    #    pages, underlined on many and italic on a few - Benefit and
    #    Prerequisite were close to an even split between bold and <u>.
    #
    #    The underline tag is Wikidot markup with no Markdown equivalent, so it
    #    goes entirely: as a label it becomes bold, and anywhere else the tag is
    #    dropped and the words it wrapped stay as they are.
    s = s.replace("<u>", "").replace("</u>", "")
    #    Emphasis around a label is normalised after the tags are gone, which
    #    also repairs the three lines where the tag sat inside bold or italic
    #    and left "***Note from the DM**:" behind once it was removed.
    s = re.sub(r"^(\s*(?:[-*+]\s+)?)\*{1,3}([^*\n]{1,40}?)\*{1,3}\s*:",
               r"\1**\2**:", s, flags=re.M)
    #    An italic paragraph that opened on such a label has lost its opening
    #    marker; drop the stray closer at the end of it rather than leave an
    #    asterisk printed on the page.
    s = re.sub(r"^(\*\*[^*\n]{1,40}\*\*:[^\n]*[^*\s])\*$", r"\1", s, flags=re.M)

    # 4. In a table, a lone dash means "nothing here" and takes an em dash.
    #    The minus signs are not touched: all 64 of them are negative numbers -
    #    -1, -6, -9 in the saving throw tables - and an em dash there would not
    #    be a dash, it would be a wrong value. Ranges keep the en dash, which
    #    is what 98 of the 100 of them already use.
    def cells(m):
        row = m.group(0)
        out = []
        for c in row.split("|"):
            t = c.strip()
            # A dash on its own, or a dash carrying a footnote marker, both
            # mean the same thing and take the same character.
            m = re.fullmatch(r"([-–]|n/a|N/A)(\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+)?", t)
            if m:
                out.append(c.replace(t, "—" + (m.group(2) or "")))
            else:
                out.append(c)
        return "|".join(out)
    s = re.sub(r"^\|.*\|[ \t]*$", cells, s, flags=re.M)
    #    The two range outliers, brought into line with the other 98.
    s = re.sub(r"(?<=\d)[-−](?=\d)", "–", s)

    # 5. Units are the short form, without a stop: ft and lbs. "ft." keeps its
    #    full stop only where that stop is ending a sentence rather than
    #    abbreviating the word.
    s = re.sub(r"(\d)\s*feet\b", r"\1 ft", s)
    s = re.sub(r"(\d)\s*foot\b", r"\1 ft", s)
    s = re.sub(r"(\d)\s*pounds\b", r"\1 lbs", s)
    #    The stop comes off last, after the long forms have been shortened, or
    #    "230 pounds." turns into "230 lbs." and keeps a stop the rest lost. A
    #    stop that is ending a sentence rather than abbreviating stays put.
    s = re.sub(r"(?<![A-Za-z])ft\.(?!\s+[A-Z])", "ft", s)
    s = re.sub(r"(?<![A-Za-z])lbs\.(?!\s+[A-Z])", "lbs", s)

    # 6. A heading is a name, not a sentence, so it does not end in a colon.
    s = re.sub(r"^(#{1,6}\s+.+?)\s*:\s*$", r"\1", s, flags=re.M)
    #    A caption sits under its table and does not need to announce that it
    #    is one; 156 of the 170 already do not.
    s = re.sub(r"^(\*)Table:\s*", r"\1", s, flags=re.M)
    return s


def apply_rewrites(slug, body):
    """Swap in a section that has been rewritten since the import.

    The section runs from its heading to whichever comes first: the next
    heading, or the end of the card it sits in. Everything between is replaced,
    so the rewrite does not have to reproduce the layout around it.
    """
    for heading, text in REWRITES.get(slug, {}).items():
        pat = re.compile(
            r"(^#{1,6}[ \t]+" + re.escape(heading) + r"[ \t]*\n)"
            r".*?(?=\n</div>|\n#{1,6}[ \t]|\Z)", re.S | re.M)
        body, n = pat.subn(lambda m: m.group(1) + text.strip(), body)
        if n != 1:
            TODO.append((slug, "rewrite for '%s' matched %d sections" % (heading, n)))
    return body

def _card_span(body, heading):
    """Where the card that opens with `heading` starts and ends.

    The divs are counted rather than guessed at, so a card holding a picture or
    a nested row is not cut off at the first close. Returns the bounds, the
    heading's own level, and the row's opening line, so a caller can rebuild
    the card at the width the page already uses.
    """
    m = re.search(r"^(#{1,6})[ \t]+" + re.escape(heading) + r"[ \t]*$", body, re.M)
    if not m:
        return None
    start = body.rfind('<div class="wd-row', 0, m.start())
    if start < 0:
        return None
    depth = 0
    for d in re.finditer(r"<div\b|</div>", body[start:]):
        depth += 1 if d.group(0)[1] != "/" else -1
        if depth == 0:
            end = start + d.end()
            return start, end, m.group(1), body[start:body.index("\n", start) + 1]
    return None


def _card(row, level, heading, text):
    return (row + '<div class="wd-cell" markdown>\n\n%s %s\n%s\n\n</div>\n</div>\n'
            % (level, heading, text.strip()))


def apply_recards(slug, body):
    """Replace a card with one card for each section given.

    The card is matched whole and rebuilt as the sections listed against it,
    keeping the row's own width so the cards that replace it sit exactly where
    it sat.
    """
    for heading, sections in RECARDS.get(slug, {}).items():
        span = _card_span(body, heading)
        if span is None:
            TODO.append((slug, "no card found for '%s'" % heading))
            continue
        start, end, level, row = span
        cards = "".join(_card(row, level, h, t) for h, t in sections)
        body = body[:start] + cards.rstrip("\n") + body[end:]
    return body


def apply_newcards(slug, body):
    """Add a card after the one it belongs behind."""
    for after, heading, text in NEWCARDS.get(slug, []):
        span = _card_span(body, after)
        if span is None:
            TODO.append((slug, "no card found for '%s'" % after))
            continue
        _, end, level, row = span
        body = body[:end] + "\n" + _card(row, level, heading, text).rstrip("\n") + body[end:]
    return body

def _first_row(body):
    """The opening row of a page, divs counted rather than guessed at."""
    if not body.startswith('<div class="wd-row'):
        return None
    depth = 0
    for d in re.finditer(r"<div\b|</div>", body):
        depth += 1 if d.group(0)[1] != "/" else -1
        if depth == 0:
            return body[:d.end()]
    return None


def title_card(title, body):
    """Put the page's name on a card of its own, above everything else.

    The name used to be the heading of the first card, which asked one heading
    to do two jobs: name the page, and label the section beneath it. It could
    not do both, and the section was the one that lost - a page's opening card
    said "Beastfolk" where it meant "Overview".

    A page that opens on a header picture keeps the picture on top and takes
    the name underneath, where a title band belongs. The card is given the
    width the first row asks for, so it lines up with the page rather than
    running wider than everything under it.
    """
    width = re.search(r"--wd-rw:\s*([^;\"]+)", body)
    card = ('<div class="wd-row"%s markdown>\n'
            '<div class="wd-cell wd-title" markdown>\n\n'
            "# %s\n\n"
            "</div>\n</div>\n"
            % (' style="--wd-rw: %s"' % width.group(1).strip() if width else "",
               title))
    lead = _first_row(body)
    if lead and "wd-plain" in lead and lead.count('<div class="wd-cell') == 1:
        return body[:len(lead)] + "\n" + card + body[len(lead):].lstrip("\n")
    return card + body


def deity_format(body, title):
    """Give a god's page the layout every god's page shares.

    Fifty-eight pages of gods came from three templates and were written down
    at least five ways. The pantheon's twenty put their facts in a list and
    their sections under a bold word and a line break. The rest wrote a bold
    label with the colon outside it, or inside it, or followed by a line break,
    or with the prose running on after it on the same line; wrote their tenets
    as bold paragraphs, or as italic lines, or - once - as a whole italic
    sentence with the tenet's name folded into it; and put their pictures in a
    boxed sidebar or an unboxed one depending on nothing more than whether
    there happened to be one picture or two.

    They now read the same way:

      - the facts first, as one list, each "**Field**: value"
      - each section of prose under a heading of its own
      - the tenets as one list, "**Tenet**: what it asks", under "Tenets of"
        and the god's own name - which on Cervidur's page it was not: that
        heading said "Tenets of Orion", copied from the page it was made from
      - pictures in a boxed sidebar

    Nothing is reworded and no section is renamed. The one line removed is
    Enigma's "Name: Enigma, the Lost God", which is the page's title again.
    Disambiguation stubs have nothing to lay out and are left as they are.
    """
    if "used for disambiguation" in body:
        return body
    cell = re.search(r'<div class="wd-cell" markdown>\n(.*?)\n</div>', body, re.S)
    if not cell:
        return body
    head = re.search(r"^(#{1,6})[ \t]+\S", cell.group(1), re.M)
    if not head:
        return body
    sub = "#" * min(6, len(head.group(1)) + 1)
    short = title.split(",")[0].strip().split()[0]

    label = re.compile(r"^\*\*(?P<name>[^*]+?)(?P<cin>:?)\*\*(?P<cout>:?)"
                       r"[ \t]*(?P<br><br>)?[ \t]*(?P<rest>.*)$")
    listed = re.compile(r"^- \*\*(?P<name>[^*]+?):?\*\*:?[ \t]*(?P<rest>.*)$")

    out, pend = [], []
    state = {"kind": None, "tenets": False}

    def flush():
        if pend:
            out.append(("\n" if state["kind"] == "stat" else "\n\n").join(pend))
            del pend[:]

    def emit(kind, text):
        if kind != state["kind"]:
            flush()
        state["kind"] = kind
        if kind in ("stat", "tenet"):
            pend.append(text)
        else:
            out.append(text)
            state["kind"] = None

    def stat(name, value):
        if name == "Domain" and "," in value:
            name = "Domains"
        emit("stat", "- **%s**: %s" % (name, value))

    blocks = []
    for block in re.split(r"\n[ \t]*\n", cell.group(1).strip("\n")):
        # A heading with its first line of content straight under it and no
        # blank line between is two blocks, not one. Vaylen's Overview runs
        # straight into his Domains, and read as one block the Domains were
        # carried along with the heading and never became part of the list.
        top = block.split("\n", 1)
        if re.match(r"^#{1,6}[ \t]", top[0]) and len(top) > 1:
            blocks.extend(top)
        else:
            blocks.append(block)
    for block in blocks:
        lines = block.split("\n")
        first = lines[0]

        if re.match(r"^#{1,6}[ \t]", first):
            emit("block", block)
            continue

        if all(listed.match(l) for l in lines):
            for l in lines:
                m = listed.match(l)
                stat(m.group("name").strip(), m.group("rest").strip())
            continue

        m = label.match(first)
        if m and (m.group("cin") or m.group("cout") or m.group("br")
                  or not m.group("rest").strip()):
            name = m.group("name").strip()
            rest = " ".join(x.strip() for x in [m.group("rest")] + lines[1:]
                            if x.strip())
            inline = bool(m.group("rest").strip()) and not m.group("br")

            if name.startswith("Tenets"):
                state["tenets"] = True
                if not name.lower().endswith(" " + short.lower()):
                    name = "Tenets of " + short
                emit("block", sub + " " + name)
                if rest:
                    emit("block", rest)
                continue
            if inline and name in DEITY_STATS and not state["tenets"]:
                if name == "Name" and rest.lower() == title.lower():
                    continue
                stat(name, rest)
                continue
            if inline and state["tenets"] and name not in DEITY_SECTIONS:
                emit("tenet", "- **%s**: %s" % (name, rest))
                continue
            state["tenets"] = False
            emit("block", sub + " " + name)
            if rest:
                emit("block", rest)
            continue

        if state["tenets"]:
            # "*Seek knowledge and harmony with the cosmos*<br>" and the tenet
            # on the next line; or "*Embrace the Night: Selene encourages...*"
            it = re.match(r"^\*(?P<name>[^*]+?)\*[ \t]*<br>[ \t]*$", first)
            if it and len(lines) > 1:
                emit("tenet", "- **%s**: %s" % (
                    it.group("name").strip(), " ".join(l.strip() for l in lines[1:])))
                continue
            it = re.match(r"^\*(?P<name>[^*:]+):[ \t]*(?P<rest>[^*]+)\*$", block)
            if it:
                emit("tenet", "- **%s**: %s" % (
                    it.group("name").strip(), it.group("rest").strip()))
                continue

        emit("block", block)
    flush()

    # The blank lines inside the card's opening and closing tags go back where
    # every other card on the site keeps them.
    body = (body[:cell.start(1)] + "\n" + "\n\n".join(out) + "\n"
            + body[cell.end(1):])

    # A sidebar of pictures is boxed, whether it holds one picture or two.
    body = body.replace('<div class="wd-cell wd-plain" markdown>',
                        '<div class="wd-cell wd-aside" markdown>')
    # Its captions name the god the way the page does.
    body = re.sub(r"^\*([^*\n]+)\*$",
                  lambda m: ("*%s*" % title) if m.group(1).lower() == title.lower()
                  else m.group(0), body, flags=re.M)
    if re.search(r"^#{1,6} Unholy Symbol$", body, re.M):
        body = body.replace("*Holy Symbol of ", "*Unholy Symbol of ")
    return body


def apply_edits(slug, text):
    """Make the small corrections listed for this page.

    An edit may name the section it belongs in, which runs from that heading to
    the next one at the same level or above. A page that repeats a structure -
    The Index runs the alphabet four times - needs that, or the same three
    characters name four different places on it.
    """
    for after, old, new in EDITS.get(slug, []):
        lo, hi = 0, len(text)
        if after:
            lo = text.find(after)
            if lo < 0:
                TODO.append((slug, "edit anchor %r not found" % after[:30]))
                continue
            level = len(after) - len(after.lstrip("#"))
            nxt = re.compile(r"^#{1,%d}[ \t]" % level, re.M).search(text, lo + len(after))
            hi = nxt.start() if nxt else len(text)
        n = text.count(old, lo, hi)
        if n != 1:
            TODO.append((slug, "edit %r matched %d times" % (old[:30], n)))
            continue
        cut = text.index(old, lo, hi)
        text = text[:cut] + new + text[cut + len(old):]
    return text


def heading_levels(s):
    """Close the gaps in a page's heading levels.

    Eleven pages jumped from # straight to ### or ####, because the levels came
    from however deep the original author happened to nest that section rather
    than from the structure of the page. The levels a page uses are remapped
    onto consecutive ones, keeping their order and their nesting.

    A page using one level throughout is remapped too, onto the first. Deepfolk
    wrote every one of its sections at level four and nothing else at all, so
    there was no gap to close and it was left alone - and then the page's name
    arrived above them at level one, four levels up from its own headings.
    """
    used = sorted({len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", s, re.M)})
    if not used:
        return s
    rank = {lv: i + 1 for i, lv in enumerate(used)}
    if all(lv == r for lv, r in rank.items()):
        return s
    return re.sub(r"^(#{1,6})(\s)",
                  lambda m: "#" * rank[len(m.group(1))] + m.group(2), s, flags=re.M)


def table_notes(s):
    """Mark the note that belongs to the table above it.

    A table's notes were written under it as ordinary paragraphs, so they came
    out as loose text sitting below a bordered table with nothing tying the two
    together. Marked here and moved into the table itself, as a full-width cell
    across its foot, by hooks/tablenotes.py.

    Only three shapes count as a note, and every line of the run has to be one
    of them or none of it is taken: a line opening with an asterisk, which is
    how the wiki writes them; a line opening with a superscript marker, which
    is how it writes the numbered ones; and a short italic line, which is how
    it captions them. Anything else after a table is the next paragraph of the
    article and is left where it is.
    """
    NOTE = re.compile(r"^(?:\\\*|[¹²³⁴⁵⁶⁷⁸⁹⁰])")
    CAPTION = re.compile(r"^\*[^*].{0,200}\*(?:<br>)?$")

    def is_note(ln):
        return bool(NOTE.match(ln) or CAPTION.match(ln))

    lines = s.split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].startswith("|"):
            i += 1
            continue
        while i < len(lines) and lines[i].startswith("|"):
            i += 1
        # Gather the paragraphs under the table for as long as they are notes.
        # A note can be several paragraphs - a caption, then the numbered
        # footnotes - and every one of them has to be marked, or the ones left
        # over stay loose below the table the rest just moved into.
        j = i
        paras = []
        while True:
            k = j
            while k < len(lines) and not lines[k].strip():
                k += 1
            para = []
            while k < len(lines) and lines[k].strip():
                para.append(k)
                k += 1
            if not para or not all(is_note(lines[p]) for p in para):
                break
            paras.append(para)
            j = k
        for para in reversed(paras):
            lines.insert(para[-1] + 1, "{: .wd-table-note }")
        i = j + len(paras)
    return "\n".join(lines)


def stat_line_breaks(s):
    """Put back the line breaks Markdown drops.

    Wikidot renders a single newline inside a paragraph as <br>. Markdown
    folds those lines into one paragraph instead, so anything the wiki wrote
    as a stack of short lines arrived as a run-on sentence:

        **Price (Item Level)**: 2800 gp        Price (Item Level): 2800 gp
        **Body Slot**: Neck             ->     Body Slot: Neck Caster Level:
        **Caster Level**: 5th                  5th ...

    Checked against the live wiki rather than assumed: Orion's "Appearance:"
    renders there as "<strong>Appearance</strong>:<br>" with the prose on the
    next line, and the spell panels break between every stat.

    This is not confined to stat blocks. Items, backgrounds, feats, ship
    weapons, ammunition, the deity pages' Appearance and Backstory labels, and
    weapon category lines are all written as adjacent lines, and all of them
    were folding. Any two adjacent lines that are both ordinary paragraph text
    get the break; headings, lists, tables, HTML, images and code are blocks of
    their own and are left alone.

    Magic items are also put in the wiki's field order while their run is in
    hand, so the rule holds for anything added later.
    """
    lines = s.split("\n")

    # Field order first, so the sort sees the run before it is broken up.
    i = 0
    while i < len(lines):
        if not STAT.match(lines[i]) or lines[i].endswith("<br>"):
            i += 1
            continue
        j = i
        while j < len(lines) and STAT.match(lines[j]) and not lines[j].endswith("<br>"):
            j += 1
        run = [STAT.match(l).groups() for l in lines[i:j]]
        if any(k.strip().lower() == "price (item level)" for k, _ in run):
            run.sort(key=lambda kv: ITEM_ORDER.get(kv[0].strip().lower(), 99))
        # Rebuilt rather than left alone, so that a label written without the
        # space after its colon - "**Type**:Regional" - reads like the rest.
        lines[i:j] = [("**%s**: %s" % (k.strip(), v.strip())).rstrip()
                      for k, v in run]
        i = j

    for i in range(len(lines) - 1):
        if BLOCK_LINE.match(lines[i]) or BLOCK_LINE.match(lines[i + 1]):
            continue
        if not lines[i].endswith("<br>"):
            lines[i] += "<br>"
    return "\n".join(lines)


def spell_cards(s):
    """Find the stat blocks, normalise them, and put each in a spell card."""
    lines = s.split("\n")
    found = []
    i = 0
    while i < len(lines):
        m = SPELL_HEAD.match(lines[i])
        if m and any(l.startswith("**Level**") for l in lines[i + 1:i + 4]):
            depth = len(m.group(1)) if m.group(1) else 99
            j = i + 1
            while j < len(lines):
                h = re.match(r"^(#{1,6})\s+", lines[j])
                if (h and len(h.group(1)) <= depth) or lines[j].startswith("</div>"):
                    break
                j += 1
            found.append((i, j))
            i = j
            continue
        i += 1

    for start, end in reversed(found):
        block, kind = normalise_spell(lines[start:end])
        while block and not block[-1].strip():
            block.pop()

        # A block that is the whole of its card becomes that card, rather than
        # a second box drawn inside the first.
        a = start - 1
        while a >= 0 and not lines[a].strip():
            a -= 1
        b = end
        while b < len(lines) and not lines[b].strip():
            b += 1
        whole_cell = (
            a >= 0 and 'class="wd-cell' in lines[a]
            and b < len(lines) and lines[b].startswith("</div>")
        )
        if whole_cell:
            lines[a] = lines[a].replace(
                ' markdown>', ' data-wd-kind="%s" markdown>' % kind).replace(
                'class="wd-cell', 'class="wd-cell wd-spell', 1)
            lines[start:end] = block + [""]
        else:
            lines[start:end] = (
                ['<div class="wd-spell" data-wd-kind="%s" markdown>' % kind, ""]
                + block + ["", "</div>", ""])
    return "\n".join(lines)


def main(backup):
    src_dir = os.path.join(backup, "source")
    slugs = [f[:-4] for f in sorted(os.listdir(src_dir))]
    keep = [s for s in slugs
            if not SKIP.match(s)
            and s not in TEMPLATE_ONLY and s not in REMOVED]
    # Link targets are matched by several names, most specific first, because
    # Wikidot links reference pages by slug and by title interchangeably and
    # often omit the category prefix a slug carries ("House of Fabrication"
    # for the page "faction-house-of-fabrication").
    linkmap = {}
    for s in keep:
        for key in slug_keys(s):
            linkmap.setdefault(key, target_path(s))
    # A link to half of a merged page goes to that half's section, not to the
    # top of the page, so "the psionic power" still means the psionic power.
    for part, (merged, anchor) in MERGE_PARTS.items():
        linkmap[norm_slug(part)] = merged + ".md#" + anchor
    for s in keep:
        raw = open(os.path.join(src_dir, s + ".txt"), "rb").read().decode("utf-8", "replace")
        heading = re.search(r"^\+\s+(.+)$", raw, re.M)
        names = []
        if s in TITLES:
            names.append(TITLES[s])
        if heading:
            names.append(re.sub(r"[*_`~\[\]]", "", heading.group(1)).strip())
        m = re.match(r"^([a-z]+)[-_](.+)$", s)
        if m:
            names.append(m.group(2))
        for n in names:
            linkmap.setdefault(norm_slug(n), target_path(s))

    # The spheres take their names from the wiki's own index rather than from
    # their slugs, which had produced "Sphere Cineraexis" for Cineræxis and
    # "Sphere Sanctum Aeternum" for Sanctum Æternum. The Known Spheres page
    # links to every one of them and spells each correctly, so that is the
    # authority; deriving it means a sphere added later is named right without
    # anyone editing a list here.
    index_src = os.path.join(src_dir, "spelljamming-known-spheres.txt")
    if os.path.exists(index_src):
        raw = open(index_src, "rb").read().decode("utf-8", "replace")
        for target, name in re.findall(r"\[\[\[([^\]|]+)\|([^\]]+)\]\]\]", raw):
            t = target.strip()
            if "sphere-" not in t:
                continue
            # The index links one sphere by its display name rather than its
            # slug; match on the normalised form so that one lands too.
            for s in keep:
                if norm_slug(s) == norm_slug(t):
                    TITLES.setdefault(s, "The %s Sphere" % name.strip())
                    # Their own headings disagreed with each other as well as
                    # with the titles - "Aerivagus Sphere", "Custodæ",
                    # "The Sidhe Sphere", "Cineræxis", four spellings of one
                    # idea. The heading takes the title so a sphere is called
                    # the same thing in the tab, the index and on the page.
                    TITLE_HEADING.add(s)
                    break

    imgs = json.load(open(os.path.join(ROOT, "_migration", "images.json"), encoding="utf-8"))
    img_by_url = {e["url"]: e["final"] for e in imgs}

    # Resolved once so the wip flag can be derived from the page source.
    wip_url = next((e["url"] for e in imgs
                    if e["final"] == "shared_under_construction.png"), None)

    tables = {}
    for f in os.listdir(TABLES):
        if f.endswith(".md"):
            tables[f[:-3]] = open(os.path.join(TABLES, f), encoding="utf-8").read()

    # Wipe generated pages; leave img/ and stylesheets/ alone.
    for root, dirs, files in os.walk(DOCS, topdown=False):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), DOCS).replace("\\", "/")
            if rel.startswith(("img/", "stylesheets/")):
                continue
            if f.endswith(".md"):
                os.remove(os.path.join(root, f))
        for d in dirs:
            p = os.path.join(root, d)
            if os.path.relpath(p, DOCS) not in ("img", "stylesheets") and not os.listdir(p):
                os.rmdir(p)

    written = 0
    merged_bodies = {}
    appended = {}
    for slug in keep:
        raw = open(os.path.join(src_dir, slug + ".txt"), "rb").read().decode("utf-8", "replace")
        body = convert(raw, slug, img_by_url, tables, linkmap)
        # Rewrites go in before the title and heading passes, so a rewritten
        # section is held to the same house style as the rest of the page.
        if slug in REWRITES or slug in RECARDS or slug in NEWCARDS:
            body = house_style(
                apply_newcards(slug, apply_recards(slug, apply_rewrites(slug, body))))

        # Half of a merged page: keep the converted body and write nothing.
        # The whole page is assembled once every half has been converted.
        if slug in MERGE_PARTS:
            merged_bodies[slug] = body
            continue

        # Content that belongs at the foot of another page. Held here and
        # appended once that page has been written.
        if slug in APPEND_TO:
            appended.setdefault(APPEND_TO[slug], []).append(body)
            continue

        # Promote the opening heading to the title only when the page has a
        # single top-level heading. A page like the glossary uses "# A", "# B"
        # as section markers; taking the first would title the page "A".
        title = None
        h1s = re.findall(r"^#\s+(.+)$", body, re.M)
        if len(h1s) == 1:
            m = re.search(r"^#\s+(.+)$", body, re.M)
            candidate = m.group(1).strip()
            plain = re.sub(r"[*_`~]", "", candidate).strip().lower()
            if body[:m.start()].strip() == "" and plain not in GENERIC_HEADINGS:
                title = candidate
                body = (body[:m.start()] + body[m.end():]).strip() + "\n"
        if not title:
            title = title_from(slug)
        # Headings carry inline markup; a title is plain text.
        title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)
        title = re.sub(r"[*_`~]", "", title)
        title = re.sub(r"^\s*Name\s*:\s*", "", title, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" :-")
        title = title.replace('"', "'")
        if not title:
            title = title_from(slug)
        title = TITLES.get(slug, title)
        # A title built from a slug inherits the slug's ASCII. The URL keeps
        # the "ae" - a URL has no business carrying an æ - but the name the
        # reader sees is spelled the way the wiki spells it everywhere else.
        title = re.sub(r"\bAntaera(n?)\b", r"Antæra\1", title)

        # A god's page is named for the god, and this wiki writes that name in
        # full: "Ukrol, Patron Deity of Humanity". The slug carries only the
        # short form of it, and under the pantheon it carried the shelf the
        # page sits on as well - "pantheon-deity-aezhera", "pantheon-mortal-
        # leonis" - which came out as the titles "Deity Aezhera" and "Mortal
        # Leonis". Neither is a name.
        #
        # The opening heading has the full form on every one of these pages, so
        # it becomes the title, and the card it was heading becomes the page's
        # overview like every other opening card. A comma is required: it is
        # what separates the name from the epithet, and a heading without one
        # is not the name-and-title form this is reading.
        if (slug not in TITLES
                and target_path(slug).split("/")[0] in DEITY_FOLDERS):
            m = re.search(r"^#{1,6}\s+(.+)$", body, re.M)
            if m:
                name = re.sub(r"[*_`~]", "", m.group(1)).strip()
                name = re.sub(r"^\s*Name\s*:\s*", "", name, flags=re.I).strip()
                if "," in name:
                    title = name
                else:
                    TODO.append((slug, "no name and title in the opening heading"))

        # A page whose opening heading disagrees with its title takes the
        # title, so the page is called one thing throughout.
        if slug in TITLE_HEADING:
            m = re.search(r"^#\s+(.+)$", body, re.M)
            if m:
                body = body[:m.start()] + "# " + title + body[m.end():]

        # The page's name is a card of its own now, at the top of the page, so
        # the opening heading is free to label the section it holds instead of
        # naming the page over again. A heading that says the page's name, or
        # says "Description" or "Introduction", is the page's overview - which
        # is what most of them called it before the name was moved into them -
        # so that is what it is called, and all of them call it the same thing.
        #
        # Only the leading heading is touched. "Overview" further down a page
        # is a section among others and is doing its job.
        m = re.search(r"^(#{1,6})\s+(.+)$", body, re.M)
        if m:
            plain = re.sub(r"[*_`~]", "", m.group(2)).strip()
            # Two of the gods' pages label the heading "Name:" before giving
            # it, which is the same heading with a word in front of it.
            plain = re.sub(r"^\s*Name\s*:\s*", "", plain, flags=re.I).strip()
            if (plain.lower() in GENERIC_HEADINGS
                    or plain.lower() == title.lower()):
                body = body[:m.start()] + m.group(1) + " Overview" + body[m.end():]

        # A disambiguation stub gets the link it was missing, put inside its
        # card so the page reads as a signpost rather than a dead end.
        if slug in DISAMBIGUATION:
            dest = DISAMBIGUATION[slug]
            rel = os.path.relpath(target_path(dest),
                                  os.path.dirname(target_path(slug)) or ".")
            link = "\nSee **[%s](%s)**.\n" % (
                TITLES.get(dest, title_from(dest)), rel.replace("\\", "/"))
            # Inside the card, not after it: the stub is one card, and a line
            # appended to the page would sit on the sky below it.
            cut = body.rstrip().rfind("\n</div>\n</div>")
            body = (body[:cut] + "\n" + link + body[cut:]) if cut != -1 else body + link

        # The Index is the hub for the wiki's own indexes, so Archived Pages
        # hangs off it rather than off the sidebar - the sidebar is a flat list
        # by design, and nesting an item under an entry turns that entry into a
        # section header with a duplicate child.
        if slug == "the-index":
            body += (
                "\n\n<div class=\"wd-row\" markdown>\n"
                "<div class=\"wd-cell\" markdown>\n\n"
                "# Archived Pages\n\n"
                "Sections retired from the current setting, kept for reference. "
                "They do not appear in search.\n\n"
                "[Browse archived pages](archived.md)\n\n"
                "</div>\n</div>\n"
            )

        rel = target_path(slug)

        # Flags are derived from the source, not a hand-kept list: a page is
        # work in progress if it carried the under-construction sign, and
        # archived if it sits in a retired section.
        meta = ['title: "' + title + '"']
        if wip_url and wip_url in raw:
            meta.append("wip: true")
        if rel.split("/")[0] in ARCHIVED_FOLDERS:
            meta.append("archived: true")
            # Honoured natively by Material's search plugin.
            meta.append("search:")
            meta.append("  exclude: true")

        out_abs = os.path.join(DOCS, rel)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        # Last, after the title heading and any injected section: those arrive
        # after the conversion pass and can reopen a gap in the heading levels
        # that pass had just closed.
        if target_path(slug).split("/")[0] in DEITY_FOLDERS:
            body = deity_format(body, title)
        body = apply_edits(slug, title_card(title, heading_levels(body)))
        with open(out_abs, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("---\n" + "\n".join(meta) + "\n---\n\n" + body)
        written += 1

    # Content moved onto the end of another page, added once that page exists.
    for target, bodies in appended.items():
        p = os.path.join(DOCS, target_path(target))
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.rstrip() + "\n\n" + "\n".join(b.strip() for b in bodies) + "\n")

    # Merged pages, assembled from the halves collected above.
    for merged, spec in MERGES.items():
        rel = merged + ".md"
        here = os.path.dirname(rel)
        lead = re.sub(
            r"\[\[\[([^\]|]+)\|([^\]]+)\]\]\]",
            lambda m: "[%s](%s)" % (
                m.group(2),
                os.path.relpath(linkmap[norm_slug(m.group(1))], here or ".")
                  .replace("\\", "/")),
            spec["lead"])
        parts = ['<div class="wd-row" style="--wd-rw: 935px" markdown>',
                 '<div class="wd-cell" markdown>', "",
                 "# Overview", "", lead, "", "</div>", "</div>", ""]
        for label, part in spec["parts"]:
            half = merged_bodies[part]
            # The variants drop a level to sit under their form's heading. The
            # label gets a row of its own rather than going inside the first
            # card - those cards are spell cards, and a section heading is not
            # part of the spell.
            half = re.sub(r"^##(?=\s)", "###", half, flags=re.M)
            # No heading for the group: each card already says whether it is a
            # spell or a psionic power, and a divider saying it again is the
            # same label twice. The anchor moves onto the first card of the
            # group so the links that meant this half still land on it.
            anchor = label.lower().replace(" ", "-")
            half = half.replace('<div class="wd-row"',
                                '<div id="%s" class="wd-row"' % anchor, 1)
            parts.append(half.rstrip() + "\n")
        with open(os.path.join(DOCS, rel), "w", encoding="utf-8", newline="\n") as fh:
            # The halves were levelled separately and then demoted a step when
            # they were joined, so the levels are closed up once more here.
            fh.write('---\ntitle: "' + spec["title"] + '"\n---\n\n'
                     + title_card(spec["title"],
                                  heading_levels("\n".join(parts))))
        written += 1

    # Pages with no Wikidot source. They have to be written here because this
    # script clears docs/ on every run, so anything hand-placed there is lost.
    with open(os.path.join(DOCS, "archived.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            '---\ntitle: "Archived Pages"\n---\n\n'
            + title_card("Archived Pages", "")
            + "<!-- ARCHIVED-INDEX -->\n"
        )
    written += 1

    print("pages written : %d  (skipped %d system pages)" % (written, len(slugs) - len(keep)))
    print("TODO markers  : %d" % len(TODO))
    for what, n in Counter(w for _, w in TODO).most_common():
        print("    %3d  %s" % (n, what))


if __name__ == "__main__":
    main(sys.argv[1])
