import json
import sqlite3
from datetime import date, datetime
from typing import Any

from api_feld_service import (
    eindeutige_textwerte,
    wert_aus_pfad,
)

from datenquelle_service import (
    DATENBANK_DATEI,
    datenquelle_laden,
    datenquelle_mit_geheimnissen_laden,
)
from sqlite_context import sqlite_verbindung
from rest_api_service import (
    RestApiFehler,
    rest_api_daten_abrufen,
)
from reconciliation_service import (
    ReconciliationFehler,
    lizenzdaten_abgleichen,
)

from sync_status_service import (
    SynchronisationLaeuftBereits,
    erfolgreiche_synchronisation_speichern,
    fehler_speichern,
    synchronisationslauf_erfolgreich_beenden,
    synchronisationslauf_fehlerhaft_beenden,
    synchronisationslauf_starten,
)

from zuweisungs_matching_service import (
    externe_zuweisungen_speichern,
)


class RestSyncFehler(Exception):
    pass


def _json_objekt_laden(
    wert: Any,
    standard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(wert, dict):
        return wert

    if wert in (None, ""):
        return standard or {}

    try:
        ergebnis = json.loads(wert)
    except (TypeError, json.JSONDecodeError) as fehler:
        raise RestSyncFehler(
            "Die gespeicherte JSON-Konfiguration "
            "ist ungültig."
        ) from fehler

    if not isinstance(ergebnis, dict):
        raise RestSyncFehler(
            "Die gespeicherte JSON-Konfiguration "
            "muss ein Objekt sein."
        )

    return ergebnis


def _wert_aus_pfad(
    datensatz: dict[str, Any],
    feldpfad: str | None,
) -> Any:
    return wert_aus_pfad(datensatz, feldpfad)


def _anzahl_bereinigen(
    wert: Any,
) -> int:
    try:
        return max(0, int(wert))
    except (TypeError, ValueError):
        return 0


def _optionale_anzahl_bereinigen(wert: Any) -> int | None:
    """Unterscheidet einen gemeldeten Nullwert von keinem Messwert."""
    if wert in (None, ""):
        return None

    return _anzahl_bereinigen(wert)


def _datum_bereinigen(wert: Any) -> str | None:
    text = str(wert or "").strip()
    return text or None


def _datum_ist_abgelaufen(wert: Any) -> bool:
    text = str(wert or "").strip()
    if not text:
        return False

    try:
        datum = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        try:
            datum = date.fromisoformat(text[:10])
        except ValueError:
            return False

    return datum < date.today()


def _regelwerte(wert: Any) -> set[str]:
    return {
        teil.strip().casefold()
        for teil in str(wert or "").replace(";", ",").split(",")
        if teil.strip()
    }


def _ziel_typ_normalisieren(wert: Any, standard: str = "benutzer") -> str:
    text = str(wert or "").strip().casefold()

    if text in {
        "geraet",
        "gerät",
        "device",
        "endpoint",
        "server",
        "computer",
        "client",
        "workstation",
        "desktop",
        "laptop",
        "mobile",
    }:
        return "geraet"

    if text in {"benutzer", "user", "person", "account"}:
        return "benutzer"

    return "geraet" if str(standard).casefold() == "geraet" else "benutzer"


def _ziel_typ_bestimmen(
    rohdaten: dict[str, Any],
    feld_mapping: dict[str, Any],
) -> str:
    standard = _ziel_typ_normalisieren(
        feld_mapping.get("ziel_typ_standard")
    )
    feldpfad = (
        feld_mapping.get("ziel_typ_feld")
        or feld_mapping.get("lizenzname")
    )

    if not feldpfad:
        return standard

    quelltexte = [
        str(wert or "").strip().casefold()
        for wert in eindeutige_textwerte(
            _wert_aus_pfad(rohdaten, feldpfad)
        )
    ]
    benutzer_werte = _regelwerte(
        feld_mapping.get("ziel_typ_benutzer_werte")
    )
    geraete_werte = _regelwerte(
        feld_mapping.get("ziel_typ_geraete_werte")
    )

    if any(
        regel in quelltext
        for quelltext in quelltexte
        for regel in geraete_werte
    ):
        return "geraet"

    if any(
        regel in quelltext
        for quelltext in quelltexte
        for regel in benutzer_werte
    ):
        return "benutzer"

    # Häufig beschreibt bereits der Produktname eindeutig, ob eine
    # Lizenz für Personen oder für Geräte bestimmt ist. Diese kleine
    # allgemeine Erkennung hält den Assistenten auch dann einfach, wenn
    # der Anbieter dafür kein separates Feld liefert.
    geraete_begriffe = {
        "server",
        "device",
        "endpoint",
        "appliance",
        "host",
        "computer",
        "client",
        "workstation",
        "desktop",
        "laptop",
        "mobile",
    }
    benutzer_begriffe = {
        "user",
        "person",
        "account",
        "named user",
    }

    if any(
        begriff in quelltext
        for quelltext in quelltexte
        for begriff in geraete_begriffe
    ):
        return "geraet"

    # Wenn die Quelle fachlich als Gerätequelle gepflegt ist, darf ein
    # Produktname wie "XDR - User" nicht automatisch wieder Personen erzeugen.
    # Manche Hersteller verwenden "User" als Lizenzpaketname, obwohl die
    # gemeldeten Zuweisungen technisch Endpoints oder Geräte sind.
    if standard == "geraet":
        return "geraet"

    if any(
        begriff in quelltext
        for quelltext in quelltexte
        for begriff in benutzer_begriffe
    ):
        return "benutzer"

    return standard


def _status_bereinigen(
    wert: Any,
) -> str:
    text = str(wert or "").strip().lower()

    if text in {
        "active",
        "aktiv",
        "enabled",
        "true",
        "1",
        "in stock",
    }:
        return "aktiv"

    if text in {
        "inactive",
        "inaktiv",
        "disabled",
        "false",
        "0",
        "out of stock",
    }:
        return "inaktiv"

    return text or "aktiv"


def _zusatzdaten_modus_bestimmen(
    feld_mapping: dict[str, Any],
) -> str:
    """
    Zusatzdaten einer REST-Quelle können echte Lizenzzuweisungen
    oder nur ein externer Gerätebestand sein.
    """
    modus = str(
        feld_mapping.get("import_modus")
        or feld_mapping.get("datenart")
        or feld_mapping.get("verwendungsart")
        or ""
    ).strip().lower()
    modus = (
        modus.replace("-", "_")
        .replace(" ", "_")
        .replace("ä", "ae")
    )

    geraetebestand_werte = {
        "geraetebestand",
        "geraete_bestand",
        "geraete",
        "geraeteinventar",
        "geraete_inventory",
        "inventar",
        "inventory",
        "device_inventory",
        "devices",
    }

    if modus in geraetebestand_werte:
        return "geraetebestand"

    return "zuweisungen"



def _zuweisung_normalisieren(
    rohdaten: dict[str, Any],
    feld_mapping: dict[str, Any],
) -> dict[str, Any]:
    lizenz_schluessel = eindeutige_textwerte(
        _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("lizenz_schluessel")
            or feld_mapping.get("lizenz_externe_id"),
        )
    )

    benutzername = _wert_aus_pfad(
        rohdaten,
        feld_mapping.get("benutzername"),
    )
    benutzername = str(benutzername or "").strip()
    if "\\" in benutzername:
        benutzername = benutzername.rsplit("\\", 1)[-1]

    return {
        "lizenz_externe_id": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("lizenz_externe_id"),
        ),
        "zuweisung_externe_id": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("zuweisung_externe_id"),
        ),
        "benutzer_externe_id": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("benutzer_externe_id"),
        ),
        "email": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("email"),
        ),
        "benutzername": benutzername,
        "status": _status_bereinigen(
            _wert_aus_pfad(
                rohdaten,
                feld_mapping.get("status"),
            )
        ),
        "lizenz_schluessel": lizenz_schluessel,
        "ziel_typ": _ziel_typ_bestimmen(
            rohdaten,
            feld_mapping,
        ),
        "ziel_externe_id": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("ziel_externe_id"),
        ),
        "ziel_name": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("ziel_name"),
        ),
        "inventarnummer": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("inventarnummer"),
        ),
        "seriennummer": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("seriennummer"),
        ),
        "geraetetyp": _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("geraetetyp"),
        ),
    }


def _zuweisungen_nach_lizenz_gruppieren(
    datensaetze: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    gruppiert: dict[str, list[dict[str, Any]]] = {}

    for datensatz in datensaetze:
        if datensatz.get("status") == "inaktiv":
            continue

        lizenz_schluessel = datensatz.get("lizenz_schluessel") or [
            datensatz.get("lizenz_externe_id")
        ]

        for lizenz_externe_id in eindeutige_textwerte(lizenz_schluessel):
            gruppiert.setdefault(
                lizenz_externe_id,
                [],
            ).append({
                **datensatz,
                "benutzer_externe_id": datensatz.get(
                    "benutzer_externe_id"
                ),
                "email": datensatz.get("email"),
                "benutzername": datensatz.get(
                    "benutzername"
                ),
                "zuweisung_externe_id": datensatz.get(
                    "zuweisung_externe_id"
                ),
            })

    return gruppiert


def _datenquellen_schluessel(
    datenquelle_id: int | str,
) -> str:
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError) as fehler:
        raise RestSyncFehler(
            "Die Datenquellen-ID ist ungültig."
        ) from fehler

    return f"rest_api:{datenquelle_id}"


def _konfiguration_erstellen(
    datenquelle: dict[str, Any],
    geheimnisse: dict[str, Any],
) -> dict[str, Any]:
    konfiguration = {
        "name": datenquelle.get("name"),
        "basis_url": datenquelle.get(
            "basis_url"
        ),
        "endpunkt": datenquelle.get(
            "endpunkt"
        ),
        "auth_typ": (
            datenquelle.get("auth_typ")
            or "keine"
        ),
        "token_url": datenquelle.get(
            "token_url"
        ),
        "scope": datenquelle.get("scope"),
    }

    konfiguration.update(
        geheimnisse.get("geheimnisse")
        or {}
    )

    return konfiguration



def _zuweisungs_konfiguration_erstellen(
    datenquelle: dict[str, Any],
    geheimnisse: dict[str, Any],
) -> dict[str, Any]:
    konfiguration = _konfiguration_erstellen(
        datenquelle,
        geheimnisse,
    )

    zuweisungen_endpunkt = str(
        datenquelle.get("zuweisungen_endpunkt")
        or ""
    ).strip()

    if zuweisungen_endpunkt:
        konfiguration["endpunkt"] = zuweisungen_endpunkt

    return konfiguration


def rest_datenquelle_zuweisungen_laden(
    datenquelle_id: int | str,
) -> dict[str, Any]:
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    if datenquelle is None:
        raise RestSyncFehler(
            "Die Datenquelle wurde nicht gefunden."
        )

    zuweisungen_endpunkt = str(
        datenquelle.get("zuweisungen_endpunkt")
        or ""
    ).strip()

    if not zuweisungen_endpunkt:
        return {
            "datenquelle_id": datenquelle.get("id"),
            "datenquelle_name": datenquelle.get("name"),
            "aktiv": False,
            "modus": "zuweisungen",
            "anzahl_datensaetze": 0,
            "datensaetze": [],
        }

    geheimnisse = datenquelle_mit_geheimnissen_laden(
        datenquelle_id
    )

    if geheimnisse is None:
        raise RestSyncFehler(
            "Die Zugangsdaten konnten nicht geladen werden."
        )

    zuweisungen_mapping = _json_objekt_laden(
        datenquelle.get("zuweisungen_feld_mapping")
    )
    modus = _zusatzdaten_modus_bestimmen(
        zuweisungen_mapping
    )

    if not zuweisungen_mapping:
        return {
            "datenquelle_id": datenquelle.get("id"),
            "datenquelle_name": datenquelle.get("name"),
            "aktiv": False,
            "modus": modus,
            "anzahl_datensaetze": 0,
            "datensaetze": [],
        }

    konfiguration = _zuweisungs_konfiguration_erstellen(
        datenquelle,
        geheimnisse,
    )

    try:
        abruf = rest_api_daten_abrufen(
            konfiguration
        )
    except RestApiFehler as fehler:
        raise RestSyncFehler(
            str(fehler)
        ) from fehler

    normalisierte_datensaetze = []

    for rohdaten in abruf["datensaetze"]:
        if not isinstance(rohdaten, dict):
            continue

        normalisierte_datensaetze.append(
            _zuweisung_normalisieren(
                rohdaten,
                zuweisungen_mapping,
            )
        )

    return {
        "datenquelle_id": datenquelle["id"],
        "datenquelle_name": datenquelle["name"],
        "aktiv": True,
        "modus": modus,
        "http_status": abruf["http_status"],
        "listen_pfad": abruf["listen_pfad"],
        "anzahl_datensaetze": len(
            normalisierte_datensaetze
        ),
        "datensaetze": normalisierte_datensaetze,
    }


def rest_datenquelle_datensaetze_laden(
    datenquelle_id: int | str,
) -> dict[str, Any]:
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    if datenquelle is None:
        raise RestSyncFehler(
            "Die Datenquelle wurde nicht gefunden."
        )

    if datenquelle.get("typ") != "rest_api":
        raise RestSyncFehler(
            "Die ausgewählte Datenquelle ist "
            "keine REST-API."
        )

    if not datenquelle.get("aktiv"):
        raise RestSyncFehler(
            "Die Datenquelle ist deaktiviert."
        )

    geheimnisse = (
        datenquelle_mit_geheimnissen_laden(
            datenquelle_id
        )
    )

    if geheimnisse is None:
        raise RestSyncFehler(
            "Die Zugangsdaten konnten nicht "
            "geladen werden."
        )

    feld_mapping = _json_objekt_laden(
        datenquelle.get("feld_mapping")
    )

    konfiguration = _konfiguration_erstellen(
        datenquelle,
        geheimnisse,
    )

    try:
        abruf = rest_api_daten_abrufen(
            konfiguration
        )
    except RestApiFehler as fehler:
        raise RestSyncFehler(
            str(fehler)
        ) from fehler

    normalisierte_datensaetze = []

    for rohdaten in abruf["datensaetze"]:
        if not isinstance(rohdaten, dict):
            continue

        ablaufdatum = _datum_bereinigen(
            _wert_aus_pfad(
                rohdaten,
                feld_mapping.get("ablaufdatum"),
            )
        )
        status_roh = _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("status"),
        )
        status = _status_bereinigen(status_roh)
        if status_roh in (None, "") and _datum_ist_abgelaufen(ablaufdatum):
            status = "inaktiv"

        anbieter = _wert_aus_pfad(
            rohdaten,
            feld_mapping.get("anbieter"),
        )

        normalisierte_datensaetze.append({
                "lizenzname": _wert_aus_pfad(
                    rohdaten,
                    feld_mapping.get(
                        "lizenzname"
                    ),
                ),
                "anbieter": str(
                    anbieter or datenquelle.get("name") or ""
                ).strip(),
                "externe_id": _wert_aus_pfad(
                    rohdaten,
                    feld_mapping.get(
                        "externe_id"
                    ),
                ),
                "anzahl": _anzahl_bereinigen(
                    _wert_aus_pfad(
                        rohdaten,
                        feld_mapping.get(
                            "anzahl"
                        ),
                    )
                ),
                "verbrauch": _optionale_anzahl_bereinigen(
                    _wert_aus_pfad(rohdaten, feld_mapping.get("verbrauch"))
                ),
                "verbrauchsdatum": _datum_bereinigen(
                    _wert_aus_pfad(
                        rohdaten,
                        feld_mapping.get("verbrauchsdatum"),
                    )
                ),
                "startdatum": _datum_bereinigen(
                    _wert_aus_pfad(rohdaten, feld_mapping.get("startdatum"))
                ),
                "ablaufdatum": ablaufdatum,
                "produktschluessel": str(
                    _wert_aus_pfad(
                        rohdaten,
                        feld_mapping.get("produktschluessel"),
                    )
                    or ""
                ).strip() or None,
                "ziel_typ": _ziel_typ_bestimmen(rohdaten, feld_mapping),
                "status": status,
                "email": _wert_aus_pfad(
                    rohdaten,
                    feld_mapping.get(
                        "email"
                    ),
                ),
            })

    return {
        "datenquelle_id": datenquelle["id"],
        "datenquelle_name": datenquelle["name"],
        "http_status": abruf["http_status"],
        "listen_pfad": abruf["listen_pfad"],
        "anzahl_datensaetze": len(
            normalisierte_datensaetze
        ),
        "datensaetze": normalisierte_datensaetze,
    }


def _vorhandene_lizenz_suchen(
    externe_id: Any,
    datenquelle_id: int | str,
    datenquellen_schluessel: str,
    ziel_typ: str | None = None,
) -> dict[str, Any] | None:
    """
    Sucht eine bereits verknüpfte externe Lizenz.

    Bevorzugt wird die eindeutige Kombination aus
    Datenquellen-ID und externer ID. Der alte Textschlüssel
    bleibt vorübergehend als Kompatibilitätsprüfung erhalten.
    """
    externe_id = str(
        externe_id or ""
    ).strip()

    try:
        datenquelle_id = int(
            datenquelle_id
        )
    except (TypeError, ValueError):
        return None

    if not externe_id:
        return None

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        ziel_typ = str(ziel_typ or "").strip().lower()
        ziel_filter = ""
        parameter: list[Any] = [
            externe_id,
            externe_id,
            datenquelle_id,
            datenquellen_schluessel,
        ]
        if ziel_typ in {"benutzer", "geraet"}:
            ziel_filter = (
                " AND COALESCE(zuweisungsart, 'benutzer') = ?"
            )
            parameter.append(ziel_typ)

        zeile = verbindung.execute(
            """
            SELECT
                id,
                name,
                anbieter,
                anzahl,
                externer_verbrauch,
                verbrauch_gemeldet_am,
                startdatum,
                ablaufdatum,
                externer_produktschluessel,
                zuweisungsart,
                externe_id,
                status,
                datenquelle,
                datenquelle_id
            FROM lizenzen
            WHERE (
                    externe_id = ?
                    OR externer_produktschluessel = ?
                  )
              AND (
                  datenquelle_id = ?
                  OR (
                      datenquelle_id IS NULL
                      AND datenquelle = ?
                  )
              )
            """ + ziel_filter + """
            ORDER BY CASE WHEN externe_id = ? THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (*parameter, externe_id),
        ).fetchone()

    return (
        dict(zeile)
        if zeile is not None
        else None
    )


def _eindeutige_quelllizenz_suchen(
    *,
    datenquelle_id: int | str,
    datenquellen_schluessel: str,
    ziel_typ: str,
) -> dict[str, Any] | None:
    """Liefert genau eine aktive Lizenz der Quelle und Verwendungsart."""
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError):
        return None

    ziel_typ = _ziel_typ_normalisieren(ziel_typ)

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row
        zeilen = verbindung.execute(
            """
            SELECT
                id,
                name,
                anbieter,
                anzahl,
                externer_verbrauch,
                verbrauch_gemeldet_am,
                startdatum,
                ablaufdatum,
                externer_produktschluessel,
                zuweisungsart,
                externe_id,
                status,
                datenquelle,
                datenquelle_id
            FROM lizenzen
            WHERE (
                    datenquelle_id = ?
                    OR (
                        datenquelle_id IS NULL
                        AND datenquelle = ?
                    )
                  )
              AND COALESCE(zuweisungsart, 'benutzer') = ?
              AND LOWER(COALESCE(status, 'aktiv')) != 'inaktiv'
            ORDER BY id
            LIMIT 2
            """,
            (
                datenquelle_id,
                datenquellen_schluessel,
                ziel_typ,
            ),
        ).fetchall()

    if len(zeilen) != 1:
        return None

    return dict(zeilen[0])


def _zuweisungen_lizenzen_zuordnen(
    *,
    datensaetze: list[dict[str, Any]],
    datenquelle_id: int | str,
    datenquellen_schluessel: str,
) -> dict[str, Any]:
    """
    Ordnet jeden gelieferten Benutzer beziehungsweise jedes Gerät einer
    lokalen Lizenz zu. Technische Produktmerkmale dürfen dabei mehrere
    Werte enthalten, werden aber nicht selbst zu lokalen Lizenzen.
    """
    gruppen: dict[tuple[int, str], dict[str, Any]] = {}
    nicht_zugeordnet: list[dict[str, Any]] = []
    ohne_zuordnungsziel = 0

    for datensatz in datensaetze:
        if datensatz.get("status") == "inaktiv":
            continue

        ziel_typ = _ziel_typ_normalisieren(
            datensatz.get("ziel_typ")
        )

        if ziel_typ == "benutzer":
            ziel_schluessel = tuple(
                str(datensatz.get(feld) or "").strip().casefold()
                for feld in (
                    "benutzer_externe_id",
                    "email",
                    "benutzername",
                )
            )
        else:
            ziel_schluessel = tuple(
                str(datensatz.get(feld) or "").strip().casefold()
                for feld in (
                    "ziel_externe_id",
                    "seriennummer",
                    "ziel_name",
                )
            )

        # Ein Endpunkt ohne Personendaten ist keine fehlerhafte
        # Benutzerzuweisung. Ebenso wenig lässt sich ein namenloses Gerät
        # sinnvoll speichern. Solche Datensätze werden neutral übersprungen.
        if not any(ziel_schluessel):
            ohne_zuordnungsziel += 1
            continue

        gefundene_lizenzen: dict[int, dict[str, Any]] = {}
        lizenz_schluessel = eindeutige_textwerte(
            datensatz.get("lizenz_schluessel")
            or [datensatz.get("lizenz_externe_id")]
        )

        for lizenz_schluessel_wert in lizenz_schluessel:
            lizenz = _vorhandene_lizenz_suchen(
                lizenz_schluessel_wert,
                datenquelle_id,
                datenquellen_schluessel,
                ziel_typ=ziel_typ,
            )
            if lizenz is not None:
                gefundene_lizenzen[lizenz["id"]] = lizenz

        # Einige APIs liefern an dieser Stelle technische Module statt
        # der gekauften Lizenz-ID. Ist für diese Quelle und Verwendungsart
        # genau eine Lizenz vorhanden, ist die Zuordnung trotzdem eindeutig.
        if not gefundene_lizenzen:
            lizenz = _eindeutige_quelllizenz_suchen(
                datenquelle_id=datenquelle_id,
                datenquellen_schluessel=datenquellen_schluessel,
                ziel_typ=ziel_typ,
            )
            if lizenz is not None:
                gefundene_lizenzen[lizenz["id"]] = lizenz

        if not gefundene_lizenzen:
            nicht_zugeordnet.append(datensatz)
            continue

        for lizenz in gefundene_lizenzen.values():
            gruppen_schluessel = (lizenz["id"], ziel_typ)
            gruppe = gruppen.setdefault(
                gruppen_schluessel,
                {
                    "lizenz": lizenz,
                    "ziel_typ": ziel_typ,
                    "datensaetze": [],
                    "_gesehen": set(),
                },
            )

            if ziel_schluessel in gruppe["_gesehen"]:
                continue

            gruppe["_gesehen"].add(ziel_schluessel)
            gruppe["datensaetze"].append(datensatz)

    bereinigte_gruppen = []
    for gruppe in gruppen.values():
        gruppe.pop("_gesehen", None)
        bereinigte_gruppen.append(gruppe)

    return {
        "gruppen": bereinigte_gruppen,
        "nicht_zugeordnet": nicht_zugeordnet,
        "ohne_zuordnungsziel": ohne_zuordnungsziel,
    }


def _externes_geraet_speichern(
    *,
    datenquelle_id: int,
    quelle: str,
    datensatz: dict[str, Any],
) -> int | None:
    externe_id = str(datensatz.get("ziel_externe_id") or "").strip()
    name = str(datensatz.get("ziel_name") or "").strip()
    seriennummer = str(datensatz.get("seriennummer") or "").strip()
    inventarnummer = str(datensatz.get("inventarnummer") or "").strip()
    geraetetyp = str(datensatz.get("geraetetyp") or "").strip()

    if not externe_id and not name and not seriennummer:
        return None

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row
        zeile = None

        if externe_id:
            zeile = verbindung.execute(
                """
                SELECT id FROM geraete
                WHERE datenquelle_id = ? AND externe_id = ?
                LIMIT 1
                """,
                (datenquelle_id, externe_id),
            ).fetchone()

        if zeile is None and seriennummer:
            treffer = verbindung.execute(
                """
                SELECT id FROM geraete
                WHERE LOWER(TRIM(COALESCE(seriennummer, ''))) = LOWER(?)
                LIMIT 2
                """,
                (seriennummer,),
            ).fetchall()
            if len(treffer) == 1:
                zeile = treffer[0]

        if zeile is None and name:
            treffer = verbindung.execute(
                """
                SELECT id FROM geraete
                WHERE LOWER(TRIM(name)) = LOWER(?)
                LIMIT 2
                """,
                (name,),
            ).fetchall()
            if len(treffer) == 1:
                zeile = treffer[0]

        if zeile is None:
            cursor = verbindung.execute(
                """
                INSERT INTO geraete (
                    name, inventarnummer, seriennummer, geraetetyp, status,
                    quelle, datenquelle_id, externe_id, zuletzt_synchronisiert
                )
                VALUES (?, ?, ?, ?, 'aktiv', ?, ?, ?, DATETIME('now'))
                """,
                (
                    name or externe_id or "Externes Gerät",
                    inventarnummer or None,
                    seriennummer or None,
                    geraetetyp or None,
                    quelle,
                    datenquelle_id,
                    externe_id or None,
                ),
            )
            return int(cursor.lastrowid)

        geraet_id = int(zeile["id"])
        verbindung.execute(
            """
            UPDATE geraete
            SET name = CASE WHEN ? != '' THEN ? ELSE name END,
                inventarnummer = CASE WHEN ? != '' THEN ? ELSE inventarnummer END,
                seriennummer = CASE WHEN ? != '' THEN ? ELSE seriennummer END,
                geraetetyp = CASE WHEN ? != '' THEN ? ELSE geraetetyp END,
                status = 'aktiv',
                quelle = ?,
                datenquelle_id = ?,
                externe_id = CASE WHEN ? != '' THEN ? ELSE externe_id END,
                zuletzt_synchronisiert = DATETIME('now')
            WHERE id = ?
            """,
            (
                name, name,
                inventarnummer, inventarnummer,
                seriennummer, seriennummer,
                geraetetyp, geraetetyp,
                quelle,
                datenquelle_id,
                externe_id, externe_id,
                geraet_id,
            ),
        )
        return geraet_id


def _externe_geraetezuweisungen_speichern(
    *,
    lizenz_id: int,
    datenquelle_id: int,
    quelle: str,
    datensaetze: list[dict[str, Any]],
) -> dict[str, int]:
    from lizenz_service import sync_lizenzzuweisung_ziel_speichern

    ergebnis = {
        "neu_zugewiesen": 0,
        "bereits_aktiv": 0,
        "fehlerhaft": 0,
        "deaktiviert": 0,
    }
    gelieferte_ids: set[str] = set()

    for datensatz in datensaetze:
        geraet_id = _externes_geraet_speichern(
            datenquelle_id=datenquelle_id,
            quelle=quelle,
            datensatz=datensatz,
        )
        if geraet_id is None:
            ergebnis["fehlerhaft"] += 1
            continue

        zuweisung_id = str(
            datensatz.get("zuweisung_externe_id")
            or datensatz.get("ziel_externe_id")
            or ""
        ).strip()
        if zuweisung_id:
            gelieferte_ids.add(zuweisung_id)

        erfolgreich, meldung = sync_lizenzzuweisung_ziel_speichern(
            lizenz_id,
            "geraet",
            geraet_id,
            quelle,
            zuweisung_id or None,
        )
        if erfolgreich:
            if "bereits" in str(meldung).lower():
                ergebnis["bereits_aktiv"] += 1
            else:
                ergebnis["neu_zugewiesen"] += 1
        else:
            ergebnis["fehlerhaft"] += 1

    if datensaetze and gelieferte_ids:
        platzhalter = ", ".join("?" for _ in gelieferte_ids)
        with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
            cursor = verbindung.execute(
                f"""
                UPDATE lizenz_zuweisungen
                SET status = 'inaktiv', entfernt_am = DATETIME('now'),
                    synchronisiert_am = DATETIME('now')
                WHERE lizenz_id = ? AND ziel_typ = 'geraet'
                  AND quelle = ? AND status = 'aktiv'
                  AND TRIM(COALESCE(externe_id, '')) != ''
                  AND externe_id NOT IN ({platzhalter})
                """,
                (lizenz_id, quelle, *sorted(gelieferte_ids)),
            )
            ergebnis["deaktiviert"] = max(0, cursor.rowcount)

    return ergebnis


def _externer_geraetebestand_speichern(
    *,
    datenquelle_id: int,
    quelle: str,
    datensaetze: list[dict[str, Any]],
) -> dict[str, int]:
    ergebnis = {
        "verarbeitet": len(datensaetze),
        "gespeichert": 0,
        "deaktiviert": 0,
        "fehlerhaft": 0,
    }
    gelieferte_ids: set[str] = set()

    for datensatz in datensaetze:
        externe_id = str(
            datensatz.get("ziel_externe_id")
            or ""
        ).strip()
        if externe_id:
            gelieferte_ids.add(externe_id)

        geraet_id = _externes_geraet_speichern(
            datenquelle_id=datenquelle_id,
            quelle=quelle,
            datensatz={
                **datensatz,
                "ziel_typ": "geraet",
            },
        )
        if geraet_id is None:
            ergebnis["fehlerhaft"] += 1
            continue

        ergebnis["gespeichert"] += 1

    if gelieferte_ids:
        with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
            verbindung.row_factory = sqlite3.Row
            vorhandene_geraete = verbindung.execute(
                """
                SELECT id, externe_id
                FROM geraete
                WHERE datenquelle_id = ?
                  AND quelle = ?
                  AND status = 'aktiv'
                  AND TRIM(COALESCE(externe_id, '')) != ''
                """,
                (datenquelle_id, quelle),
            ).fetchall()

            zu_deaktivierende_ids = []
            for zeile in vorhandene_geraete:
                externe_id = str(
                    zeile["externe_id"] or ""
                ).strip()
                if externe_id not in gelieferte_ids:
                    zu_deaktivierende_ids.append(
                        int(zeile["id"])
                    )

            for start in range(0, len(zu_deaktivierende_ids), 400):
                teilmenge = zu_deaktivierende_ids[start:start + 400]
                platzhalter = ", ".join("?" for _ in teilmenge)
                cursor = verbindung.execute(
                    f"""
                    UPDATE geraete
                    SET status = 'inaktiv',
                        zuletzt_synchronisiert = DATETIME('now')
                    WHERE id IN ({platzhalter})
                    """,
                    teilmenge,
                )
                ergebnis["deaktiviert"] += max(0, cursor.rowcount)

    return ergebnis


def _vorbereitete_lizenz_suchen(
    *,
    datenquelle_id: int | str,
    lizenzname: str,
    anbieter: str,
) -> dict[str, Any] | None:
    """
    Sucht eine noch nicht mit einer externen ID
    verbundene Lizenz derselben Datenquelle.

    Eine automatische Verbindung ist nur erlaubt,
    wenn Name und Anbieter exakt übereinstimmen und
    genau ein Treffer existiert.
    """
    try:
        datenquelle_id = int(
            datenquelle_id
        )
    except (TypeError, ValueError):
        return None

    lizenzname = str(
        lizenzname or ""
    ).strip()

    anbieter = str(
        anbieter or ""
    ).strip()

    if not lizenzname:
        return None

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        if anbieter:
            zeilen = verbindung.execute(
                """
                SELECT
                    id,
                    name,
                    anbieter,
                    anzahl,
                    externe_id,
                    status,
                    datenquelle,
                    datenquelle_id
                FROM lizenzen
                WHERE datenquelle_id = ?
                  AND TRIM(
                      COALESCE(externe_id, '')
                  ) = ''
                  AND LOWER(TRIM(name)) = LOWER(?)
                  AND LOWER(TRIM(
                      COALESCE(anbieter, '')
                  )) = LOWER(?)
                ORDER BY id
                LIMIT 2
                """,
                (
                    datenquelle_id,
                    lizenzname,
                    anbieter,
                ),
            ).fetchall()

        else:
            zeilen = verbindung.execute(
                """
                SELECT
                    id,
                    name,
                    anbieter,
                    anzahl,
                    externe_id,
                    status,
                    datenquelle,
                    datenquelle_id
                FROM lizenzen
                WHERE datenquelle_id = ?
                  AND TRIM(
                      COALESCE(externe_id, '')
                  ) = ''
                  AND LOWER(TRIM(name)) = LOWER(?)
                ORDER BY id
                LIMIT 2
                """,
                (
                    datenquelle_id,
                    lizenzname,
                ),
            ).fetchall()

    if len(zeilen) != 1:
        return None

    return dict(
        zeilen[0]
    )


def rest_datenquelle_sync_vorschau(
    datenquelle_id: int | str,
) -> dict[str, Any]:
    abruf = rest_datenquelle_datensaetze_laden(
        datenquelle_id
    )

    datenquellen_schluessel = (
        _datenquellen_schluessel(
            datenquelle_id
        )
    )

    ergebnis_datensaetze = []
    anzahl_neu = 0
    anzahl_aktualisieren = 0
    anzahl_unveraendert = 0
    anzahl_fehlerhaft = 0

    for datensatz in abruf["datensaetze"]:
        lizenzname = str(
            datensatz.get("lizenzname")
            or ""
        ).strip()

        externe_id = str(
            datensatz.get("externe_id")
            or ""
        ).strip()

        if not lizenzname or not externe_id:
            anzahl_fehlerhaft += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "aktion": "fehlerhaft",
                    "meldung": (
                        "Lizenzname oder externe ID "
                        "fehlt."
                    ),
                }
            )

            continue

        vorhanden = _vorhandene_lizenz_suchen(
            externe_id,
            datenquelle_id,
            datenquellen_schluessel,
        )

        automatisch_verbunden = False

        if vorhanden is None:
            vorhanden = _vorbereitete_lizenz_suchen(
                datenquelle_id=datenquelle_id,
                lizenzname=lizenzname,
                anbieter=str(
                    datensatz.get("anbieter")
                    or ""
                ).strip(),
            )

            automatisch_verbunden = (
                vorhanden is not None
            )

        if vorhanden is None:
            anzahl_neu += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "aktion": "neu",
                    "vorhandene_lizenz_id": None,
                    "automatisch_verbunden": False,
                }
            )

            continue

        verbrauch_geliefert = (
            datensatz.get("verbrauch") not in (None, "")
        )
        verbrauchsdatum_geliefert = bool(
            str(datensatz.get("verbrauchsdatum") or "").strip()
        )

        geaendert = any(
            [
                str(
                    vorhanden.get("name")
                    or ""
                ).strip()
                != lizenzname,
                str(
                    vorhanden.get("anbieter")
                    or ""
                ).strip()
                != str(
                    datensatz.get("anbieter")
                    or ""
                ).strip(),
                int(
                    vorhanden.get("anzahl")
                    or 0
                )
                != int(
                    datensatz.get("anzahl")
                    or 0
                ),
                verbrauch_geliefert
                and vorhanden.get("externer_verbrauch")
                != datensatz.get("verbrauch"),
                verbrauchsdatum_geliefert
                and str(vorhanden.get("verbrauch_gemeldet_am") or "").strip()
                != str(datensatz.get("verbrauchsdatum") or "").strip(),
                str(vorhanden.get("startdatum") or "").strip()
                != str(datensatz.get("startdatum") or "").strip(),
                str(vorhanden.get("ablaufdatum") or "").strip()
                != str(datensatz.get("ablaufdatum") or "").strip(),
                str(vorhanden.get("externer_produktschluessel") or "").strip()
                != str(datensatz.get("produktschluessel") or "").strip(),
                str(vorhanden.get("zuweisungsart") or "benutzer").strip()
                != str(datensatz.get("ziel_typ") or "benutzer").strip(),
                str(
                    vorhanden.get("status")
                    or ""
                ).strip()
                != str(
                    datensatz.get("status")
                    or ""
                ).strip(),
            ]
        )

        if geaendert:
            anzahl_aktualisieren += 1
            aktion = "aktualisieren"
        else:
            anzahl_unveraendert += 1
            aktion = "unveraendert"

        ergebnis_datensaetze.append(
            {
                **datensatz,
                "aktion": aktion,
                "vorhandene_lizenz_id": (
                    vorhanden["id"]
                ),
                "automatisch_verbunden": (
                    automatisch_verbunden
                ),
            }
        )

    return {
        "datenquelle_id": (
            abruf["datenquelle_id"]
        ),
        "datenquelle_name": (
            abruf["datenquelle_name"]
        ),
        "neu": anzahl_neu,
        "aktualisieren": (
            anzahl_aktualisieren
        ),
        "unveraendert": (
            anzahl_unveraendert
        ),
        "fehlerhaft": (
            anzahl_fehlerhaft
        ),
        "datensaetze": (
            ergebnis_datensaetze
        ),
    }


def rest_datenquelle_synchronisieren(
    datenquelle_id: int | str,
    ausgeloest_durch: str = "manuell",
) -> dict[str, Any]:
    """
    Übernimmt die normalisierten REST-Datensätze
    in die lokale Lizenzverwaltung und protokolliert
    den Synchronisationslauf.
    """
    try:
        datenquelle_id_int = int(
            datenquelle_id
        )
    except (TypeError, ValueError) as fehler:
        raise RestSyncFehler(
            "Die Datenquellen-ID ist ungültig."
        ) from fehler

    try:
        lauf_id = synchronisationslauf_starten(
            datenquelle_id_int,
            ausgeloest_durch=ausgeloest_durch,
        )

    except SynchronisationLaeuftBereits as fehler:
        raise RestSyncFehler(
            str(fehler)
        ) from fehler

    angelegt = 0
    aktualisiert = 0
    deaktiviert = 0
    unveraendert = 0
    fehlerhaft = 0
    meldungen = []

    try:
        vorschau = rest_datenquelle_sync_vorschau(
            datenquelle_id_int
        )

        datenquellen_schluessel = (
            _datenquellen_schluessel(
                datenquelle_id_int
            )
        )

        try:
            reconciliation = lizenzdaten_abgleichen(
                datenquelle_id=datenquelle_id_int,
                datenquellen_schluessel=(
                    datenquellen_schluessel
                ),
                datensaetze=vorschau["datensaetze"],
                beschreibung=(
                    "Automatisch über REST-API "
                    "synchronisiert."
                ),
                anzahl_bereinigen=(
                    _anzahl_bereinigen
                ),
                status_bereinigen=(
                    _status_bereinigen
                ),
            )
        except ReconciliationFehler as fehler:
            raise RestSyncFehler(
                str(fehler)
            ) from fehler

        angelegt = reconciliation[
            "angelegt"
        ]
        aktualisiert = reconciliation[
            "aktualisiert"
        ]
        deaktiviert = reconciliation[
            "deaktiviert"
        ]
        unveraendert = reconciliation[
            "unveraendert"
        ]
        fehlerhaft = reconciliation[
            "fehlerhaft"
        ]
        meldungen = reconciliation[
            "meldungen"
        ]

        zuweisungen_ergebnis = {
            "aktiv": False,
            "verarbeitet": 0,
            "neu_zugewiesen": 0,
            "reaktiviert": 0,
            "bereits_aktiv": 0,
            "deaktiviert": 0,
            "nicht_gefunden": 0,
            "mehrdeutig": 0,
            "fehlerhaft": 0,
            "deaktiviert_erfasst": 0,
            "ohne_email_ignoriert": 0,
            "meldungen": [],
            "konflikte": [],
        }

        zuweisungen_abruf = (
            rest_datenquelle_zuweisungen_laden(
                datenquelle_id_int
            )
        )

        if zuweisungen_abruf.get("aktiv"):
            if zuweisungen_abruf.get("modus") == "geraetebestand":
                zuweisungen_ergebnis["geraetebestand"] = (
                    _externer_geraetebestand_speichern(
                        datenquelle_id=datenquelle_id_int,
                        quelle=datenquellen_schluessel,
                        datensaetze=zuweisungen_abruf["datensaetze"],
                    )
                )
            else:
                zuordnung = _zuweisungen_lizenzen_zuordnen(
                    datensaetze=zuweisungen_abruf["datensaetze"],
                    datenquelle_id=datenquelle_id_int,
                    datenquellen_schluessel=datenquellen_schluessel,
                )

                zuweisungen_ergebnis["aktiv"] = True
                zuweisungen_ergebnis["verarbeitet"] = (
                    zuweisungen_abruf.get(
                        "anzahl_datensaetze",
                        0,
                    )
                )

                nicht_zugeordnet = zuordnung["nicht_zugeordnet"]
                if nicht_zugeordnet:
                    anzahl_nicht_zugeordnet = len(nicht_zugeordnet)
                    zuweisungen_ergebnis["fehlerhaft"] += (
                        anzahl_nicht_zugeordnet
                    )
                    meldung = (
                        f"{anzahl_nicht_zugeordnet} Benutzer oder Geräte "
                        "konnten keiner eindeutigen Lizenz zugeordnet werden."
                    )
                    zuweisungen_ergebnis["meldungen"].append({
                        "meldung": meldung,
                    })
                    zuweisungen_ergebnis["konflikte"].append({
                        "typ": "lizenzzuordnung_nicht_eindeutig",
                        "anzahl_zuweisungen": anzahl_nicht_zugeordnet,
                        "meldung": (
                            "Für diese Einträge gibt es mehrere mögliche "
                            "Lizenzen. Bitte die Zuordnung der Datenquelle prüfen."
                        ),
                    })

                for gruppe in zuordnung["gruppen"]:
                    lizenz = gruppe["lizenz"]
                    ziel_typ = gruppe["ziel_typ"]
                    ziel_datensaetze = gruppe["datensaetze"]

                    if ziel_typ == "geraet":
                        ergebnis = _externe_geraetezuweisungen_speichern(
                            lizenz_id=lizenz["id"],
                            datenquelle_id=datenquelle_id_int,
                            quelle=datenquellen_schluessel,
                            datensaetze=ziel_datensaetze,
                        )
                    else:
                        ergebnis = externe_zuweisungen_speichern(
                            lizenz_id=lizenz["id"],
                            quelle=datenquellen_schluessel,
                            datensaetze=ziel_datensaetze,
                            vollstaendiger_abzug=True,
                        )

                    for schluessel in [
                        "neu_zugewiesen",
                        "reaktiviert",
                        "bereits_aktiv",
                        "deaktiviert",
                        "nicht_gefunden",
                        "mehrdeutig",
                        "fehlerhaft",
                        "deaktiviert_erfasst",
                        "ohne_email_ignoriert",
                    ]:
                        zuweisungen_ergebnis[schluessel] += int(
                            ergebnis.get(schluessel, 0) or 0
                        )

                    for eintrag in ergebnis.get("datensaetze", []):
                        konflikt = eintrag.get("konflikt")
                        if konflikt:
                            zuweisungen_ergebnis["konflikte"].append({
                                **konflikt,
                                "lizenzname": lizenz.get("name"),
                            })

                    if "erfolgreich" in ergebnis and not ergebnis.get(
                        "erfolgreich"
                    ):
                        zuweisungen_ergebnis["meldungen"].append({
                            "lizenzname": lizenz.get("name"),
                            "meldung": ergebnis.get(
                                "meldung",
                                "Die Zuordnungen konnten nicht vollständig "
                                "verarbeitet werden.",
                            ),
                        })

        erfolgsmeldung = (
            "Synchronisierung erfolgreich: "
            f"{angelegt} angelegt, "
            f"{aktualisiert} aktualisiert, "
            f"{deaktiviert} deaktiviert, "
            f"{unveraendert} unverändert, "
            f"{fehlerhaft} fehlerhaft."
        )

        if zuweisungen_ergebnis.get("aktiv"):
            erfolgsmeldung += (
                " Zuweisungen: "
                f"{zuweisungen_ergebnis['neu_zugewiesen']} "
                "neu, "
                f"{zuweisungen_ergebnis['reaktiviert']} "
                "reaktiviert, "
                f"{zuweisungen_ergebnis['bereits_aktiv']} "
                "bereits aktiv, "
                f"{zuweisungen_ergebnis['deaktiviert']} "
                "deaktiviert, "
                f"{zuweisungen_ergebnis['fehlerhaft']} "
                "fehlerhaft."
            )
            if zuweisungen_ergebnis["deaktiviert_erfasst"]:
                erfolgsmeldung += (
                    f" {zuweisungen_ergebnis['deaktiviert_erfasst']} nicht mehr "
                    "im Benutzerbestand gefundene Personen wurden als "
                    "deaktiviert mit Lizenz erfasst."
                )
            if zuweisungen_ergebnis["ohne_email_ignoriert"]:
                erfolgsmeldung += (
                    f" {zuweisungen_ergebnis['ohne_email_ignoriert']} technische "
                    "Datensätze ohne E-Mail wurden ignoriert."
                )

        geraetebestand_ergebnis = zuweisungen_ergebnis.get(
            "geraetebestand"
        ) or {}
        if geraetebestand_ergebnis:
            erfolgsmeldung += (
                " Gerätebestand: "
                f"{geraetebestand_ergebnis.get('gespeichert', 0)} "
                "übernommen"
            )
            if geraetebestand_ergebnis.get("deaktiviert"):
                erfolgsmeldung += (
                    f", {geraetebestand_ergebnis['deaktiviert']} "
                    "nicht mehr gelieferte Geräte deaktiviert"
                )
            if geraetebestand_ergebnis.get("fehlerhaft"):
                erfolgsmeldung += (
                    f", {geraetebestand_ergebnis['fehlerhaft']} "
                    "Einträge übersprungen"
                )
            erfolgsmeldung += "."

        fehlerdetails = None

        if meldungen:
            fehlerzeilen = []

            for eintrag in meldungen:
                externe_id = str(
                    eintrag.get("externe_id")
                    or "Ohne externe ID"
                ).strip()

                grund = str(
                    eintrag.get("meldung")
                    or "Unbekannter Fehler"
                ).strip()

                fehlerzeilen.append(
                    f"{externe_id}: {grund}"
                )

            fehlerdetails = "\n".join(
                fehlerzeilen
            )

        synchronisationslauf_erfolgreich_beenden(
            lauf_id=lauf_id,
            angelegt=angelegt,
            aktualisiert=aktualisiert,
            deaktiviert=deaktiviert,
            unveraendert=unveraendert,
            fehlerhaft=fehlerhaft,
            meldung=erfolgsmeldung,
            fehlerdetails=fehlerdetails,
            zuweisungen_verarbeitet=(
                zuweisungen_ergebnis.get("verarbeitet", 0)
            ),
            zuweisungen_neu=(
                zuweisungen_ergebnis.get("neu_zugewiesen", 0)
            ),
            zuweisungen_reaktiviert=(
                zuweisungen_ergebnis.get("reaktiviert", 0)
            ),
            zuweisungen_bereits_aktiv=(
                zuweisungen_ergebnis.get("bereits_aktiv", 0)
            ),
            zuweisungen_deaktiviert=(
                zuweisungen_ergebnis.get("deaktiviert", 0)
            ),
            zuweisungen_fehlerhaft=(
                zuweisungen_ergebnis.get("fehlerhaft", 0)
            ),
            zuweisungen_nicht_gefunden=(
                zuweisungen_ergebnis.get("nicht_gefunden", 0)
            ),
            zuweisungen_mehrdeutig=(
                zuweisungen_ergebnis.get("mehrdeutig", 0)
            ),
            konfliktdetails=(
                zuweisungen_ergebnis.get("konflikte", [])
            ),
        )

        erfolgreiche_synchronisation_speichern(
            datenquelle_id_int,
            lauf_id=lauf_id,
            meldung=erfolgsmeldung,
        )

        return {
            "datenquelle_id": (
                datenquelle_id_int
            ),
            "datenquelle_name": (
                vorschau["datenquelle_name"]
            ),
            "angelegt": angelegt,
            "aktualisiert": aktualisiert,
            "deaktiviert": deaktiviert,
            "unveraendert": unveraendert,
            "fehlerhaft": fehlerhaft,
            "meldungen": meldungen,
            "zuweisungen": zuweisungen_ergebnis,
        }

    except Exception as fehler:
        fehlermeldung = str(fehler).strip()

        if not fehlermeldung:
            fehlermeldung = (
                "Unbekannter Fehler bei der "
                "REST-Synchronisierung."
            )

        try:
            synchronisationslauf_fehlerhaft_beenden(
                lauf_id,
                fehlermeldung,
            )
        except Exception:
            pass

        try:
            fehler_speichern(
                datenquelle_id_int,
                fehlermeldung,
                lauf_id=lauf_id,
            )
        except Exception:
            pass

        if isinstance(fehler, RestSyncFehler):
            raise

        raise RestSyncFehler(
            "Die Synchronisierung wurde "
            "abgebrochen. Es wurden keine "
            "Änderungen gespeichert."
        ) from fehler
