import os
print(">>> loading rekordbox_reader")
DEFAULT_DB_PATH = os.path.join(os.environ.get("APPDATA", ""), "Pioneer", "rekordbox", "master.db")

def auto_detect_rekordbox_db():
    print(f"Attempting to auto-detect Rekordbox DB at: {DEFAULT_DB_PATH}")
    return DEFAULT_DB_PATH if os.path.isfile(DEFAULT_DB_PATH) else ""

def is_valid_rekordbox_db(path):
    return path and os.path.isfile(path)
