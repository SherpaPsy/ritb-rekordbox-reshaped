"""Resolve Rekordbox tracks with no label (Tracks.label_id IS NULL) against
the OneNote label-history index built by core/onenote_index.py.

Two-tier matching, per project decision:
  - Exact (artist, title) match against OneNote history -> applied directly,
    updating Tracks.label_id in place (creating the Label row if needed).
  - No exact match, but the same artist appears elsewhere in OneNote history
    -> collected as a ranked suggestion for manual review, not auto-applied.

Run directly to resolve everything and write a report of what happened:
    poetry run python -m core.label_resolver <rekordbox_sqlite_db> [onenote_index_db]
"""
import os
import re
import sqlite3
import sys
from collections import Counter

from core.rekordbox_extractor import get_or_create

NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")

DEFAULT_ONENOTE_DB_PATH = os.path.join(os.path.dirname(__file__), "secrets", "onenote_index.db")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "label_resolution.txt")


def normalize(text):
    """Fold casing/punctuation/whitespace differences for matching.

    Rekordbox and hand-typed OneNote text disagree on things like curly vs
    straight apostrophes and extra spacing - comparing on a stripped-down
    alphanumeric key avoids missing matches over that noise.
    """
    return NORMALIZE_PATTERN.sub("", (text or "").lower())


def resolve(rb_conn, onenote_conn):
    """Resolve unlabeled tracks in rb_conn against onenote_conn's index.

    Returns {"applied": [...], "suggested": [...], "unmatched": [...]}:
      - applied: (track_id, title, label) tracks updated with an exact match.
      - suggested: (track_id, title, artist_text, [(label, count), ...]) tracks
        with no exact title match, ranked by how often that label shows up
        for the same artist elsewhere in OneNote history.
      - unmatched: (track_id, title, artist_text) tracks with no OneNote
        history for either the exact title or the artist.
    """
    onenote_tracks = onenote_conn.execute("SELECT id, title, label FROM OneNoteTracks").fetchall()
    label_by_id = {oid: label for oid, _, label in onenote_tracks}

    title_index = {}
    for oid, title, _ in onenote_tracks:
        title_index.setdefault(normalize(title), []).append(oid)

    artists_by_track = {}
    artist_label_counts = {}  # normalized artist -> Counter(label -> count)
    for oid, artist in onenote_conn.execute("SELECT onenote_track_id, artist FROM OneNoteTrackArtists"):
        norm_artist = normalize(artist)
        artists_by_track.setdefault(oid, set()).add(norm_artist)
        label = label_by_id.get(oid)
        if label:
            artist_label_counts.setdefault(norm_artist, Counter())[label] += 1

    unlabeled = rb_conn.execute(
        """SELECT t.id, t.track_title, GROUP_CONCAT(a.name, '||')
           FROM Tracks t
           LEFT JOIN Track_Artists ta ON ta.track_id = t.id AND ta.role = 'artist'
           LEFT JOIN Artists a ON a.id = ta.artist_id
           WHERE t.label_id IS NULL
           GROUP BY t.id"""
    ).fetchall()

    applied, suggested, unmatched = [], [], []
    label_cache = {}

    for track_id, title, artist_text in unlabeled:
        norm_title = normalize(title)
        norm_artists = {normalize(a) for a in (artist_text or "").split("||") if a.strip()}

        matched_label = next(
            (
                label_by_id[oid]
                for oid in title_index.get(norm_title, [])
                if artists_by_track.get(oid, set()) & norm_artists
            ),
            None,
        )

        if matched_label:
            label_id = get_or_create(rb_conn, label_cache, "Labels", matched_label)
            rb_conn.execute("UPDATE Tracks SET label_id = ? WHERE id = ?", (label_id, track_id))
            applied.append((track_id, title, matched_label))
            continue

        candidate_labels = Counter()
        for norm_artist in norm_artists:
            candidate_labels.update(artist_label_counts.get(norm_artist, {}))

        if candidate_labels:
            suggested.append((track_id, title, artist_text, candidate_labels.most_common()))
        else:
            unmatched.append((track_id, title, artist_text))

    rb_conn.commit()
    return {"applied": applied, "suggested": suggested, "unmatched": unmatched}


def write_report(result, path):
    """Write a plain-text summary of what resolve() did.

    Mirrors core/rekordbox_extractor.write_review_report's style/location
    convention (reports/, gitignored).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"Labels applied from an exact OneNote match ({len(result['applied'])})\n")
        f.write("=" * 60 + "\n")
        for track_id, title, label in result["applied"]:
            f.write(f"[{track_id}] {title} -> {label}\n")

        f.write("\n")
        f.write(f"Suggested labels from same-artist history, needs manual review ({len(result['suggested'])})\n")
        f.write("=" * 60 + "\n")
        for track_id, title, artist_text, ranked_labels in result["suggested"]:
            options = ", ".join(f"{label} ({count}x)" for label, count in ranked_labels)
            f.write(f"[{track_id}] {title} - {artist_text}\n")
            f.write(f"    candidates: {options}\n\n")

        f.write("\n")
        f.write(f"Still unmatched, no OneNote history for this artist or title ({len(result['unmatched'])})\n")
        f.write("=" * 60 + "\n")
        f.write("Not included in detail - too many to fix by hand.\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m core.label_resolver <rekordbox_sqlite_db> [onenote_index_db]")
        sys.exit(1)

    rb_db_path = sys.argv[1]
    onenote_db_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ONENOTE_DB_PATH

    rb_conn = sqlite3.connect(rb_db_path)
    rb_conn.execute("PRAGMA foreign_keys = ON")
    onenote_conn = sqlite3.connect(onenote_db_path)
    try:
        report = resolve(rb_conn, onenote_conn)
    finally:
        rb_conn.close()
        onenote_conn.close()

    write_report(report, REPORT_PATH)
    print(
        f"Applied {len(report['applied'])} exact matches, "
        f"{len(report['suggested'])} suggestions for review, "
        f"{len(report['unmatched'])} still unmatched -> {REPORT_PATH}"
    )
