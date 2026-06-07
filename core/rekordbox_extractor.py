import os
import re
import sqlite3

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdSongPlaylist

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")

# Matches a single, non-nested trailing "[Label]" or "[Label Year]" tag, e.g.
# "Forgiven [Future Avenue]" or "Utopia (Original Mix) [All Day I Dream 2023]".
# The [^\[\]] restriction stops it from spanning across titles that legitimately
# contain their own bracket pairs, e.g. "Song [Subtitle] Feat. X [WhiteLabel 2023]".
LABEL_TAG_PATTERN = re.compile(r"\[([^\[\]]+?)(?:\s+(\d{4}))?\]\s*$")

# Bracket content that reads as a credit rather than a label, e.g.
# "[Feat. Michele Adamson]" or "[Jozif voxatron remix]" - these are part of the
# real title, not your [Label] tagging convention.
CREDIT_LIKE_PATTERN = re.compile(r"\bfeat\b|\bfeat\.|\bfeaturing\b|\bremix\b", re.I)


def parse_title(title):
    """Split a deliberate trailing [Label]/[Label Year] tag off a track title.

    Returns (title, label, flagged) where `flagged` is the raw bracket text when
    it looked like a tag but read as a credit (feat./remix) rather than a label -
    in that case the title is returned unchanged and should be reviewed manually.
    """
    match = LABEL_TAG_PATTERN.search(title or "")
    if not match:
        return title, None, None

    bracket_text = match.group(1).strip()
    if CREDIT_LIKE_PATTERN.search(bracket_text):
        return title, None, bracket_text

    return title[:match.start()].rstrip(), bracket_text, None


def init_schema(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())


def get_or_create(conn, cache, table, name):
    """Look up or insert a name, matching case/whitespace-insensitively.

    Rekordbox stores the same artist/label under inconsistent casing or stray
    whitespace (e.g. "Blusoul" vs "BLUSOUL"). Comparing on a normalized key
    folds these into one row, keeping whichever spelling is encountered first
    as the canonical display name.
    """
    if not name:
        return None
    name = name.strip()
    key = name.lower()
    if key in cache:
        return cache[key]
    row = conn.execute(f"SELECT id FROM {table} WHERE LOWER(TRIM(name)) = ?", (key,)).fetchone()
    if row is None:
        row_id = conn.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,)).lastrowid
    else:
        row_id = row[0]
    cache[key] = row_id
    return row_id


def link_track_artist(conn, track_id, artist_id, role):
    if artist_id is None:
        return
    conn.execute(
        "INSERT OR IGNORE INTO Track_Artists (track_id, artist_id, role) VALUES (?, ?, ?)",
        (track_id, artist_id, role),
    )


def import_track(conn, caches, content, unresolved_labels, review_titles):
    rb_id = content.ID
    if rb_id in caches["tracks"]:
        return caches["tracks"][rb_id]

    title, bracket_label, flagged = parse_title(content.Title)
    if flagged:
        review_titles.append((rb_id, content.Title, f"bracket reads as a credit, not a label: {flagged!r}"))
    elif "[" in title or "]" in title:
        review_titles.append((rb_id, content.Title, "title still contains brackets after parsing"))

    label_name = bracket_label or (content.Label.Name if content.Label else None)
    label_id = get_or_create(conn, caches["labels"], "Labels", label_name)
    if label_id is None:
        unresolved_labels.append((rb_id, content.Title))

    track_id = conn.execute(
        """INSERT INTO Tracks (track_title, version, label_id, album_name, date, tempo, key, genre)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            title,
            None,
            label_id,
            content.Album.Name if content.Album else None,
            content.ReleaseDate or content.StockDate or None,
            content.BPM / 100 if content.BPM else None,
            content.Key.ScaleName if content.Key else None,
            content.Genre.Name if content.Genre else None,
        ),
    ).lastrowid
    caches["tracks"][rb_id] = track_id

    artist_id = get_or_create(conn, caches["artists"], "Artists", content.Artist.Name) if content.Artist else None
    remixer_id = get_or_create(conn, caches["artists"], "Artists", content.Remixer.Name) if content.Remixer else None
    link_track_artist(conn, track_id, artist_id, "artist")
    link_track_artist(conn, track_id, remixer_id, "remixer")

    return track_id


def extract(sqlite_db_path, rekordbox_db_path=None):
    """Walk Rekordbox playlists and populate a fresh SQLite db using sql/schema.sql.

    Only tracks that appear in at least one (non-folder) playlist are imported.

    Returns a dict with two review lists:
      - "unresolved_labels": (rekordbox_track_id, title) where no label could be
        found from either a [Label] title tag or Rekordbox's Label field.
      - "review_titles": (rekordbox_track_id, title, reason) for titles whose
        bracket tagging didn't fit the [Label]/[Label Year] convention cleanly -
        e.g. a bracket that reads as a feat./remix credit rather than a label,
        or a title that still contains brackets after parsing (duplicated tags,
        years placed outside the brackets, label names that themselves contain
        brackets, corrupted/duplicated text, etc). Worth a manual look.
    """
    rb = Rekordbox6Database(rekordbox_db_path) if rekordbox_db_path else Rekordbox6Database()
    conn = sqlite3.connect(sqlite_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)

    caches = {"artists": {}, "labels": {}, "tracks": {}}
    unresolved_labels = []
    review_titles = []

    try:
        for playlist in rb.get_playlist():
            if playlist.is_folder:
                continue

            songs = (
                rb.session.query(DjmdSongPlaylist)
                .filter_by(PlaylistID=playlist.ID)
                .order_by(DjmdSongPlaylist.TrackNo)
            )
            songs = list(songs)
            if not songs:
                continue

            set_id = conn.execute(
                "INSERT INTO Sets (title, date) VALUES (?, ?)", (playlist.Name, None)
            ).lastrowid

            for song in songs:
                if song.Content is None:
                    continue
                track_id = import_track(conn, caches, song.Content, unresolved_labels, review_titles)
                conn.execute(
                    "INSERT OR IGNORE INTO Set_Tracks (set_id, track_number, track_id) VALUES (?, ?, ?)",
                    (set_id, song.TrackNo, track_id),
                )

        conn.commit()
    finally:
        conn.close()
        rb.session.close()

    return {"unresolved_labels": unresolved_labels, "review_titles": review_titles}


def write_review_report(report, path):
    """Write the actionable review_titles list to a plain-text file.

    These are the tracks worth fixing at the source (in Rekordbox, since that's
    what this extractor reads from) - malformed [Label Year] tags, brackets that
    read as credits rather than labels, etc. Each line includes the Rekordbox
    track ID so the track can be found again via search.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"Titles to review in Rekordbox ({len(report['review_titles'])})\n")
        f.write("=" * 60 + "\n\n")
        for rb_id, title, reason in report["review_titles"]:
            f.write(f"[{rb_id}] {title}\n")
            f.write(f"    reason: {reason}\n\n")

        f.write("\n")
        f.write(f"Tracks with no resolvable label ({len(report['unresolved_labels'])})\n")
        f.write("=" * 60 + "\n")
        f.write("Not included in detail - too many to fix by hand. This is the\n")
        f.write("candidate list for a future external label-lookup feature.\n")
