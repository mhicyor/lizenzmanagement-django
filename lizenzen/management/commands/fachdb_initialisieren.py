"""Reproduzierbarer Bootstrap der separaten SQLite-Fachdatenbank."""

import os
import sqlite3
from contextlib import closing

from django.core.management.base import BaseCommand, CommandError

import database


class Command(BaseCommand):
    help = (
        "Legt die separate SQLite-Fachdatenbank an beziehungsweise "
        "ergaenzt ein vorhandenes Schema und prueft anschliessend "
        "dessen Integritaet."
    )

    def handle(self, *args, **options):
        try:
            database.datenbank_erstellen()

            with closing(database.verbindung_oeffnen()) as verbindung:
                fremdschluessel_aktiv = int(
                    verbindung.execute(
                        "PRAGMA foreign_keys"
                    ).fetchone()[0]
                )
                integritaetsmeldungen = [
                    zeile[0]
                    for zeile in verbindung.execute(
                        "PRAGMA integrity_check"
                    ).fetchall()
                ]
                fremdschluesselfehler = verbindung.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                tabellenanzahl = int(
                    verbindung.execute(
                        """
                        SELECT COUNT(*)
                        FROM sqlite_master
                        WHERE type = 'table'
                          AND name NOT LIKE 'sqlite_%'
                        """
                    ).fetchone()[0]
                )
        except (OSError, sqlite3.DatabaseError) as fehler:
            raise CommandError(
                "Die Fachdatenbank konnte nicht initialisiert werden: "
                f"{fehler}"
            ) from fehler

        if not fremdschluessel_aktiv:
            raise CommandError(
                "Die SQLite-Fremdschluesselpruefung ist nicht aktiv."
            )

        if integritaetsmeldungen != ["ok"]:
            raise CommandError(
                "Die SQLite-Integritaetspruefung ist fehlgeschlagen: "
                + "; ".join(str(wert) for wert in integritaetsmeldungen)
            )

        if fremdschluesselfehler:
            raise CommandError(
                "Die Fachdatenbank enthaelt "
                f"{len(fremdschluesselfehler)} "
                "ungueltige Fremdschluesselverknuepfung(en)."
            )

        datenbankpfad = os.path.abspath(os.fspath(database.DB_NAME))
        self.stdout.write(
            self.style.SUCCESS(
                "Fachdatenbank erfolgreich initialisiert: "
                f"{datenbankpfad} ({tabellenanzahl} Fachtabellen)."
            )
        )

