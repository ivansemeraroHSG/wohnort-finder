"""
build_db.py – baut die SQLite-Datenbank aus den Rohdaten (Arbeitspaket 1).

Verantwortlich: <Name eintragen>

Ausführen (im Projektordner):
    python scripts/build_db.py

Liest die Dateien aus data/raw/, bereinigt sie und schreibt die Tabellen
gemeinden, steuern, mieten, bewertungen und pendel_cache in data/wohnort.db.
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "wohnort.db"


def create_empty_tables(con: sqlite3.Connection) -> None:
    """Legt die Tabellen an, die die App während der Nutzung füllt."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS bewertungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sitzung TEXT,
            bfs_nr INTEGER,
            gefaellt INTEGER,
            zeitpunkt TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS pendel_cache (
            bfs_nr INTEGER,
            ziel TEXT,
            minuten REAL,
            abgefragt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bfs_nr, ziel)
        )""")


def main() -> None:
    """Baut die ganze Datenbank neu auf."""
    con = sqlite3.connect(DB_PATH)
    # TODO (AP 1): Gemeinden, Steuern und Mieten aus RAW einlesen, bereinigen, mit to_sql schreiben
    create_empty_tables(con)
    con.commit()
    con.close()
    print(f"Datenbank erstellt: {DB_PATH}")


if __name__ == "__main__":
    main()
