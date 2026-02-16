CREATE TABLE Artists (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  soundcloud TEXT,
  tiktok TEXT,
  instagram TEXT,
  facebook TEXT
);

CREATE TABLE Labels (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  soundcloud TEXT,
  tiktok TEXT,
  instagram TEXT,
  facebook TEXT
);

CREATE TABLE LabelOwners (
  label_id INTEGER NOT NULL,
  artist_id INTEGER NOT NULL,
  PRIMARY KEY (label_id, artist_id),
  FOREIGN KEY (label_id) REFERENCES Labels(id),
  FOREIGN KEY (artist_id) REFERENCES Artists(id)
);

CREATE TABLE Sets (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  date DATE
);

CREATE TABLE Tracks (
  id INTEGER PRIMARY KEY,
  track_title TEXT NOT NULL,
  version TEXT,
  label TEXT NOT NULL,
  artist TEXT NOT NULL,
  album_name TEXT,
  date DATE,
  tempo REAL,
  key TEXT,
  genre TEXT
);

CREATE TABLE Set_Tracks (
  set_id INTEGER NOT NULL,
  track_number INTEGER NOT NULL,
  track_id INTEGER NOT NULL,
  PRIMARY KEY (set_id, track_number),
  FOREIGN KEY (set_id) REFERENCES Sets(id),
  FOREIGN KEY (track_id) REFERENCES Tracks(id)
);