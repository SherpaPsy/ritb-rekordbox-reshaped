-- Separate index of label history parsed from OneNote setlist pages, used to
-- resolve missing Labels on Rekordbox tracks that have no [Label] tag or
-- Rekordbox Label field (see core/label_resolver.py). Deliberately kept apart
-- from sql/schema.sql: this is a disposable, rebuildable lookup index, not
-- part of the Rekordbox-derived data model.

CREATE TABLE OneNoteTracks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  raw_artist_text TEXT NOT NULL,
  label TEXT NOT NULL,
  set_date DATE,
  page_title TEXT NOT NULL,
  section_name TEXT NOT NULL
);

-- One row per artist on a track: OneNote's artist line lists multiple artists
-- comma-separated (e.g. "Wayward Brothers, Arina Alba"), and same-artist
-- fallback matching needs to query a single artist name at a time.
CREATE TABLE OneNoteTrackArtists (
  onenote_track_id INTEGER NOT NULL,
  artist TEXT NOT NULL,
  FOREIGN KEY (onenote_track_id) REFERENCES OneNoteTracks(id)
);

CREATE INDEX idx_onenote_tracks_title ON OneNoteTracks(title COLLATE NOCASE);
CREATE INDEX idx_onenote_track_artists_artist ON OneNoteTrackArtists(artist COLLATE NOCASE);
CREATE INDEX idx_onenote_track_artists_track ON OneNoteTrackArtists(onenote_track_id);
