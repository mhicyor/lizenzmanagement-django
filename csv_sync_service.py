import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from django.conf import settings

from benutzer_status_service import (
    IN_QUELLE_DEAKTIVIERT,
    NICHT_IN_QUELLE_GEFUNDEN,
)
from datenquelle_service import DATENBANK_DATEI, datenquelle_laden
from sync_status_service import (
    SynchronisationLaeuftBereits,
    erfolgreiche_synchronisation_speichern,
    fehler_speichern,
    synchronisationslauf_erfolgreich_beenden,
    synchronisationslauf_fehlerhaft_beenden,
    synchronisationslauf_starten,
)
from sqlite_context import sqlite_verbindung


class CsvSyncFehler(Exception):
    pass


def _text(wert: Any) -> str:
    return str(wert or "").strip()


def _json_objekt_laden(wert: Any) -> dict[str, Any]:
    if isinstance(wert, dict):
        return wert
    if wert in (None, ""):
        return {}
    try:
        ergebnis = json.loads(wert)
    except (TypeError, json.JSONDecodeError) as fehler:
        raise CsvSyncFehler(
            "Die gespeicherte CSV-Konfiguration ist ungültig."
        ) from fehler
    if not isinstance(ergebnis, dict):
        raise CsvSyncFehler(
            "Die gespeicherte CSV-Konfiguration muss ein Objekt sein."
        )
    return ergebnis


def _status_aktiv(wert: Any) -> int:
    text = _text(wert).lower()
    if text in {
        "inactive", "inaktiv", "disabled", "deaktiviert",
        "false", "0", "gesperrt", "blocked",
    }:
        return 0
    return 1


def _csv_dateipfad_ermitteln(relativer_pfad: str) -> Path:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    csv_verzeichnis = (media_root / "csv_datenquellen").resolve()
    dateipfad = (media_root / _text(relativer_pfad)).resolve()
    try:
        dateipfad.relative_to(csv_verzeichnis)
    except ValueError as fehler:
        raise CsvSyncFehler(
            "Der gespeicherte CSV-Dateipfad ist ungültig."
        ) from fehler
    if not dateipfad.is_file() or dateipfad.suffix.lower() != ".csv":
        raise CsvSyncFehler(
            "Die gespeicherte CSV-Datei wurde nicht gefunden."
        )
    return dateipfad


def _benutzerdaten_normalisieren(
    zeile: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    def feld(name: str) -> str:
        spalte = _text(mapping.get(name))
        wert = _text(zeile.get(spalte)) if spalte else ""
        return "" if wert in {"-", "'-"} else wert

    vorname = feld("vorname")
    nachname = feld("nachname")
    name = feld("name") or " ".join(
        teil for teil in (vorname, nachname) if teil
    )
    email = feld("email").lower()
    benutzername = feld("benutzername")
    externe_id = feld("externe_id")

    if not benutzername:
        benutzername = email or externe_id

    return {
        "name": name,
        "vorname": vorname,
        "nachname": nachname,
        "benutzername": benutzername,
        "email": email,
        "abteilung": feld("abteilung"),
        "externe_id": externe_id,
        "aktiv": _status_aktiv(feld("status")),
    }


def csv_datenquelle_datensaetze_laden(
    datenquelle_id: int | str,
) -> dict[str, Any]:
    datenquelle = datenquelle_laden(datenquelle_id)
    if datenquelle is None:
        raise CsvSyncFehler("Die Datenquelle wurde nicht gefunden.")
    if _text(datenquelle.get("typ")).lower() != "csv":
        raise CsvSyncFehler(
            "Die ausgewählte Datenquelle ist keine CSV-Datenquelle."
        )
    if not bool(datenquelle.get("aktiv", 0)):
        raise CsvSyncFehler("Die CSV-Datenquelle ist deaktiviert.")

    mapping = _json_objekt_laden(datenquelle.get("feld_mapping"))
    if "lizenzname" in mapping:
        raise CsvSyncFehler(
            "Diese ältere CSV-Quelle enthält noch Lizenzdaten. "
            "Bitte lege sie als neue Benutzer-CSV erneut an."
        )
    if not (
        mapping.get("name")
        or (mapping.get("vorname") and mapping.get("nachname"))
    ):
        raise CsvSyncFehler(
            "Im CSV-Mapping fehlen Vorname und Nachname."
        )

    konfiguration = _json_objekt_laden(
        datenquelle.get("konfiguration_info")
    )
    trennzeichen = konfiguration.get("trennzeichen") or ";"
    if trennzeichen == "\\t":
        trennzeichen = "\t"
    if trennzeichen not in {",", ";", "\t", "|"}:
        raise CsvSyncFehler("Das gespeicherte CSV-Trennzeichen ist ungültig.")

    dateipfad = _csv_dateipfad_ermitteln(datenquelle.get("endpunkt"))
    kodierung = konfiguration.get("encoding") or "utf-8-sig"
    datensaetze: list[dict[str, Any]] = []
    try:
        with dateipfad.open("r", encoding=kodierung, newline="") as datei:
            reader = csv.DictReader(
                datei,
                delimiter=trennzeichen,
                quotechar='"',
                doublequote=True,
                strict=True,
            )
            spalten = [_text(spalte) for spalte in (reader.fieldnames or [])]
            fehlende_spalten = {
                _text(spalte) for spalte in mapping.values()
            } - set(spalten)
            if fehlende_spalten:
                raise CsvSyncFehler(
                    "In der CSV-Datei fehlen zugeordnete Spalten: "
                    + ", ".join(sorted(fehlende_spalten))
                )
            for zeile in reader:
                if any(_text(wert) for wert in zeile.values()):
                    datensaetze.append(
                        _benutzerdaten_normalisieren(zeile, mapping)
                    )
    except UnicodeDecodeError as fehler:
        raise CsvSyncFehler(
            "Die CSV-Datei konnte nicht als UTF-8 gelesen werden."
        ) from fehler
    except csv.Error as fehler:
        raise CsvSyncFehler(
            f"Die CSV-Datei konnte nicht gelesen werden: {fehler}"
        ) from fehler

    return {
        "datenquelle_id": int(datenquelle["id"]),
        "datenquelle_name": datenquelle.get("name", ""),
        "dateipfad": str(dateipfad),
        "dateiname": konfiguration.get("dateiname") or dateipfad.name,
        "trennzeichen": trennzeichen,
        "kodierung": kodierung,
        "spalten": spalten,
        "anzahl_datensaetze": len(datensaetze),
        "datensaetze": datensaetze,
    }


def _quellen_schluessel(datenquelle_id: int | str) -> str:
    try:
        return f"csv:{int(datenquelle_id)}"
    except (TypeError, ValueError) as fehler:
        raise CsvSyncFehler("Die Datenquellen-ID ist ungültig.") from fehler


def _benutzer_treffer(
    cursor: sqlite3.Cursor,
    datensatz: dict[str, Any],
    quelle: str,
) -> list[sqlite3.Row]:
    bedingungen = []
    parameter: list[Any] = []
    externe_id = _text(datensatz.get("externe_id"))
    email = _text(datensatz.get("email")).lower()
    benutzername = _text(datensatz.get("benutzername"))

    if externe_id:
        bedingungen.append("(quelle = ? AND externe_id = ?)")
        parameter.extend((quelle, externe_id))
    if email:
        bedingungen.append("LOWER(TRIM(COALESCE(email, ''))) = ?")
        parameter.append(email)
    if benutzername:
        bedingungen.append("LOWER(TRIM(benutzername)) = LOWER(?)")
        parameter.append(benutzername)
    if not bedingungen and _text(datensatz.get("name")):
        bedingungen.append("LOWER(TRIM(name)) = LOWER(?)")
        parameter.append(_text(datensatz.get("name")))
    if not bedingungen:
        return []

    return cursor.execute(
        """
        SELECT id, name, vorname, nachname, benutzername, email,
               abteilung, aktiv, quelle, externe_id
        FROM benutzer
        WHERE """ + " OR ".join(bedingungen) + " ORDER BY id",
        parameter,
    ).fetchall()


def csv_datenquelle_sync_vorschau(
    datenquelle_id: int | str,
) -> dict[str, Any]:
    abruf = csv_datenquelle_datensaetze_laden(datenquelle_id)
    quelle = _quellen_schluessel(datenquelle_id)
    ergebnis = []
    zaehler = {
        "neu": 0,
        "aktualisieren": 0,
        "unveraendert": 0,
        "fehlerhaft": 0,
    }
    gesehene_kennungen: set[tuple[str, str]] = set()

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row
        cursor = verbindung.cursor()
        for datensatz in abruf["datensaetze"]:
            kennungen = {
                (feld, _text(datensatz.get(feld)).lower())
                for feld in ("email", "benutzername", "externe_id")
                if _text(datensatz.get(feld))
            }
            if not kennungen and _text(datensatz.get("name")):
                kennungen.add((
                    "name",
                    _text(datensatz.get("name")).lower(),
                ))
            if kennungen & gesehene_kennungen:
                aktion = "fehlerhaft"
                meldung = "Dieser Benutzer ist in der CSV-Datei mehrfach enthalten."
                treffer = []
            elif not _text(datensatz.get("name")):
                aktion = "fehlerhaft"
                meldung = "Vorname und Nachname sind erforderlich."
                treffer = []
            else:
                treffer = _benutzer_treffer(cursor, datensatz, quelle)
                if len(treffer) > 1:
                    aktion = "fehlerhaft"
                    meldung = "Mehrere lokale Benutzer passen zu diesem Datensatz."
                elif not treffer:
                    aktion = "neu"
                    meldung = "Benutzer wird neu angelegt."
                elif _text(treffer[0]["quelle"]) != quelle:
                    aktion = "unveraendert"
                    meldung = "Vorhandenem Benutzer sicher zugeordnet; Stammdaten bleiben unverändert."
                else:
                    vergleich = {
                        feld: datensatz.get(feld)
                        for feld in (
                            "name", "vorname", "nachname", "benutzername",
                            "email", "abteilung", "aktiv", "externe_id",
                        )
                    }
                    geaendert = any(
                        _text(treffer[0][feld]) != _text(wert)
                        for feld, wert in vergleich.items()
                    )
                    aktion = "aktualisieren" if geaendert else "unveraendert"
                    meldung = "Benutzerdaten werden aktualisiert." if geaendert else "Keine Änderung."

            gesehene_kennungen.update(kennungen)
            zaehler[aktion] += 1
            ergebnis.append({
                **datensatz,
                "aktion": aktion,
                "meldung": meldung,
                "vorhandener_benutzer_id": treffer[0]["id"] if len(treffer) == 1 else None,
            })

    return {
        "datenquelle_id": abruf["datenquelle_id"],
        "datenquelle_name": abruf["datenquelle_name"],
        **zaehler,
        "datensaetze": ergebnis,
    }


def _vorschau_anwenden(
    vorschau: dict[str, Any],
    quelle: str,
) -> dict[str, Any]:
    zaehler = {
        "angelegt": 0,
        "aktualisiert": 0,
        "deaktiviert": 0,
        "unveraendert": 0,
        "fehlerhaft": 0,
    }
    meldungen = []
    gesehene_ids: set[int] = set()

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        cursor = verbindung.cursor()
        for datensatz in vorschau["datensaetze"]:
            aktion = datensatz["aktion"]
            benutzer_id = datensatz.get("vorhandener_benutzer_id")
            if aktion == "fehlerhaft":
                zaehler["fehlerhaft"] += 1
                meldungen.append({
                    "externe_id": datensatz.get("externe_id") or datensatz.get("email"),
                    "meldung": datensatz.get("meldung"),
                })
                continue
            if aktion == "unveraendert":
                zaehler["unveraendert"] += 1
                if benutzer_id:
                    gesehene_ids.add(int(benutzer_id))
                continue
            if aktion == "neu":
                benutzername = _text(datensatz["benutzername"])
                if not benutzername:
                    namensschluessel = hashlib.sha256(
                        _text(datensatz["name"]).lower().encode("utf-8")
                    ).hexdigest()[:12]
                    benutzername = (
                        f"{quelle.replace(':', '-')}-{namensschluessel}"
                    )
                cursor.execute(
                    """
                    INSERT INTO benutzer (
                        name, vorname, nachname, benutzername, email,
                        abteilung, aktiv, quelle, externe_id,
                        zuletzt_synchronisiert, deaktivierungsgrund
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?
                    )
                    """,
                    (
                        datensatz["name"], datensatz["vorname"],
                        datensatz["nachname"], benutzername,
                        datensatz["email"], datensatz["abteilung"],
                        datensatz["aktiv"], quelle, datensatz["externe_id"],
                        (
                            None
                            if datensatz["aktiv"]
                            else IN_QUELLE_DEAKTIVIERT
                        ),
                    ),
                )
                gesehene_ids.add(int(cursor.lastrowid))
                zaehler["angelegt"] += 1
                continue

            cursor.execute(
                """
                UPDATE benutzer
                SET name = ?, vorname = ?, nachname = ?, benutzername = ?,
                    email = ?, abteilung = ?, aktiv = ?, externe_id = ?,
                    zuletzt_synchronisiert = CURRENT_TIMESTAMP,
                    deaktivierungsgrund = ?
                WHERE id = ? AND quelle = ?
                """,
                (
                    datensatz["name"], datensatz["vorname"],
                    datensatz["nachname"], datensatz["benutzername"],
                    datensatz["email"], datensatz["abteilung"],
                    datensatz["aktiv"], datensatz["externe_id"],
                    (
                        None
                        if datensatz["aktiv"]
                        else IN_QUELLE_DEAKTIVIERT
                    ),
                    benutzer_id, quelle,
                ),
            )
            gesehene_ids.add(int(benutzer_id))
            zaehler["aktualisiert"] += 1

        # Ausschließlich Benutzer dieser CSV-Quelle werden bei vollständigem
        # Import als nicht mehr enthalten markiert. AD-Benutzer bleiben unberührt.
        aktive_quellenbenutzer = cursor.execute(
            "SELECT COUNT(*) FROM benutzer WHERE quelle = ? AND aktiv = 1",
            (quelle,),
        ).fetchone()[0]
        valide_datensaetze = len(vorschau["datensaetze"]) - zaehler["fehlerhaft"]
        vollstaendig_genug = (
            not aktive_quellenbenutzer
            or valide_datensaetze * 2 >= aktive_quellenbenutzer
        )
        if (
            vorschau["datensaetze"]
            and not zaehler["fehlerhaft"]
            and vollstaendig_genug
        ):
            platzhalter = ",".join("?" for _ in gesehene_ids)
            sql = (
                "UPDATE benutzer "
                "SET aktiv = 0, deaktivierungsgrund = ? "
                "WHERE quelle = ? AND aktiv = 1"
            )
            parameter: list[Any] = [
                NICHT_IN_QUELLE_GEFUNDEN,
                quelle,
            ]
            if gesehene_ids:
                sql += f" AND id NOT IN ({platzhalter})"
                parameter.extend(sorted(gesehene_ids))
            cursor.execute(sql, parameter)
            zaehler["deaktiviert"] = max(0, cursor.rowcount)

        verbindung.commit()

    return {**zaehler, "meldungen": meldungen}


def csv_datenquelle_synchronisieren(
    datenquelle_id: int | str,
    ausgeloest_durch: str = "manuell",
) -> dict[str, Any]:
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError) as fehler:
        raise CsvSyncFehler("Die Datenquellen-ID ist ungültig.") from fehler
    try:
        lauf_id = synchronisationslauf_starten(
            datenquelle_id, ausgeloest_durch=ausgeloest_durch
        )
    except SynchronisationLaeuftBereits as fehler:
        raise CsvSyncFehler(str(fehler)) from fehler

    try:
        vorschau = csv_datenquelle_sync_vorschau(datenquelle_id)
        ergebnis = _vorschau_anwenden(
            vorschau, _quellen_schluessel(datenquelle_id)
        )
        meldung = (
            "CSV-Benutzersynchronisierung erfolgreich: "
            f"{ergebnis['angelegt']} angelegt, "
            f"{ergebnis['aktualisiert']} aktualisiert, "
            f"{ergebnis['deaktiviert']} deaktiviert, "
            f"{ergebnis['unveraendert']} unverändert, "
            f"{ergebnis['fehlerhaft']} fehlerhaft."
        )
        details = "\n".join(
            f"{eintrag.get('externe_id') or 'Ohne Kennung'}: {eintrag.get('meldung')}"
            for eintrag in ergebnis["meldungen"]
        ) or None
        synchronisationslauf_erfolgreich_beenden(
            lauf_id=lauf_id, meldung=meldung, fehlerdetails=details,
            **{schluessel: ergebnis[schluessel] for schluessel in (
                "angelegt", "aktualisiert", "deaktiviert",
                "unveraendert", "fehlerhaft",
            )},
        )
        erfolgreiche_synchronisation_speichern(
            datenquelle_id, lauf_id=lauf_id, meldung=meldung
        )
        return {
            "datenquelle_id": datenquelle_id,
            "datenquelle_name": vorschau["datenquelle_name"],
            **ergebnis,
        }
    except Exception as fehler:
        fehlermeldung = _text(fehler) or "Unbekannter CSV-Fehler."
        try:
            synchronisationslauf_fehlerhaft_beenden(lauf_id, fehlermeldung)
            fehler_speichern(datenquelle_id, fehlermeldung, lauf_id=lauf_id)
        except Exception:
            pass
        if isinstance(fehler, CsvSyncFehler):
            raise
        raise CsvSyncFehler(
            "Die CSV-Benutzersynchronisierung ist unerwartet fehlgeschlagen."
        ) from fehler
