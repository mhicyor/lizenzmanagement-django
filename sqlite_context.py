from demo.database import connect as demo_connection
"""Kleine, einheitliche Lebenszyklusverwaltung fuer SQLite-Verbindungen."""

import sqlite3
from contextlib import contextmanager
from os import PathLike
from typing import Iterator


@contextmanager
def sqlite_verbindung(
    datenbank_datei: str | bytes | PathLike[str] | PathLike[bytes],
) -> Iterator[sqlite3.Connection]:
    """Oeffnet eine Transaktion und schliesst die Verbindung garantiert.

    Der eingebaute Kontextmanager von ``sqlite3.Connection`` bestaetigt oder
    verwirft zwar eine Transaktion, schliesst die Verbindung aber nicht. Diese
    kleine Kapselung erhaelt genau dieses Transaktionsverhalten und ergaenzt
    das verlaessliche Schliessen im ``finally``-Block.
    """
    verbindung = demo_connection(datenbank_datei)
    # SQLite aktiviert Fremdschluesselpruefungen nicht automatisch pro
    # Verbindung. Die zentrale Kapselung stellt sicher, dass jede darueber
    # geoeffnete Verbindung dieselben Integritaetsregeln verwendet.
    verbindung.execute("PRAGMA foreign_keys = ON")

    try:
        with verbindung:
            yield verbindung
    finally:
        verbindung.close()
