"""Build the OneNote label-history index (sql/onenote_schema.sql) used by
core/label_resolver.py to fill in missing Rekordbox labels.

Pulls every dated setlist page across all of "John's Notebook"'s yearly
sections, parses out (title, artist(s), label) triplets and writes them to
a fresh sqlite db, kept separate from the Rekordbox-derived db (see memory/
onenote-graph-integration for why: it's a rebuildable lookup index, not
part of the Rekordbox data model).

Run directly to (re)build the index:
    poetry run python -m core.onenote_index [output_db_path]
"""
import os
import sqlite3
import sys

import requests

from core.onenote_auth import get_access_token
from core.onenote_client import PullAborted, get_page_content, list_section_pages
from core.onenote_parser import is_set_page_title, parse_page_date, parse_page_tracks

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "onenote_schema.sql")
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "secrets", "onenote_index.db")

# "John's Notebook" - one section per year of weekly setlist pages. Naming
# shifted from "Music Stuff" to "Mixes" after 2022. "2022 BC" (the other 2022
# section named in memory/onenote-graph-integration) turned out on inspection
# to hold unrelated pages ("Ross", "Orders ") - not setlists, so it's left
# out here.
SECTIONS = [
    ("2021 Music Stuff", "0-661EC6E34A72A5E2!113"),
    ("2022 Music Stuff", "0-661EC6E34A72A5E2!80278"),
    ("2023 Music Stuff", "0-661EC6E34A72A5E2!82495"),
    ("2024 Mixes", "0-661EC6E34A72A5E2!152649"),
    ("2025 Mixes", "0-661EC6E34A72A5E2!279008"),
    ("2026 Mixes", "0-661EC6E34A72A5E2!s7dc524c0930047a8b0cbe5ecaba24e3a"),
]


def init_schema(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())


def build_index(db_path=DEFAULT_DB_PATH, force_refresh_token=False):
    """Sign in, pull every dated page across SECTIONS, and (re)build the index db.

    Pass force_refresh_token=True to re-run after a run that aborted with a
    "token needs a forced refresh" warning (see onenote_client.TokenRevoked)
    - otherwise get_access_token's local cache has no way to know the
    previous token was revoked server-side and would just hand back the same
    bad one.

    Returns a list of warning strings for pages whose paragraphs didn't
    cleanly group into title/artist/label triplets - worth a manual look in
    OneNote, but the rest of the page is still indexed.
    """
    token = get_access_token(force_refresh=force_refresh_token)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)  # rebuilt from scratch each run - it's a derived index
    conn = sqlite3.connect(db_path)
    init_schema(conn)

    warnings = []
    page_count = 0
    track_count = 0
    aborted = False

    try:
        for section_name, section_id in SECTIONS:
            for page in list_section_pages(token, section_id):
                if not is_set_page_title(page["title"]):
                    continue  # not a dated set page - e.g. "Best of mix", "Songs to fix"

                set_date = parse_page_date(page["title"])
                if set_date is None:
                    warnings.append(
                        f"{page['title']!r} ({section_name}): looks like a dated set page but the "
                        f"date didn't parse cleanly (typo?) - indexed anyway with no set_date"
                    )

                try:
                    content = get_page_content(token, page["id"])
                except PullAborted:
                    # Sustained rate limiting or a revoked token - not a
                    # one-off page problem. Stop the whole run rather than
                    # burn through the rest of the pages hitting it too (see
                    # RateLimited/TokenRevoked's docstrings). Whatever was
                    # indexed before this point is still saved below.
                    raise
                except requests.exceptions.RequestException as exc:
                    # A genuinely one-off failure on this page - skip it and
                    # keep going rather than lose everything already pulled.
                    warnings.append(f"{page['title']!r} ({section_name}): failed to fetch page content ({exc})")
                    continue

                tracks, warning = parse_page_tracks(content, page["title"], section_name)
                if warning:
                    warnings.append(warning)

                page_count += 1
                for track in tracks:
                    track_id = conn.execute(
                        """INSERT INTO OneNoteTracks (title, raw_artist_text, label, set_date, page_title, section_name)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (track["title"], track["artist_text"], track["label"], set_date, page["title"], section_name),
                    ).lastrowid
                    for artist in track["artist_text"].split(","):
                        artist = artist.strip()
                        if artist:
                            conn.execute(
                                "INSERT INTO OneNoteTrackArtists (onenote_track_id, artist) VALUES (?, ?)",
                                (track_id, artist),
                            )
                    track_count += 1
    except PullAborted as exc:
        aborted = True
        warnings.append(f"aborted early: {exc}")

    conn.commit()
    conn.close()

    status = "Partially indexed (aborted early)" if aborted else "Indexed"
    print(f"{status} {track_count} tracks from {page_count} pages across {len(SECTIONS)} sections -> {db_path}")
    for warning in warnings:
        print(f"  warning: {warning}")
    if aborted:
        print(
            "  stopped early - see the last warning above. If it was rate limiting, wait a while "
            "(e.g. 30-60 min) before re-running; if the token was revoked, re-run with "
            "force_refresh_token=True (or `python -m core.onenote_index --refresh-token`)"
        )

    return warnings


if __name__ == "__main__":
    args = sys.argv[1:]
    refresh_token = "--refresh-token" in args
    positional = [a for a in args if a != "--refresh-token"]
    out_path = positional[0] if positional else DEFAULT_DB_PATH
    build_index(out_path, force_refresh_token=refresh_token)
