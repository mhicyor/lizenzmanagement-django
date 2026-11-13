import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone as datetime_timezone

from rest_api_service import (
    RestApiFehler,
    ALLE_BENUTZER_MARKER,
    rest_api_endpunkt_testen,
    rest_api_verbindung_testen,
)
from rest_anbieterprofil_service import (
    assistent_standardwerte_anwenden,
    oeffentliche_assistent_profile,
)

from urllib.parse import urlencode
from lizenzprodukt_zuordnung_service import (
    offene_lizenzprodukt_zuordnungen_laden,
    produktkandidaten_mit_entscheidungen_laden,
)
from gruppen_mapping_service import (
    gruppen_mapping_entscheidung_speichern,
)
from lizenz_erkennungsregel_service import (
    lizenz_erkennungsregel_speichern,
)

from sync_orchestrator_service import (
    SyncOrchestratorFehler,
    datenquelle_synchronisieren,
)

from lizenz_logik_service import (
    ermittle_lizenz_ziel_typ,
    gespeicherte_datenquelle_laden,
    ist_datenquellen_lizenz,
    ist_manuell_verwaltete_lizenz,
)
from django.conf import settings
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.timezone import localtime, now
from django.http import JsonResponse

from datenquelle_service import (
    DatenquelleFehler,
    ERLAUBTE_AUTOMATISCHE_SYNC_INTERVALLE,
    alte_csv_temp_dateien_bereinigen,
    automatische_synchronisation_speichern,
    csv_datenquelle_aktualisieren,
    csv_datenquelle_speichern,
    datenquelle_deaktivieren,
    datenquelle_laden,
    datenquelle_loeschen,
    datenquelle_reaktivieren,
    datenquelle_mit_geheimnissen_laden,
    lade_eingerichtete_datenquellen,
    rest_datenquelle_aktualisieren,
    rest_datenquelle_speichern,
)

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

PROJEKT_ORDNER = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

if PROJEKT_ORDNER not in sys.path:
    sys.path.append(PROJEKT_ORDNER)


from anbieter_service import (
    lade_anbieter,
    lade_anbieter_details,
    anbieter_hinzufuegen,
    anbieter_aktualisieren,
    anbieter_deaktivieren,
    anbieter_reaktivieren,
    anbieter_loeschen,
    anzahl_lizenzen_mit_anbieter,
)
from lizenz_modell_service import (
    lade_lizenz_modelle,
    lade_lizenz_modell,
    standard_lizenzmodell_id_laden,
)

from zuweisungsziel_service import (
    lade_zuweisungsziel_typen,
    lade_zuweisungsziel_typ,
    standard_zuweisungszieltyp_id_laden,
)

from database import verbindung_oeffnen
from sync_config_service import pruefe_sync_konfiguration
from sync_status_service import (
    abruf_erlaubt,
    status_laden,
    synchronisationslaeufe_laden,
)

from geraete_service import (
    lade_geraete_uebersicht,
    geraet_hinzufuegen,
    lade_geraet_details,
    geraet_aktualisieren,
    geraet_loeschen,
)

from server_service import (
    lade_server_uebersicht,
    server_hinzufuegen,
    lade_server_details,
    server_aktualisieren,
    server_loeschen,
)

from lizenz_service import (
    lade_lizenzen_uebersicht,
    lade_lizenzuebersicht,
    lade_kostenuebersicht,
    lizenz_hinzufuegen,
    lizenz_aktualisieren,
    weise_lizenz_zu,
    weise_lizenz_an_ziel_zu,
    lade_lizenz_details,
    lade_lizenz_ziele,
    entferne_lizenzzuweisung,
    entferne_lizenzzuweisung_flexibel,
    lizenz_loeschen,
    lade_entfernte_lizenz_ziele,
)

from lizenz_kategorie_service import (
    lade_lizenz_kategorien,
    lade_lizenz_kategorie,
    lizenz_kategorie_hinzufuegen,
    lizenz_kategorie_aktualisieren,
    lizenz_kategorie_deaktivieren,
    lizenz_kategorie_reaktivieren,
    lizenz_kategorie_loeschen,
    anzahl_lizenzen_mit_kategorie,
)
from lizenz_klassifikation import (
    lizenzklasse_anzeigename,
    zuweisungsart_anzeigename,
    kostenmodell_anzeigename,
    technologiebereich_anzeigename,
)

from benutzer_service import (
    lade_aktive_benutzer_ids_fuer_lizenz,
    lade_aktive_benutzer_ids_mit_lizenz,
    lade_benutzer_exportdaten,
    lade_benutzer_uebersicht,
    benutzer_hinzufuegen,
    lade_benutzer_details,
)

from pdf_export_service import benutzerliste_pdf_erstellen
from csv_export_service import benutzerliste_csv_erstellen
from csv_import_service import (
    CsvImportFehler,
    csv_datei_analysieren,
)

from auswertung_service import (
    lade_dashboard_statistik,
    lade_lizenzkategorien_statistik,
    lade_ablaufende_lizenzen,
    lade_deaktivierte_benutzer_mit_lizenzen,
)

from .view_helpers import (
    _deaktivierte_benutzer_gruppieren,
    _eindeutige_spaltenwerte,
    _eintraege_filtern,
    _formularfelder_aus_post,
    _ist_modal_anfrage,
    _modal_darstellung,
    _modal_nachricht_response,
    modal_parent_reload_response,
)
from .stammdaten_views import (
    anbieter_bearbeiten_view,
    anbieter_deaktivieren_view,
    anbieter_hinzufuegen_view,
    anbieter_liste_view,
    anbieter_loeschen_view,
    anbieter_reaktivieren_view,
    lizenzkategorie_bearbeiten_view,
    lizenzkategorie_deaktivieren_view,
    lizenzkategorie_hinzufuegen_view,
    lizenzkategorie_loeschen_view,
    lizenzkategorie_reaktivieren_view,
    lizenzkategorien_view,
)
from .reporting_views import (
    ablaufende_lizenzen,
    auswertungen,
    kostenbericht,
    lizenzbestand,
)
from .bestand_views import (
    geraet_bearbeiten_view,
    geraet_hinzufuegen_view,
    geraet_lizenz_zuweisen,
    geraet_loeschen_view,
    geraete_liste,
    lizenz_zuweisung_entfernen_view,
    server_bearbeiten_view,
    server_hinzufuegen_view,
    server_liste,
    server_lizenz_zuweisen,
    server_loeschen_view,
)
from .benutzer_views import (
    benutzer_detail,
    benutzer_export_csv,
    benutzer_export_pdf,
    benutzer_hinzufuegen_view,
    benutzer_liste,
    deaktivierte_benutzer,
    deaktivierte_benutzer_export_csv,
    deaktivierte_benutzer_export_pdf,
    lizenzzuweisung_entfernen,
)
from .auth_views import login_view, logout_view, startseite
from .integration_views import (
    ad_synchronisation,
    adobe_import,
)
from .audit_service import (
    lizenz_bearbeitung_protokollieren,
    lizenz_erstellt_protokollieren,
    lizenz_historie_laden,
)


@login_required
def lizenzen_liste(request):
    suchtext = request.GET.get(
        "suche",
        ""
    ).strip().lower()

    schnellfilter = request.GET.get(
        "filter",
        "alle"
    ).strip()

    alle_lizenzen = lade_lizenzen_uebersicht()
    lizenzen = []

    # Nur aktive und nicht archivierte Kategorien
    # für den Filter laden.
    kategorien_roh = lade_lizenz_kategorien(
        nur_aktive=True
    )

    aktive_filter_kategorien = []

    for kategorie in kategorien_roh:
        kategorie_id = kategorie[0]

        kategorie_name = (
            kategorie[1]
            if len(kategorie) > 1 and kategorie[1]
            else ""
        )

        kategorie_slug = (
            kategorie[7]
            if len(kategorie) > 7 and kategorie[7]
            else ""
        )

        archiviert = (
            bool(kategorie[9])
            if len(kategorie) > 9
            else False
        )

        if (
            not kategorie_name
            or not kategorie_slug
            or archiviert
        ):
            continue

        aktive_filter_kategorien.append({
            "id": kategorie_id,
            "name": kategorie_name,
            "slug": kategorie_slug,
        })

    kategorie_filter_slugs = {
        kategorie["slug"]
        for kategorie in aktive_filter_kategorien
    }

    kategorie_filter_aktiv = (
        schnellfilter in kategorie_filter_slugs
    )

    ausgewaehlte_kategorie = ""

    for kategorie in aktive_filter_kategorien:
        if kategorie["slug"] == schnellfilter:
            ausgewaehlte_kategorie = (
                kategorie["name"]
            )
            break

    for lizenz in alle_lizenzen:
        kostenmodell = (
            lizenz[10]
            if len(lizenz) > 10 and lizenz[10]
            else "fortlaufend"
        )

        kategorie_id = (
            lizenz[12]
            if len(lizenz) > 12
            else None
        )

        kategorie_name = (
            lizenz[13]
            if len(lizenz) > 13 and lizenz[13]
            else ""
        )

        kategorie_slug = (
            lizenz[14]
            if len(lizenz) > 14 and lizenz[14]
            else ""
        )

        beschreibung = (
            lizenz[15]
            if len(lizenz) > 15 and lizenz[15]
            else ""
        )

        datenquelle = (
            lizenz[16]
            if len(lizenz) > 16 and lizenz[16]
            else "manuell"
        )

        api_sync_aktiv = (
            lizenz[17]
            if len(lizenz) > 17
            else 0
        )

        externe_id = (
            lizenz[18]
            if len(lizenz) > 18 and lizenz[18]
            else ""
        )

        status = (
            lizenz[19]
            if len(lizenz) > 19 and lizenz[19]
            else "aktiv"
        )

        kategorie_beschreibung = (
            lizenz[20]
            if len(lizenz) > 20 and lizenz[20]
            else ""
        )

        kategorie_typische_nutzung = (
            lizenz[21]
            if len(lizenz) > 21 and lizenz[21]
            else ""
        )

        suchbasis = " ".join([
            str(lizenz[0]).lower(),
            str(lizenz[1]).lower(),
            str(lizenz[2]).lower(),
            str(lizenz[3]).lower(),
            str(lizenz[5]).lower(),
            str(lizenz[6]).lower(),
            str(lizenz[7]).lower(),
            str(kostenmodell).lower(),
            str(kategorie_name).lower(),
            str(kategorie_slug).lower(),
            str(beschreibung).lower(),
            str(datenquelle).lower(),
            str(externe_id).lower(),
            str(status).lower(),
            str(kategorie_beschreibung).lower(),
            str(kategorie_typische_nutzung).lower(),
        ])

        passt_suche = (
            not suchtext
            or suchtext in suchbasis
        )

        passt_filter = True

        if schnellfilter == "fortlaufend":
            passt_filter = (
                kostenmodell in {"fortlaufend", "monatlich"}
            )

        elif schnellfilter == "jaehrlich":
            passt_filter = (
                kostenmodell in {"jaehrlich", "jährlich"}
            )

        elif schnellfilter == "einmalig":
            passt_filter = (
                kostenmodell == "einmalig"
            )

        elif schnellfilter == "api":
            passt_filter = (
                datenquelle != "manuell"
                or int(api_sync_aktiv or 0) == 1
            )

        elif schnellfilter == "manuell":
            passt_filter = (
                datenquelle == "manuell"
                and int(api_sync_aktiv or 0) == 0
            )

        elif kategorie_filter_aktiv:
            passt_filter = (
                kategorie_slug == schnellfilter
            )

        if passt_suche and passt_filter:
            lizenzen.append((
                lizenz[0],                              # 0 ID
                lizenz[1],                              # 1 Name
                lizenz[2],                              # 2 Anbieter
                lizenz[3],                              # 3 Anzahl
                lizenz[4],                              # 4 Lizenztyp
                lizenz[5],                              # 5 Kosten
                lizenz[6],                              # 6 Ablaufdatum
                lizenz[7],                              # 7 Verlängerungsdatum
                "",                                     # 8 Alte Lizenzklasse
                "",                                     # 9 Alte Zuweisungsart
                kostenmodell_anzeigename(
                    kostenmodell
                ),                                      # 10 Kostenmodell
                "",                                     # 11 Technologiebereich
                kategorie_id,                           # 12 Kategorie-ID
                kategorie_name,                         # 13 Kategorie-Name
                kategorie_slug,                         # 14 Kategorie-Slug
                beschreibung,                           # 15 Beschreibung
                datenquelle,                            # 16 Datenquelle
                api_sync_aktiv,                         # 17 API-Sync
                externe_id,                             # 18 Externe ID
                status,                                 # 19 Status
                kategorie_beschreibung,                 # 20 Kategoriebeschreibung
                kategorie_typische_nutzung,             # 21 Typische Nutzung
            ))

    return render(
        request,
        "lizenzen/startseite.html",
        {
            "lizenzen": lizenzen,
            "suchtext": suchtext,
            "schnellfilter": schnellfilter,
            "aktive_filter_kategorien": (
                aktive_filter_kategorien
            ),
            "ausgewaehlte_kategorie": (
                ausgewaehlte_kategorie
            ),
        }
    )


@login_required
def dashboard(request):
    statistik = lade_dashboard_statistik()

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            l.id,
            l.name,
            l.anbieter,
            l.anzahl,
            COALESCE(
                l.externer_verbrauch,
                COALESCE(b.anzahl, 0) + COALESCE(g.anzahl, 0)
            ) AS vergeben,
            l.kosten,
            l.kostenmodell,
            COALESCE(b.anzahl, 0) + COALESCE(g.anzahl, 0)
                AS lokal_zugewiesen,
            l.verbrauch_gemeldet_am,
            l.externer_verbrauch
        FROM lizenzen l
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM zuweisungen
            WHERE status = 'aktiv'
            GROUP BY lizenz_id
        ) b ON b.lizenz_id = l.id
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM lizenz_zuweisungen
            WHERE status = 'aktiv' AND ziel_typ != 'benutzer'
            GROUP BY lizenz_id
        ) g ON g.lizenz_id = l.id
        ORDER BY l.name
    """)

    lizenzdaten = cursor.fetchall()
    verbindung.close()

    reporting = []

    for lizenz in lizenzdaten:
        lizenz_id = lizenz[0]
        name = lizenz[1]
        anbieter = lizenz[2]
        gesamt = lizenz[3] or 0
        vergeben = lizenz[4] or 0
        kosten_je_lizenz = lizenz[5] or 0
        kostenmodell = lizenz[6] or "fortlaufend"
        # Aeltere Aufrufer und einzelne Tests liefern weiterhin das bisherige
        # sieben Spalten breite Format. In diesem Fall entspricht der bereits
        # berechnete Verbrauch zugleich dem lokalen Stand.
        lokal_zugewiesen = (
            lizenz[7] or 0
            if len(lizenz) > 7
            else vergeben
        )
        verbrauch_gemeldet_am = (
            lizenz[8]
            if len(lizenz) > 8
            else None
        )
        hat_externen_verbrauch = (
            lizenz[9] is not None
            if len(lizenz) > 9
            else False
        )

        try:
            kosten_je_lizenz = float(
                str(kosten_je_lizenz).replace(",", ".")
            )
        except (TypeError, ValueError):
            kosten_je_lizenz = 0.0

        frei = max(0, gesamt - vergeben)
        auslastung = (
            min(
                100,
                round(
                    vergeben
                    / gesamt
                    * 100
                ),
            )
            if gesamt
            else 0
        )

        if kostenmodell in {"fortlaufend", "monatlich"}:
            monatskosten_je_lizenz = kosten_je_lizenz
        elif kostenmodell in {"jaehrlich", "jährlich"}:
            monatskosten_je_lizenz = kosten_je_lizenz / 12
        elif kostenmodell in {
            "einmalig",
            "kostenlos",
            "volumenvertrag",
        }:
            monatskosten_je_lizenz = 0
        else:
            monatskosten_je_lizenz = kosten_je_lizenz

        gesamt_kosten = gesamt * monatskosten_je_lizenz
        jahreskosten = gesamt_kosten * 12
        jahreskosten_je_lizenz = monatskosten_je_lizenz * 12

        reporting.append({
            "id": lizenz_id,
            "name": name,
            "anbieter": anbieter,
            "gesamt": gesamt,
            "vergeben": vergeben,
            "lokal_zugewiesen": lokal_zugewiesen,
            "verbrauch_gemeldet_am": verbrauch_gemeldet_am,
            "hat_externen_verbrauch": hat_externen_verbrauch,
            "abweichung": abs(vergeben - lokal_zugewiesen),
            "frei": frei,
            "auslastung": auslastung,
            "status": (
                "Voll belegt"
                if gesamt and frei == 0
                else "Fast ausgelastet"
                if auslastung >= 80
                else "Kapazität frei"
            ),
            "status_klasse": (
                "voll"
                if gesamt and frei == 0
                else "warnung"
                if auslastung >= 80
                else "frei"
            ),
            "kosten": f"{kosten_je_lizenz:.2f}",
            "gesamt_kosten": f"{gesamt_kosten:.2f}",
            "jahreskosten": f"{jahreskosten:.2f}",
            "monatskosten_je_lizenz": (
                f"{monatskosten_je_lizenz:.2f}"
            ),
            "jahreskosten_je_lizenz": (
                f"{jahreskosten_je_lizenz:.2f}"
            ),
        })

    reporting.sort(
        key=lambda eintrag: float(
            eintrag["gesamt_kosten"]
        ),
        reverse=True,
    )

    gesamtsumme = sum(float(eintrag["gesamt_kosten"]) for eintrag in reporting)

    gesamt_lizenzen = int(
        statistik.get("gesamt_lizenzen", 0)
        or 0
    )
    vergebene_lizenzen = int(
        statistik.get("vergebene_lizenzen", 0)
        or 0
    )
    auslastung_gesamt = (
        min(
            100,
            round(
                vergebene_lizenzen
                / gesamt_lizenzen
                * 100
            ),
        )
        if gesamt_lizenzen
        else 0
    )

    ablaufende_lizenzen = lade_ablaufende_lizenzen(30)
    deaktivierte_benutzer = _deaktivierte_benutzer_gruppieren(
        lade_deaktivierte_benutzer_mit_lizenzen()
    )
    lizenzkategorien_statistik = lade_lizenzkategorien_statistik()

    return render(
        request,
        "lizenzen/dashboard.html",
        {
            "dashboard_kennzahlen": {
                "lizenztypen": statistik.get(
                    "anzahl_lizenztypen",
                    0,
                ),
                "gesamt": gesamt_lizenzen,
                "vergeben": vergebene_lizenzen,
                "frei": statistik.get(
                    "freie_lizenzen",
                    0,
                ),
                "aktive_benutzer": statistik.get(
                    "aktive_benutzer",
                    0,
                ),
                "auslastung": auslastung_gesamt,
                "monatskosten": (
                    f"{float(gesamtsumme):.2f}"
                ),
                "jahreskosten": (
                    f"{float(gesamtsumme) * 12:.2f}"
                ),
            },
            "reporting": reporting,
            "gesamtsumme": f"{float(gesamtsumme):.2f}",
            "ablaufende_lizenzen": ablaufende_lizenzen,
            "deaktivierte_benutzer": deaktivierte_benutzer,
            "lizenzkategorien_statistik": lizenzkategorien_statistik,
        }
    )
@login_required
@xframe_options_sameorigin
def lizenz_detail(request, lizenz_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    lizenz, benutzer, entfernte_benutzer = (
        lade_lizenz_details(lizenz_id)
    )

    if lizenz is None:
        return render(
            request,
            "lizenzen/lizenz_nicht_gefunden.html",
            {
                "ist_modal": ist_modal,
                "template_basis": template_basis,
            },
        )

    suchtext = request.GET.get(
        "suche",
        "",
    ).strip()

    ziel_typ = ermittle_lizenz_ziel_typ(
        lizenz
    )

    # -------------------------------------------------
    # Benutzer durchsuchen
    # -------------------------------------------------

    suchtext_klein = suchtext.lower()
    benutzer = _eintraege_filtern(
        benutzer,
        suchtext_klein,
    )
    entfernte_benutzer = _eintraege_filtern(
        entfernte_benutzer,
        suchtext_klein,
    )

    # -------------------------------------------------
    # Zielzuweisungen laden
    # -------------------------------------------------

    server_ziele = []
    geraete_ziele = []

    entfernte_server_ziele = []
    entfernte_geraete_ziele = []

    if ziel_typ == "server":
        server_ziele = lade_lizenz_ziele(
            lizenz_id,
            "server",
        )

        entfernte_server_ziele = (
            lade_entfernte_lizenz_ziele(
                lizenz_id,
                "server",
            )
        )

        benutzer = []
        entfernte_benutzer = []

    elif ziel_typ == "geraet":
        geraete_ziele = lade_lizenz_ziele(
            lizenz_id,
            "geraet",
        )

        entfernte_geraete_ziele = (
            lade_entfernte_lizenz_ziele(
                lizenz_id,
                "geraet",
            )
        )

        benutzer = []
        entfernte_benutzer = []

        geraete_ziele = _eintraege_filtern(
            geraete_ziele,
            suchtext_klein,
        )
        entfernte_geraete_ziele = _eintraege_filtern(
            entfernte_geraete_ziele,
            suchtext_klein,
        )

    # -------------------------------------------------
    # Datenquelle auflösen
    # -------------------------------------------------

    datenquelle = None
    datenquelle_name = "Manuell"

    gespeicherte_datenquelle = (
        gespeicherte_datenquelle_laden(
            lizenz,
            datenquelle_index=18,
        )
    )

    if gespeicherte_datenquelle != "manuell":
        try:
            datenquelle_id = int(
                gespeicherte_datenquelle
            )
        except (TypeError, ValueError):
            datenquelle_id = None

        if datenquelle_id is not None:
            datenquelle = datenquelle_laden(
                datenquelle_id
            )

        if datenquelle:
            datenquelle_name = (
                datenquelle.get("name")
                or "Datenquelle"
            )
        else:
            datenquelle_name = "Datenquelle"

    lizenz_anzeigenamen = {
        "lizenzklasse": lizenzklasse_anzeigename(
            lizenz[8]
        ),
        "zuweisungsart": zuweisungsart_anzeigename(
            lizenz[9]
        ),
        "kostenmodell": kostenmodell_anzeigename(
            lizenz[10]
        ),
        "technologiebereich": (
            technologiebereich_anzeigename(
                lizenz[11]
            )
        ),
    }

    return render(
        request,
        "lizenzen/lizenz_detail.html",
        {
            "lizenz": lizenz,
            "datenquelle": datenquelle,
            "datenquelle_name": datenquelle_name,
            "ziel_typ": ziel_typ,
            "benutzer": benutzer,
            "entfernte_benutzer": entfernte_benutzer,
            "server_ziele": server_ziele,
            "geraete_ziele": geraete_ziele,
            "entfernte_server_ziele": (
                entfernte_server_ziele
            ),
            "entfernte_geraete_ziele": (
                entfernte_geraete_ziele
            ),
            "lokale_zuweisungsanzahl": (
                len(geraete_ziele)
                if ziel_typ == "geraet"
                else len(server_ziele)
                if ziel_typ == "server"
                else len(benutzer)
            ),
            "suchtext": suchtext,
            "lizenz_anzeigenamen": (
                lizenz_anzeigenamen
            ),
            "lizenz_historie": lizenz_historie_laden(
                lizenz_id
            ),
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )

@login_required
@xframe_options_sameorigin
def lizenz_bearbeiten_view(request, lizenz_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    lizenz, _, _ = lade_lizenz_details(lizenz_id)

    kategorien_roh = lade_lizenz_kategorien(
        nur_aktive=True
    )

    kategorien = []

    for kategorie in kategorien_roh:
        kategorien.append({
            "id": kategorie[0],
            "name": kategorie[1],
            "beschreibung": kategorie[2],
            "lizenzlogik": (
                kategorie[3]
                if len(kategorie) > 3
                else ""
            ),
            "typische_zuordnung": (
                kategorie[4]
                if len(kategorie) > 4
                else ""
            ),
            "interne_lizenzklasse": (
                kategorie[5]
                if len(kategorie) > 5
                else "benutzer"
            ),
            "aktiv": (
                bool(kategorie[6])
                if len(kategorie) > 6
                else True
            ),
            "slug": (
                kategorie[7]
                if len(kategorie) > 7
                else ""
            ),
            "standard_zuweisungsart": (
                kategorie[8]
                if len(kategorie) > 8
                else "benutzer"
            ),
            "archiviert": (
                bool(kategorie[9])
                if len(kategorie) > 9
                else False
            ),
            "archiviert_am": (
                kategorie[10]
                if len(kategorie) > 10
                else ""
            ),
            "archivierungsgrund": (
                kategorie[11]
                if len(kategorie) > 11
                else ""
            ),
            "sortierung": (
                kategorie[12]
                if len(kategorie) > 12
                else 100
            ),
            "erstellt_am": (
                kategorie[13]
                if len(kategorie) > 13
                else ""
            ),
            "aktualisiert_am": (
                kategorie[14]
                if len(kategorie) > 14
                else ""
            ),
        })

    basis_context = {
        "lizenz": lizenz,
        "kategorien": kategorien,
        "anbieter_liste": lade_anbieter(
            nur_aktive=True
        ),
        "datenquellen_liste": (
            lade_eingerichtete_datenquellen()
        ),
        "fehler": "",
        "ist_modal": ist_modal,
        "template_basis": template_basis,
    }

    def fehler_anzeigen(meldung):
        context = basis_context.copy()
        context["fehler"] = meldung

        return render(
            request,
            "lizenzen/lizenz_bearbeiten.html",
            context,
        )

    if lizenz is None:
        return fehler_anzeigen(
            "Die ausgewählte Lizenz existiert nicht."
        )

    if request.method != "POST":
        return render(
            request,
            "lizenzen/lizenz_bearbeiten.html",
            basis_context,
        )

    name = request.POST.get(
        "name",
        "",
    ).strip()

    anbieter = request.POST.get(
        "anbieter",
        "",
    ).strip()

    beschreibung = request.POST.get(
        "beschreibung",
        "",
    ).strip()

    kategorie_id = request.POST.get(
        "kategorie_id",
        "",
    ).strip()

    anzahl_roh = request.POST.get(
        "anzahl",
        "",
    ).strip()

    kosten_roh = request.POST.get(
        "kosten",
        "",
    ).strip()

    kostenmodell = request.POST.get(
        "kostenmodell",
        "fortlaufend",
    ).strip().lower()

    ablaufdatum = request.POST.get(
        "ablaufdatum",
        "",
    ).strip()

    verlaengerungsdatum = request.POST.get(
        "verlaengerungsdatum",
        "",
    ).strip()

    datenquelle = request.POST.get(
        "datenquelle",
        "manuell",
    ).strip()

    externe_id = (
        str(lizenz[20]).strip()
        if len(lizenz) > 20 and lizenz[20]
        else ""
    )

    status = request.POST.get(
        "status",
        "aktiv",
    ).strip().lower()

    if not datenquelle:
        datenquelle = "manuell"

    if (
        not name
        or not anbieter
        or not anzahl_roh
        or not kosten_roh
    ):
        return fehler_anzeigen(
            "Bitte alle Pflichtfelder ausfüllen."
        )

    kategorie = None
    kategorie_id_int = None

    if kategorie_id:
        try:
            kategorie_id_int = int(
                kategorie_id
            )

        except (TypeError, ValueError):
            return fehler_anzeigen(
                "Bitte eine gültige Lizenzkategorie "
                "auswählen."
            )

        kategorie = lade_lizenz_kategorie(
            kategorie_id_int
        )

        if kategorie is None:
            return fehler_anzeigen(
                "Die ausgewählte Lizenzkategorie "
                "existiert nicht."
            )

        kategorie_aktiv = (
            bool(kategorie[6])
            if len(kategorie) > 6
            else True
        )

        kategorie_archiviert = (
            bool(kategorie[9])
            if len(kategorie) > 9
            else False
        )

        if not kategorie_aktiv:
            return fehler_anzeigen(
                "Deaktivierte Kategorien können nicht "
                "verwendet werden."
            )

        if kategorie_archiviert:
            return fehler_anzeigen(
                "Archivierte Kategorien können nicht "
                "verwendet werden."
            )

    if kostenmodell not in {
        "fortlaufend",
        "jaehrlich",
        "einmalig",
    }:
        return fehler_anzeigen(
            "Bitte ein gültiges Abrechnungsintervall "
            "auswählen."
        )

    erlaubte_statuswerte = {
        "aktiv",
        "inaktiv",
    }

    if status not in erlaubte_statuswerte:
        return fehler_anzeigen(
            "Bitte einen gültigen Lizenzstatus "
            "auswählen."
        )

    try:
        anzahl = int(
            anzahl_roh
        )

        if anzahl < 1:
            raise ValueError

    except (TypeError, ValueError):
        return fehler_anzeigen(
            "Die Anzahl muss eine ganze Zahl "
            "größer als 0 sein."
        )

    try:
        kosten = float(
            kosten_roh.replace(",", ".")
        )

        if kosten < 0:
            raise ValueError

    except (TypeError, ValueError):
        return fehler_anzeigen(
            "Die Kosten müssen eine gültige "
            "Zahl ab 0 sein."
        )

    if datenquelle == "manuell":
        datenquelle_id = None
        api_sync_aktiv = 0
        externe_id = ""

    else:
        eingerichtete_datenquellen = (
            lade_eingerichtete_datenquellen()
        )

        erlaubte_datenquellen_ids = {
            str(eintrag["id"])
            for eintrag in eingerichtete_datenquellen
            if eintrag.get("id") is not None
        }

        if (
            str(datenquelle)
            not in erlaubte_datenquellen_ids
        ):
            return fehler_anzeigen(
                "Die ausgewählte Datenquelle "
                "existiert nicht oder ist nicht "
                "mehr aktiv."
            )

        datenquelle_id = int(
            datenquelle
        )
        api_sync_aktiv = 1

    lizenztyp = name

    erlaubte_zieltypen = {
        "benutzer",
        "geraet",
        "server",
    }

    bisheriger_zieltyp = (
        ermittle_lizenz_ziel_typ(
            lizenz
        )
    )

    if (
        bisheriger_zieltyp
        not in erlaubte_zieltypen
    ):
        bisheriger_zieltyp = "benutzer"

    # Beim Bearbeiten beschreibt die Kategorie nur die fachliche
    # Einordnung. Die technische Zielart der Lizenz bleibt unverändert,
    # damit Preis-, Laufzeit- oder Kategorieänderungen nicht versehentlich
    # aktive Zuweisungen blockieren.
    lizenzklasse = bisheriger_zieltyp
    zuweisungsart = (
        str(lizenz[9]).strip().lower()
        if len(lizenz) > 9 and lizenz[9]
        else bisheriger_zieltyp
    )

    if lizenzklasse not in erlaubte_zieltypen:
        lizenzklasse = bisheriger_zieltyp

    if zuweisungsart not in erlaubte_zieltypen:
        zuweisungsart = lizenzklasse

    neuer_zieltyp = lizenzklasse

    # Ein Zielartwechsel ist nur möglich, wenn
    # keine aktiven Zuweisungen mehr existieren.
    if neuer_zieltyp != bisheriger_zieltyp:
        aktive_zuweisungen = []

        if bisheriger_zieltyp == "benutzer":
            _, aktive_benutzer, _ = (
                lade_lizenz_details(
                    lizenz_id
                )
            )

            aktive_zuweisungen = (
                aktive_benutzer or []
            )

        elif bisheriger_zieltyp in {
            "geraet",
            "server",
        }:
            aktive_zuweisungen = (
                lade_lizenz_ziele(
                    lizenz_id,
                    bisheriger_zieltyp,
                )
                or []
            )

        if aktive_zuweisungen:
            zieltyp_anzeigenamen = {
                "benutzer": (
                    "Benutzerzuweisungen"
                ),
                "geraet": (
                    "Gerätezuweisungen"
                ),
                "server": (
                    "Serverzuweisungen"
                ),
            }

            alter_typ_name = (
                zieltyp_anzeigenamen.get(
                    bisheriger_zieltyp,
                    "Zuweisungen",
                )
            )

            return fehler_anzeigen(
                "Die Zielart der Lizenz kann nicht "
                "geändert werden, solange noch aktive "
                f"{alter_typ_name} vorhanden sind. "
                "Bitte entferne zuerst alle aktiven "
                "Zuweisungen und speichere die Änderung "
                "anschließend erneut."
            )

    technologiebereich = (
        str(lizenz[11]).strip()
        if len(lizenz) > 11 and lizenz[11]
        else "allgemein"
    )

    lizenz_aktualisieren(
        lizenz_id=lizenz_id,
        name=name,
        anbieter=anbieter,
        anzahl=anzahl,
        lizenztyp=lizenztyp,
        kosten=kosten,
        ablaufdatum=ablaufdatum,
        verlaengerungsdatum=(
            verlaengerungsdatum
        ),
        lizenzklasse=lizenzklasse,
        zuweisungsart=zuweisungsart,
        kostenmodell=kostenmodell,
        technologiebereich=(
            technologiebereich
        ),
        kategorie_id=kategorie_id_int,
        lizenzmodell_id=None,
        zuweisungszieltyp_id=None,
        beschreibung=beschreibung,
        datenquelle=datenquelle,
        datenquelle_id=datenquelle_id,
        api_sync_aktiv=api_sync_aktiv,
        externe_id=externe_id,
        status=status,
    )

    aktualisierte_lizenz, _, _ = lade_lizenz_details(
        lizenz_id
    )
    lizenz_bearbeitung_protokollieren(
        request.user,
        lizenz,
        aktualisierte_lizenz,
    )

    if ist_modal:
        return _modal_nachricht_response(
            "lizenz_gespeichert"
        )

    return redirect(
        "lizenz_detail",
        lizenz_id=lizenz_id,
    )


def lizenzlogik_daten_fuer_formular_laden():
    lizenz_modelle_roh = lade_lizenz_modelle(nur_aktive=True)
    zuweisungsziel_typen_roh = lade_zuweisungsziel_typen(nur_aktive=True)

    lizenz_modelle = []

    for modell in lizenz_modelle_roh:
        lizenz_modelle.append({
            "id": modell[0],
            "name": modell[1],
            "slug": modell[2],
            "beschreibung": modell[3],
            "logik_typ": modell[4],
            "aktiv": bool(modell[5]),
            "sortierung": modell[6],
        })

    zuweisungsziel_typen = []

    for zieltyp in zuweisungsziel_typen_roh:
        zuweisungsziel_typen.append({
            "id": zieltyp[0],
            "name": zieltyp[1],
            "slug": zieltyp[2],
            "beschreibung": zieltyp[3],
            "basistyp": zieltyp[4],
            "aktiv": bool(zieltyp[5]),
            "sortierung": zieltyp[6],
        })

    return lizenz_modelle, zuweisungsziel_typen


def standard_lizenzlogik_fuer_lizenzklasse_laden(lizenzklasse):
    if lizenzklasse == "geraet":
        lizenzmodell_id = standard_lizenzmodell_id_laden("geraetebasiert")
        zuweisungszieltyp_id = standard_zuweisungszieltyp_id_laden("geraet")
        return lizenzmodell_id, zuweisungszieltyp_id

    if lizenzklasse == "server":
        lizenzmodell_id = standard_lizenzmodell_id_laden("infrastrukturbasiert")
        zuweisungszieltyp_id = standard_zuweisungszieltyp_id_laden("server")
        return lizenzmodell_id, zuweisungszieltyp_id

    lizenzmodell_id = standard_lizenzmodell_id_laden("nutzerbasiert")
    zuweisungszieltyp_id = standard_zuweisungszieltyp_id_laden("benutzer")
    return lizenzmodell_id, zuweisungszieltyp_id


def formular_lizenzlogik_validieren_oder_standard_laden(
    request,
    lizenzklasse,
    zuweisungsart
):
    lizenzmodell_id = request.POST.get("lizenzmodell_id", "").strip()
    zuweisungszieltyp_id = request.POST.get("zuweisungszieltyp_id", "").strip()

    if not lizenzmodell_id or not zuweisungszieltyp_id:
        return standard_lizenzlogik_fuer_lizenzklasse_laden(lizenzklasse), None

    try:
        lizenzmodell_id_int = int(lizenzmodell_id)
    except ValueError:
        return (None, None), "Bitte ein gültiges Lizenzmodell auswählen."

    try:
        zuweisungszieltyp_id_int = int(zuweisungszieltyp_id)
    except ValueError:
        return (None, None), "Bitte einen gültigen Zuweisungszieltyp auswählen."

    lizenzmodell = lade_lizenz_modell(lizenzmodell_id_int)

    if lizenzmodell is None:
        return (None, None), "Das ausgewählte Lizenzmodell existiert nicht."

    if not bool(lizenzmodell[5]):
        return (None, None), "Das ausgewählte Lizenzmodell ist nicht aktiv."

    zuweisungszieltyp = lade_zuweisungsziel_typ(zuweisungszieltyp_id_int)

    if zuweisungszieltyp is None:
        return (None, None), "Der ausgewählte Zuweisungszieltyp existiert nicht."

    if not bool(zuweisungszieltyp[5]):
        return (None, None), "Der ausgewählte Zuweisungszieltyp ist nicht aktiv."

    basistyp = zuweisungszieltyp[4]

    if basistyp in ["benutzer", "geraet", "server"]:
        lizenzklasse = basistyp
        zuweisungsart = basistyp

    return (lizenzmodell_id_int, zuweisungszieltyp_id_int, lizenzklasse, zuweisungsart), None

@login_required
@xframe_options_sameorigin
def lizenz_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    kategorien_roh = lade_lizenz_kategorien(nur_aktive=True)
    kategorien = []

    for kategorie in kategorien_roh:
        kategorien.append({
            "id": kategorie[0],
            "name": kategorie[1],
            "beschreibung": kategorie[2],
            "lizenzlogik": kategorie[3] if len(kategorie) > 3 else "",
            "typische_zuordnung": (
                kategorie[4] if len(kategorie) > 4 else ""
            ),
            "interne_lizenzklasse": (
                kategorie[5] if len(kategorie) > 5 else "benutzer"
            ),
            "aktiv": (
                bool(kategorie[6]) if len(kategorie) > 6 else True
            ),
            "slug": kategorie[7] if len(kategorie) > 7 else "",
            "standard_zuweisungsart": (
                kategorie[8] if len(kategorie) > 8 else "benutzer"
            ),
            "archiviert": (
                bool(kategorie[9]) if len(kategorie) > 9 else False
            ),
            "archiviert_am": (
                kategorie[10] if len(kategorie) > 10 else ""
            ),
            "archivierungsgrund": (
                kategorie[11] if len(kategorie) > 11 else ""
            ),
            "sortierung": (
                kategorie[12] if len(kategorie) > 12 else 100
            ),
            "erstellt_am": (
                kategorie[13] if len(kategorie) > 13 else ""
            ),
            "aktualisiert_am": (
                kategorie[14] if len(kategorie) > 14 else ""
            ),
        })

    template_name = "lizenzen/lizenz_hinzufuegen.html"

    basis_context = {
        "fehler": "",
        "kategorien": kategorien,
        "anbieter_liste": lade_anbieter(nur_aktive=True),
        "datenquellen_liste": lade_eingerichtete_datenquellen(),
        "benutzer_liste": lade_benutzer_uebersicht(),
        "geraete_liste": lade_geraete_uebersicht(),
        "ist_modal": ist_modal,
        "template_basis": template_basis,
        "formular_daten": {},
    }

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        anbieter = request.POST.get("anbieter", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        kategorie_id = request.POST.get("kategorie_id", "").strip()

        anzahl_roh = request.POST.get("anzahl", "").strip()
        kosten_roh = request.POST.get("kosten", "").strip()

        kostenmodell = request.POST.get(
            "kostenmodell",
            "fortlaufend"
        ).strip()

        ablaufdatum = request.POST.get(
            "ablaufdatum",
            ""
        ).strip()

        verlaengerungsdatum = request.POST.get(
            "verlaengerungsdatum",
            ""
        ).strip()

        # Verwaltungsart:
        # "manuell" oder "datenquelle"
        verwaltungsart = request.POST.get(
            "verwaltungsart",
            ""
        ).strip().lower()

        # Auswahl aus dem späteren Manuell-Modal:
        # "keine", "benutzer" oder "geraet"
        manuelle_zuweisung_art = request.POST.get(
            "manuelle_zuweisung_art",
            "keine"
        ).strip().lower()

        manuelles_ziel_id = request.POST.get(
            "manuelles_ziel_id",
            ""
        ).strip()

        # Auswahl aus dem späteren Datenquellen-Modal.
        ausgewaehlte_datenquelle = request.POST.get(
            "datenquelle",
            ""
        ).strip()

        externe_id = ""
        formular_daten = {
            "name": name,
            "anbieter": anbieter,
            "beschreibung": beschreibung,
            "kategorie_id": kategorie_id,
            "anzahl": anzahl_roh,
            "kosten": kosten_roh,
            "kostenmodell": kostenmodell,
            "ablaufdatum": ablaufdatum,
            "verlaengerungsdatum": verlaengerungsdatum,
            "verwaltungsart": verwaltungsart,
            "manuelle_zuweisung_art": manuelle_zuweisung_art,
            "manuelles_ziel_id": manuelles_ziel_id,
            "datenquelle": ausgewaehlte_datenquelle,
        }

        def render_mit_fehler(fehlertext):
            context = basis_context.copy()
            context["fehler"] = fehlertext
            context["formular_daten"] = formular_daten

            return render(
                request,
                template_name,
                context
            )

        if (
            not name
            or not anbieter
            or not anzahl_roh
            or not kosten_roh
            or not kategorie_id
        ):
            return render_mit_fehler(
                "Bitte alle Pflichtfelder ausfüllen."
            )

        if verwaltungsart not in ["manuell", "datenquelle"]:
            return render_mit_fehler(
                "Bitte eine gültige Verwaltungsart auswählen."
            )

        try:
            kategorie_id_int = int(kategorie_id)

        except (TypeError, ValueError):
            return render_mit_fehler(
                "Bitte eine gültige Lizenzkategorie auswählen."
            )

        kategorie = lade_lizenz_kategorie(kategorie_id_int)

        if kategorie is None:
            return render_mit_fehler(
                "Die ausgewählte Lizenzkategorie existiert nicht."
            )

        if len(kategorie) > 9 and bool(kategorie[9]):
            return render_mit_fehler(
                "Archivierte Kategorien können nicht für neue "
                "Lizenzen verwendet werden."
            )

        if kostenmodell not in [
            "fortlaufend",
            "jaehrlich",
            "einmalig",
        ]:
            return render_mit_fehler(
                "Bitte ein gültiges Abrechnungsintervall auswählen."
            )

        try:
            anzahl = int(anzahl_roh)

            if anzahl < 1:
                raise ValueError

        except (TypeError, ValueError):
            return render_mit_fehler(
                "Die Anzahl muss eine ganze Zahl größer als 0 sein."
            )

        try:
            kosten = float(kosten_roh.replace(",", "."))

            if kosten < 0:
                raise ValueError

        except (TypeError, ValueError):
            return render_mit_fehler(
                "Die Kosten müssen eine gültige Zahl ab 0 sein."
            )

        if verwaltungsart == "manuell":
            datenquelle = "manuell"
            datenquelle_id = None
            api_sync_aktiv = 0
            externe_id = ""

            erlaubte_zuweisungsarten = [
                "keine",
                "benutzer",
                "geraet",
            ]

            if manuelle_zuweisung_art not in erlaubte_zuweisungsarten:
                return render_mit_fehler(
                    "Bitte eine gültige manuelle Zuweisungsart auswählen."
                )

            if (
                manuelle_zuweisung_art in ["benutzer", "geraet"]
                and not manuelles_ziel_id
            ):
                return render_mit_fehler(
                    "Bitte ein Ziel für die manuelle Zuweisung auswählen."
                )

            if manuelles_ziel_id:
                try:
                    manuelles_ziel_id = int(manuelles_ziel_id)

                    if manuelles_ziel_id < 1:
                        raise ValueError

                except (TypeError, ValueError):
                    return render_mit_fehler(
                        "Das ausgewählte Zuweisungsziel ist ungültig."
                    )

        else:
            datenquelle = ausgewaehlte_datenquelle

            if not datenquelle:
                return render_mit_fehler(
                    "Bitte eine eingerichtete Datenquelle auswählen."
                )

            eingerichtete_datenquellen = (
                lade_eingerichtete_datenquellen()
            )

            erlaubte_datenquellen_ids = {
                str(eintrag["id"])
                for eintrag in eingerichtete_datenquellen
            }

            if str(datenquelle) not in erlaubte_datenquellen_ids:
                return render_mit_fehler(
                    "Die ausgewählte Datenquelle existiert nicht "
                    "oder ist nicht aktiv."
                )

            datenquelle_id = int(
                datenquelle
            )
            api_sync_aktiv = 1
            externe_id = ""

            manuelle_zuweisung_art = "keine"
            manuelles_ziel_id = ""

        lizenztyp = name
        technologiebereich = "allgemein"

        # Die alten Felder bleiben aus Kompatibilitätsgründen bestehen.
        # Die Kategorie liefert den Standardwert.
        interne_lizenzklasse = (
            kategorie[5]
            if len(kategorie) > 5 and kategorie[5]
            else "benutzer"
        )

        standard_zuweisungsart = (
            kategorie[8]
            if len(kategorie) > 8 and kategorie[8]
            else interne_lizenzklasse
        )

        erlaubte_alte_zieltypen = [
            "benutzer",
            "geraet",
            "server",
        ]

        if interne_lizenzklasse not in erlaubte_alte_zieltypen:
            interne_lizenzklasse = "benutzer"

        if standard_zuweisungsart not in erlaubte_alte_zieltypen:
            standard_zuweisungsart = interne_lizenzklasse

        lizenzklasse = interne_lizenzklasse
        zuweisungsart = standard_zuweisungsart

        if (
            verwaltungsart == "manuell"
            and manuelle_zuweisung_art
            in {"benutzer", "geraet"}
            and manuelle_zuweisung_art != lizenzklasse
        ):
            zieltyp_anzeigenamen = {
                "benutzer": "einem Benutzer",
                "geraet": "einem Gerät",
                "server": "einem Server",
            }

            erlaubtes_ziel = zieltyp_anzeigenamen.get(
                lizenzklasse,
                "dem vorgesehenen Zieltyp",
            )

            return render_mit_fehler(
                "Die ausgewählte Kategorie definiert diese "
                f"Lizenz als {lizenzklasse}basiert. "
                "Eine direkte Erstzuweisung ist deshalb nur "
                f"an {erlaubtes_ziel} möglich."
            )

        else:
            lizenzklasse = interne_lizenzklasse
            zuweisungsart = standard_zuweisungsart

        neue_lizenz_id = lizenz_hinzufuegen(
            name=name,
            anbieter=anbieter,
            anzahl=anzahl,
            lizenztyp=lizenztyp,
            kosten=kosten,
            ablaufdatum=ablaufdatum,
            verlaengerungsdatum=verlaengerungsdatum,
            lizenzklasse=lizenzklasse,
            zuweisungsart=zuweisungsart,
            kostenmodell=kostenmodell,
            technologiebereich=technologiebereich,
            kategorie_id=kategorie_id_int,
            lizenzmodell_id=None,
            zuweisungszieltyp_id=None,
            beschreibung=beschreibung,
            datenquelle=datenquelle,
            datenquelle_id=datenquelle_id,
            api_sync_aktiv=api_sync_aktiv,
            externe_id=externe_id,
            status="aktiv",
        )

        if (
            verwaltungsart == "manuell"
            and manuelle_zuweisung_art in ["benutzer", "geraet"]
        ):
            erfolgreich, meldung = weise_lizenz_an_ziel_zu(
                lizenz_id=neue_lizenz_id,
                ziel_typ=manuelle_zuweisung_art,
                ziel_id=manuelles_ziel_id,
            )

            if not erfolgreich:
                # Falls die Erstzuweisung fehlschlägt,
                # wird keine halbfertige Lizenz behalten.
                lizenz_loeschen(neue_lizenz_id)

                return render_mit_fehler(
                    "Die Lizenz konnte nicht vollständig angelegt werden: "
                    + meldung
                )

        angelegte_lizenz, _, _ = lade_lizenz_details(
            neue_lizenz_id
        )
        lizenz_erstellt_protokollieren(
            request.user,
            angelegte_lizenz,
        )

        if ist_modal:
            return _modal_nachricht_response(
                "lizenz_gespeichert"
            )

        return redirect(
            "lizenz_detail",
            lizenz_id=neue_lizenz_id
        )

    return render(
        request,
        template_name,
        basis_context
    )
@login_required
@xframe_options_sameorigin
def lizenz_zuweisen(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    fehler = ""
    erfolg = ""

    suchtext = request.GET.get(
        "suche",
        "",
    ).strip().lower()

    ausgewaehlter_benutzer_id = request.GET.get(
        "benutzer_id",
        "",
    ).strip()

    ausgewaehlter_geraet_id = request.GET.get(
        "geraet_id",
        "",
    ).strip()

    vorausgewaehlte_lizenz_id = request.GET.get(
        "lizenz_id",
        "",
    ).strip()

    # -------------------------------------------------
    # Benutzer und Abteilungen laden
    # -------------------------------------------------

    alle_benutzer = lade_benutzer_uebersicht()
    benutzer_liste = []
    ausgewaehlter_benutzer = None

    abteilungen = [
        "Alle Abteilungen"
    ]

    for benutzer in alle_benutzer:
        abteilung = benutzer[4] or ""

        if (
            abteilung
            and abteilung not in abteilungen
        ):
            abteilungen.append(
                abteilung
            )

    abteilungen.sort()

    if "Alle Abteilungen" in abteilungen:
        abteilungen.remove(
            "Alle Abteilungen"
        )

    abteilungen.insert(
        0,
        "Alle Abteilungen",
    )

    for benutzer in alle_benutzer:
        benutzer_id = str(
            benutzer[0]
        )

        suchbasis = " ".join(
            str(wert).lower()
            for wert in benutzer
        )

        if (
            ausgewaehlter_benutzer_id
            and benutzer_id
            == ausgewaehlter_benutzer_id
        ):
            ausgewaehlter_benutzer = (
                benutzer
            )

        if (
            not suchtext
            or suchtext in suchbasis
        ):
            benutzer_liste.append(
                benutzer
            )

    # -------------------------------------------------
    # Nur manuell verwaltete Lizenzen bereitstellen
    # -------------------------------------------------

    lizenz_liste = (
        lade_lizenzen_uebersicht()
    )

    manuelle_lizenzen = [
        lizenz
        for lizenz in lizenz_liste
        if ist_manuell_verwaltete_lizenz(
            lizenz,
            datenquelle_index=16,
            api_sync_index=17,
        )
    ]

    benutzer_lizenzen = [
        lizenz
        for lizenz in manuelle_lizenzen
        if ermittle_lizenz_ziel_typ(
            lizenz
        ) == "benutzer"
    ]

    geraete_lizenzen = [
        lizenz
        for lizenz in manuelle_lizenzen
        if ermittle_lizenz_ziel_typ(
            lizenz
        ) == "geraet"
    ]

    geraete_liste = (
        lade_geraete_uebersicht()
    )

    ausgewaehltes_geraet = next(
        (
            geraet
            for geraet in geraete_liste
            if str(geraet[0])
            == ausgewaehlter_geraet_id
        ),
        None,
    )

    # -------------------------------------------------
    # Vorausgewählte Lizenz prüfen
    # -------------------------------------------------

    vorausgewaehlte_lizenz = None

    if vorausgewaehlte_lizenz_id:
        vorausgewaehlte_lizenz, _, _ = (
            lade_lizenz_details(
                vorausgewaehlte_lizenz_id
            )
        )

        if vorausgewaehlte_lizenz is None:
            return render(
                request,
                "lizenzen/lizenz_nicht_gefunden.html",
                {
                    "ist_modal": ist_modal,
                    "template_basis": (
                        template_basis
                    ),
                },
            )

        if not ist_manuell_verwaltete_lizenz(
            vorausgewaehlte_lizenz,
            datenquelle_index=18,
            api_sync_index=19,
        ):
            fehler = (
                "Diese Lizenz wird über eine "
                "Datenquelle/API geführt und kann "
                "nicht manuell zugewiesen werden. "
                "Bitte nutze dafür den "
                "Datenquellen-Abgleich."
            )

    # -------------------------------------------------
    # Zuweisung speichern
    # -------------------------------------------------

    if request.method == "POST":
        zuweisung_typ = request.POST.get(
            "zuweisung_typ",
            "",
        ).strip().lower()

        if zuweisung_typ == "benutzer":
            benutzer_ids = request.POST.getlist(
                "benutzer_ids"
            )

            # Kompatibilität mit der bisherigen Einzelauswahl
            if not benutzer_ids:
                einzelne_benutzer_id = request.POST.get(
                    "benutzer_id",
                    "",
                ).strip()

                if einzelne_benutzer_id:
                    benutzer_ids = [
                        einzelne_benutzer_id
                    ]

            # Leere und doppelte IDs entfernen
            benutzer_ids = list(
                dict.fromkeys(
                    benutzer_id.strip()
                    for benutzer_id in benutzer_ids
                    if benutzer_id.strip()
                )
            )

            lizenz_id = request.POST.get(
                "lizenz_id",
                "",
            ).strip()

            if not benutzer_ids or not lizenz_id:
                fehler = (
                    "Bitte mindestens einen Benutzer "
                    "auswählen und eine Lizenz wählen."
                )

            else:
                ausgewaehlte_lizenz, _, _ = (
                    lade_lizenz_details(
                        lizenz_id
                    )
                )

                if ausgewaehlte_lizenz is None:
                    fehler = (
                        "Die ausgewählte Lizenz "
                        "existiert nicht."
                    )

                elif not ist_manuell_verwaltete_lizenz(
                    ausgewaehlte_lizenz,
                    datenquelle_index=18,
                    api_sync_index=19,
                ):
                    fehler = (
                        "Diese Lizenz ist API-geführt "
                        "und darf nicht manuell "
                        "zugewiesen werden. Die "
                        "Zuweisung muss über die "
                        "Datenquelle synchronisiert "
                        "werden."
                    )

                else:
                    ziel_typ = (
                        ermittle_lizenz_ziel_typ(
                            ausgewaehlte_lizenz
                        )
                    )

                    lizenzname = (
                        ausgewaehlte_lizenz[1]
                    )

                    if ziel_typ != "benutzer":
                        fehler = (
                            f"Die Lizenz „{lizenzname}“ "
                            "ist keine Benutzerlizenz."
                        )

                    else:
                        erfolgreiche_zuweisungen = 0
                        fehlgeschlagene_zuweisungen = []

                        for benutzer_id in benutzer_ids:
                            erfolgreich, meldung = (
                                weise_lizenz_zu(
                                    benutzer_id,
                                    lizenz_id,
                                )
                            )

                            if erfolgreich:
                                erfolgreiche_zuweisungen += 1
                            else:
                                fehlgeschlagene_zuweisungen.append(
                                    meldung
                                )

                        if erfolgreiche_zuweisungen:
                            erfolg = (
                                f"Die Lizenz wurde "
                                f"{erfolgreiche_zuweisungen} "
                                f"Benutzer(n) erfolgreich "
                                f"zugewiesen."
                            )

                        if fehlgeschlagene_zuweisungen:
                            eindeutige_fehler = list(
                                dict.fromkeys(
                                    fehlgeschlagene_zuweisungen
                                )
                            )

                            fehler = (
                                f"{len(fehlgeschlagene_zuweisungen)} "
                                f"Zuweisung(en) konnten nicht "
                                f"durchgeführt werden: "
                                + " ".join(eindeutige_fehler)
                            )

        elif zuweisung_typ == "geraet":
            geraete_ids = [
                geraet_id.strip()
                for geraet_id in request.POST.getlist(
                    "geraete_ids"
                )
                if geraet_id.strip()
            ]

            lizenz_id = request.POST.get(
                "lizenz_id",
                "",
            ).strip()

            if not geraete_ids or not lizenz_id:
                fehler = (
                    "Bitte mindestens ein Gerät "
                    "und eine Gerätelizenz auswählen."
                )

            else:
                ausgewaehlte_lizenz, _, _ = (
                    lade_lizenz_details(
                        lizenz_id
                    )
                )

                if ausgewaehlte_lizenz is None:
                    fehler = (
                        "Die ausgewählte Lizenz "
                        "existiert nicht."
                    )

                elif not ist_manuell_verwaltete_lizenz(
                    ausgewaehlte_lizenz,
                    datenquelle_index=18,
                    api_sync_index=19,
                ):
                    fehler = (
                        "Diese Lizenz ist API-geführt "
                        "und darf nicht manuell "
                        "zugewiesen werden. Die "
                        "Zuweisung muss über die "
                        "Datenquelle synchronisiert "
                        "werden."
                    )

                else:
                    ziel_typ = (
                        ermittle_lizenz_ziel_typ(
                            ausgewaehlte_lizenz
                        )
                    )

                    lizenzname = (
                        ausgewaehlte_lizenz[1]
                    )

                    if ziel_typ != "geraet":
                        fehler = (
                            f"Die Lizenz „{lizenzname}“ "
                            "ist keine Gerätelizenz."
                        )

                    else:
                        erfolgreiche_zuweisungen = 0
                        fehlermeldungen = []

                        for geraet_id in geraete_ids:
                            erfolgreich, meldung = (
                                weise_lizenz_an_ziel_zu(
                                    lizenz_id,
                                    "geraet",
                                    geraet_id,
                                )
                            )

                            if erfolgreich:
                                erfolgreiche_zuweisungen += 1
                            else:
                                fehlermeldungen.append(
                                    meldung
                                )

                        if erfolgreiche_zuweisungen:
                            erfolg = (
                                f"{erfolgreiche_zuweisungen} "
                                "Gerät"
                                + (
                                    " wurde"
                                    if erfolgreiche_zuweisungen == 1
                                    else "e wurden"
                                )
                                + " erfolgreich zugewiesen."
                            )

                        if fehlermeldungen:
                            fehler = " ".join(
                                dict.fromkeys(
                                    fehlermeldungen
                                )
                            )

        if ist_modal and erfolg and not fehler:
            return _modal_nachricht_response(
                "lizenz_gespeichert"
            )

    return render(
        request,
        "lizenzen/lizenz_zuweisen.html",
        {
            "benutzer_liste": benutzer_liste,
            "abteilungen": abteilungen,
            "lizenz_liste": manuelle_lizenzen,
            "benutzer_lizenzen": (
                benutzer_lizenzen
            ),
            "geraete_lizenzen": (
                geraete_lizenzen
            ),
            "geraete_liste": geraete_liste,
            "fehler": fehler,
            "erfolg": erfolg,
            "suchtext": suchtext,
            "ausgewaehlter_benutzer": (
                ausgewaehlter_benutzer
            ),
            "ausgewaehltes_geraet": (
                ausgewaehltes_geraet
            ),
            "vorausgewaehlte_lizenz_id": (
                vorausgewaehlte_lizenz_id
            ),
            "vorausgewaehlte_lizenz": (
                vorausgewaehlte_lizenz
            ),
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
@xframe_options_sameorigin
@require_POST
def lizenz_loeschen_view(request, lizenz_id):
    ist_modal = _ist_modal_anfrage(request)

    lizenz_loeschen(lizenz_id)

    if ist_modal:
        return HttpResponse("""
            <!DOCTYPE html>
            <html lang="de">
            <head>
                <meta charset="UTF-8">
                <title>Lizenz gelöscht</title>
            </head>
            <body>
                <script>
                    window.parent.postMessage(
                        "lizenz_geloescht",
                        window.location.origin
                    );

                    /*
                     * Sicherheits-Fallback:
                     * Falls das Hauptfenster die Nachricht nicht verarbeitet,
                     * wird die Lizenzübersicht neu geladen.
                     */
                    window.setTimeout(function () {
                        try {
                            window.parent.location.href =
                                "/lizenzen/";
                        } catch (error) {
                            window.location.href =
                                "/lizenzen/";
                        }
                    }, 400);
                </script>
            </body>
            </html>
        """)

    return redirect("lizenzen_liste")

def _sync_intervall_anzeige(
    intervall_minuten,
):
    try:
        intervall_minuten = int(
            intervall_minuten
        )
    except (TypeError, ValueError):
        return ""

    return ERLAUBTE_AUTOMATISCHE_SYNC_INTERVALLE.get(
        intervall_minuten,
        "",
    )


def _naechste_synchronisation_anzeige(
    zeitpunkt,
):
    zeitpunkt = str(
        zeitpunkt or ""
    ).strip()

    if not zeitpunkt:
        return ""

    try:
        utc_zeitpunkt = datetime.strptime(
            zeitpunkt,
            "%Y-%m-%d %H:%M:%S",
        ).replace(
            tzinfo=datetime_timezone.utc
        )
    except ValueError:
        return ""

    lokaler_zeitpunkt = localtime(
        utc_zeitpunkt
    )
    heute = localtime(now()).date()
    lauf_tag = lokaler_zeitpunkt.date()

    uhrzeit = lokaler_zeitpunkt.strftime(
        "%H:%M"
    )

    if lauf_tag == heute:
        return f"Heute um {uhrzeit} Uhr"

    if lauf_tag == heute.fromordinal(
        heute.toordinal() + 1
    ):
        return f"Morgen um {uhrzeit} Uhr"

    return lokaler_zeitpunkt.strftime(
        "%d.%m.%Y um %H:%M Uhr"
    )


@login_required
def synchronisation_uebersicht(request):
    gespeicherte_quellen = (
        lade_eingerichtete_datenquellen(
            nur_aktive=False
        )
    )

    # Adobe ist keine aktive Sonderintegration mehr.
    # Adobe soll künftig als normale REST-API-Datenquelle
    # eingerichtet und angezeigt werden.
    gespeicherte_quellen = [
        quelle
        for quelle in gespeicherte_quellen
        if str(
            quelle.get("typ", "")
        ).strip().lower() != "adobe"
    ]

    eingerichtete_verbindungen = []

    spezielle_urls = {
        "ad": "/synchronisation/ad/",
    }

    auth_anzeigenamen = {
        "api_key": "API-Key",
        "oauth2_client_credentials": "OAuth 2.0",
        "oauth2_account": "OAuth-Konto",
    }

    status_anzeigenamen = {
        "verbunden": "Verbunden",
        "demo_verbunden": "Verbunden",
        "einrichtung_erforderlich": (
            "Einrichtung erforderlich"
        ),
        "nicht_eingerichtet": (
            "Noch nicht eingerichtet"
        ),
        "fehler": "Fehler",
        "deaktiviert": "Deaktiviert",
    }

    eingerichtete_typen = set()

    verbindung = verbindung_oeffnen()

    try:
        aktive_laeufe = {
            int(zeile[0])
            for zeile in verbindung.execute(
                """
                SELECT datenquelle_id
                FROM synchronisationslaeufe
                WHERE status = 'laeuft'
                """
            ).fetchall()
        }
    finally:
        verbindung.close()

    for quelle in gespeicherte_quellen:
        typ = str(
            quelle.get("typ", "")
        ).strip().lower()

        if not typ:
            continue

        eingerichtete_typen.add(typ)

        status = str(
            quelle.get(
                "status",
                "nicht_eingerichtet",
            )
        ).strip().lower()

        auth_typ = str(
            quelle.get("auth_typ", "")
        ).strip()

        demo_modus = bool(
            quelle.get("demo_modus", False)
        )

        if typ == "adobe":
            beschreibung = (
                "Adobe-Lizenzdaten und zugehörige Benutzer "
                "mit dem lokalen Bestand abgleichen."
            )

        elif typ == "ad":
            beschreibung = (
                "Benutzer und deren aktuellen Status aus "
                "dem Active Directory übernehmen."
            )

        elif typ == "csv":
            beschreibung = (
                "Benutzer aus einer hinterlegten CSV-Datei "
                "einlesen und mit dem lokalen Bestand abgleichen."
            )

        elif typ == "rest_api":
            beschreibung = (
                "Lizenzdaten über eine REST-API abrufen und "
                "mit dem lokalen Bestand abgleichen."
            )

        else:
            beschreibung = (
                "Externe Daten für den Lizenzbestand "
                "bereitstellen und synchronisieren."
            )

        eingerichtete_verbindungen.append({
            "id": quelle.get("id"),
            "name": quelle.get(
                "name",
                "Unbenannte Datenquelle",
            ),
            "typ": typ,
            "aktiv": bool(
                quelle.get("aktiv", 0)
            ),
            "synchronisierung_laeuft": (
                int(quelle.get("id"))
                in aktive_laeufe
            ),
            "status": status,
            "status_anzeige": (
                status_anzeigenamen.get(
                    status,
                    status.replace(
                        "_",
                        " ",
                    ).title(),
                )
            ),
            "beschreibung": beschreibung,
            "url": spezielle_urls.get(
                typ,
                "",
            ),
            "auth_typ": auth_typ,
            "zuweisungen_endpunkt": quelle.get(
                "zuweisungen_endpunkt",
                "",
            ),
            "auth_anzeige": (
                auth_anzeigenamen.get(
                    auth_typ,
                    "",
                )
            ),
            "demo_modus": demo_modus,
            "kann_synchronisieren": (
                typ in {
                    "ad",
                    "adobe",
                    "rest_api",
                    "csv",
                }
                and bool(
                    quelle.get("aktiv", 0)
                )
            ),
            "letzte_meldung": quelle.get(
                "letzte_meldung",
                "",
            ),
            "automatische_synchronisation": bool(
                quelle.get(
                    "automatische_synchronisation",
                    0,
                )
            ),
            "sync_intervall_anzeige": (
                _sync_intervall_anzeige(
                    quelle.get(
                        "sync_intervall_minuten"
                    )
                )
            ),
            "naechste_synchronisation_anzeige": (
                _naechste_synchronisation_anzeige(
                    quelle.get(
                        "naechste_synchronisation"
                    )
                )
            ),
        })

    anbieter_definitionen = [
        {
            "typ": "eigene_rest_api",
            "name": "REST-API-Verbindung",
            "beschreibung": (
                "Verbinde ein externes System über einen "
                "geführten, sicheren Einrichtungsassistenten."
            ),
            "status": "verfuegbar",
            "status_anzeige": "Bereit zur Einrichtung",
            "einrichtbar": True,
            "prioritaet": 10,
        },
    ]

    verfuegbare_anbieter = []

    for anbieter in anbieter_definitionen:
        typ = anbieter["typ"]

        if typ in eingerichtete_typen:
            continue

        verfuegbare_anbieter.append({
            **anbieter,
            "einrichtbar": typ in {
                "adobe",
                "sophos",
            },
        })

    verfuegbare_anbieter.sort(
        key=lambda eintrag: eintrag["prioritaet"]
    )

    anzahl_eingerichtet = len(
        eingerichtete_verbindungen
    )

    anzahl_verbunden = sum(
        1
        for quelle in eingerichtete_verbindungen
        if quelle.get("status") in {
            "verbunden",
            "demo_verbunden",
        }
    )

    anzahl_fehler = sum(
        1
        for quelle in eingerichtete_verbindungen
        if quelle.get("status") == "fehler"
    )

    anzahl_automatische_quellen = sum(
        1
        for quelle in gespeicherte_quellen
        if bool(
            quelle.get(
                "automatische_synchronisation",
                0,
            )
        )
        and bool(
            quelle.get("aktiv", 0)
        )
    )

    sync_status = request.GET.get(
        "sync_status",
        "",
    ).strip()

    sync_meldung = request.GET.get(
        "sync_meldung",
        "",
    ).strip()

    return render(
        request,
        "lizenzen/synchronisation.html",
        {
            "synchronisationen": (
                eingerichtete_verbindungen
            ),
            "eingerichtete_verbindungen": (
                eingerichtete_verbindungen
            ),
            "verfuegbare_anbieter": (
                verfuegbare_anbieter
            ),
            "sync_status": sync_status,
            "sync_meldung": sync_meldung,
            "anzahl_eingerichtet": anzahl_eingerichtet,
            "anzahl_verbunden": anzahl_verbunden,
            "anzahl_fehler": anzahl_fehler,
            "synchronisationslaeufe": (
                synchronisationslaeufe_laden(
                    limit=10
                )
            ),
            "anzahl_automatische_quellen": (
                anzahl_automatische_quellen
            ),
        },
    )

@login_required
@require_POST
def datenquelle_deaktivieren_view(
    request,
    datenquelle_id,
):
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    erlaubte_typen = {
        "rest_api",
        "csv",
    }

    typ = str(
        (datenquelle or {}).get(
            "typ",
            "",
        )
    ).strip().lower()

    if typ in erlaubte_typen:
        datenquelle_deaktivieren(
            datenquelle_id
        )

    return redirect(
        "synchronisation_uebersicht"
    )


@login_required
@require_POST
def datenquelle_reaktivieren_view(
    request,
    datenquelle_id,
):
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    erlaubte_typen = {
        "rest_api",
        "csv",
    }

    typ = str(
        (datenquelle or {}).get(
            "typ",
            "",
        )
    ).strip().lower()

    if typ in erlaubte_typen:
        datenquelle_reaktivieren(
            datenquelle_id
        )

    return redirect(
        "synchronisation_uebersicht"
    )


@login_required
def datenquelle_automatik_view(
    request,
    datenquelle_id,
):
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    if datenquelle is None:
        return redirect(
            "synchronisation_uebersicht"
        )

    ist_modal = _ist_modal_anfrage(request)
    fehlermeldung = ""

    erlaubte_intervalle = set(
        ERLAUBTE_AUTOMATISCHE_SYNC_INTERVALLE
    )

    if request.method == "POST":
        aktiviert = (
            request.POST.get("aktiviert") == "1"
        )

        intervall = request.POST.get(
            "intervall",
            "1440",
        )

        try:
            intervall = int(intervall)
        except (TypeError, ValueError):
            intervall = 1440

        if aktiviert and intervall not in erlaubte_intervalle:
            fehlermeldung = (
                "Bitte eine verfügbare Häufigkeit auswählen."
            )
        else:
            try:
                datenquelle = (
                    automatische_synchronisation_speichern(
                        datenquelle_id,
                        aktiviert,
                        intervall if aktiviert else None,
                    )
                )

                return render(
                    request,
                    "lizenzen/synchronisation_automatik.html",
                    {
                        "ist_modal": ist_modal,
                        "template_basis": (
                            "lizenzen/modal_base.html"
                            if ist_modal
                            else "lizenzen/base.html"
                        ),
                        "datenquelle": datenquelle,
                        "gespeichert": True,
                        "fehlermeldung": "",
                    },
                )

            except DatenquelleFehler as fehler:
                fehlermeldung = str(fehler)

    return render(
        request,
        "lizenzen/synchronisation_automatik.html",
        {
            "ist_modal": ist_modal,
            "template_basis": (
                "lizenzen/modal_base.html"
                if ist_modal
                else "lizenzen/base.html"
            ),
            "datenquelle": datenquelle,
            "gespeichert": False,
            "fehlermeldung": fehlermeldung,
        },
    )


@login_required
@require_POST
def datenquelle_loeschen_view(
    request,
    datenquelle_id,
):
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    erlaubte_typen = {
        "rest_api",
        "csv",
    }

    typ = str(
        (datenquelle or {}).get(
            "typ",
            "",
        )
    ).strip().lower()

    if typ in erlaubte_typen:
        datenquelle_loeschen(
            datenquelle_id
        )

    return redirect(
        "synchronisation_uebersicht"
    )


@login_required
@require_POST
def datenquelle_synchronisieren_view(
    request,
    datenquelle_id,
):
    try:
        ergebnis = datenquelle_synchronisieren(
            datenquelle_id
        )

        sync_status = ergebnis.get(
            "status",
            "erfolg",
        )

        sync_meldung = ergebnis.get(
            "meldung",
            (
                "Die Synchronisierung wurde "
                "erfolgreich abgeschlossen."
            ),
        )

        if sync_status == "teilweise_erfolgreich":
            konflikte = ergebnis.get(
                "konflikte",
                [],
            )

            anzahl_konflikte = len(
                konflikte
            )

            if anzahl_konflikte:
                sync_meldung = (
                    f"{anzahl_konflikte} Konflikte erkannt. "
                    "Details findest du im Synchronisationsverlauf."
                )
            else:
                sync_meldung = (
                    "Die Synchronisation wurde abgeschlossen, "
                    "es wurden jedoch Hinweise erkannt."
                )

        parameter = urlencode(
            {
                "sync_status": sync_status,
                "sync_meldung": sync_meldung,
            }
        )

    except SyncOrchestratorFehler as fehler:
        parameter = urlencode(
            {
                "sync_status": "fehler",
                "sync_meldung": str(fehler),
            }
        )

    except Exception:
        parameter = urlencode(
            {
                "sync_status": "fehler",
                "sync_meldung": (
                    "Bei der Synchronisierung ist "
                    "ein unerwarteter Fehler "
                    "aufgetreten."
                ),
            }
        )

    return redirect(
        "/synchronisation/"
        f"?{parameter}"
    )

@login_required
def datenquelle_lizenzprodukte_view(
    request,
    datenquelle_id,
):
    offene_zuordnungen = (
        offene_lizenzprodukt_zuordnungen_laden(
            datenquelle_id
        )
    )

    return render(
        request,
        "lizenzen/datenquelle_lizenzprodukte.html",
        {
            "datenquelle_id": datenquelle_id,
            "offene_zuordnungen": offene_zuordnungen,
        },
    )


@login_required
def synchronisation_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    return render(
        request,
        "lizenzen/synchronisation_quelle_auswaehlen.html",
        {
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
def synchronisation_csv_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    kontext = {
        "ist_modal": ist_modal,
        "template_basis": template_basis,
        "csv_fehler": "",
        "csv_dateiname": "",
        "csv_spalten": [],
        "csv_vorschau": [],
        "csv_trennzeichen": "",
        "csv_trennzeichen_roh": "",
        "csv_datensatzanzahl": 0,
        "csv_mapping": {},
        "csv_temp_datei": "",
    }

    if request.method == "POST":
        aktion = request.POST.get(
            "aktion",
            "pruefen",
        ).strip().lower()

        if aktion == "speichern":
            name = request.POST.get(
                "csv_name",
                "",
            ).strip()

            temp_datei_relativ = request.POST.get(
                "csv_temp_datei",
                "",
            ).strip()

            dateiname = request.POST.get(
                "csv_dateiname",
                "",
            ).strip()

            trennzeichen = request.POST.get(
                "csv_trennzeichen_roh",
                "",
            )

            datensatzanzahl = request.POST.get(
                "csv_datensatzanzahl",
                "0",
            )

            feld_mapping = {
                "vorname": request.POST.get(
                    "mapping_vorname",
                    "",
                ).strip(),
                "nachname": request.POST.get(
                    "mapping_nachname",
                    "",
                ).strip(),
                "benutzername": request.POST.get(
                    "mapping_benutzername",
                    "",
                ).strip(),
                "email": request.POST.get(
                    "mapping_email",
                    "",
                ).strip(),
                "abteilung": request.POST.get(
                    "mapping_abteilung",
                    "",
                ).strip(),
            }

            feld_mapping = {
                schluessel: wert
                for schluessel, wert
                in feld_mapping.items()
                if wert
            }

            media_root = Path(
                settings.MEDIA_ROOT
            ).resolve()

            temp_verzeichnis = (
                media_root
                / "csv_datenquellen"
                / "temp"
            ).resolve()

            temp_pfad = (
                media_root
                / temp_datei_relativ
            ).resolve()

            try:
                temp_pfad.relative_to(
                    temp_verzeichnis
                )
            except ValueError:
                kontext["csv_fehler"] = (
                    "Die temporäre CSV-Datei ist ungültig."
                )
            else:
                if (
                    not temp_pfad.is_file()
                    or temp_pfad.suffix.lower() != ".csv"
                ):
                    kontext["csv_fehler"] = (
                        "Die geprüfte CSV-Datei wurde "
                        "nicht mehr gefunden. Bitte lade "
                        "sie erneut hoch."
                    )
                else:
                    ziel_verzeichnis = (
                        media_root
                        / "csv_datenquellen"
                    )

                    ziel_verzeichnis.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    ziel_dateiname = (
                        f"{uuid4().hex}.csv"
                    )

                    ziel_pfad = (
                        ziel_verzeichnis
                        / ziel_dateiname
                    )

                    relativer_zielpfad = (
                        "csv_datenquellen/"
                        f"{ziel_dateiname}"
                    )

                    try:
                        temp_pfad.replace(
                            ziel_pfad
                        )

                        datenquelle_id = (
                            csv_datenquelle_speichern(
                                name=name,
                                dateiname=dateiname,
                                dateipfad=(
                                    relativer_zielpfad
                                ),
                                trennzeichen=(
                                    trennzeichen
                                ),
                                feld_mapping=(
                                    feld_mapping
                                ),
                                datensatzanzahl=(
                                    datensatzanzahl
                                ),
                            )
                        )

                    except DatenquelleFehler as fehler:
                        if ziel_pfad.exists():
                            ziel_pfad.unlink()

                        kontext["csv_fehler"] = str(
                            fehler
                        )

                    except Exception:
                        if ziel_pfad.exists():
                            ziel_pfad.unlink()

                        kontext["csv_fehler"] = (
                            "Die CSV-Datenquelle konnte "
                            "nicht gespeichert werden."
                        )

                    else:
                        if ist_modal:
                            datenquelle_payload = json.dumps(
                                {
                                    "type": "datenquelle_gespeichert",
                                    "datenquelle": {
                                        "id": datenquelle_id,
                                        "name": name,
                                        "typ": "csv",
                                        "status": "verbunden",
                                    },
                                },
                                ensure_ascii=False,
                            )

                            return HttpResponse(
                                """
                                <!doctype html>
                                <html lang="de">
                                    <head>
                                        <meta charset="utf-8">
                                        <title>
                                            Datenquelle gespeichert
                                        </title>
                                    </head>

                                    <body>
                                        <script>
                                            window.parent.postMessage(
                                                __DATENQUELLE_PAYLOAD__,
                                                window.location.origin
                                            );
                                        </script>
                                    </body>
                                </html>
                                """.replace(
                                    "__DATENQUELLE_PAYLOAD__",
                                    datenquelle_payload,
                                )
                            )

                        parameter = urlencode({
                            "sync_status": "erfolg",
                            "sync_meldung": (
                                "CSV-Datenquelle erfolgreich "
                                "gespeichert."
                            ),
                            "datenquelle_id": (
                                datenquelle_id
                            ),
                        })

                        return redirect(
                            "/synchronisation/"
                            f"?{parameter}"
                        )

        else:
            csv_datei = request.FILES.get(
                "csv_datei"
            )

            if csv_datei is None:
                kontext["csv_fehler"] = (
                    "Bitte wähle eine CSV-Datei aus."
                )

            elif csv_datei.size > 5 * 1024 * 1024:
                kontext["csv_fehler"] = (
                    "Die CSV-Datei darf höchstens "
                    "5 MB groß sein."
                )

            elif not csv_datei.name.lower().endswith(
                ".csv"
            ):
                kontext["csv_fehler"] = (
                    "Bitte lade eine Datei mit der "
                    "Endung .csv hoch."
                )

            else:
                kontext["csv_dateiname"] = (
                    csv_datei.name
                )

                try:
                    dateiinhalt = csv_datei.read()
                    analyse = csv_datei_analysieren(
                        dateiinhalt
                    )

                    kontext.update({
                        "csv_mapping": analyse["mapping"],
                        "csv_spalten": analyse["spalten"],
                        "csv_vorschau": analyse["vorschau"],
                        "csv_datensatzanzahl": len(
                            analyse["datensaetze"]
                        ),
                        "csv_trennzeichen": analyse[
                            "trennzeichen_anzeige"
                        ],
                        "csv_trennzeichen_roh": analyse[
                            "trennzeichen"
                        ],
                    })

                    alte_csv_temp_dateien_bereinigen()
                    temp_verzeichnis = (
                        Path(settings.MEDIA_ROOT)
                        / "csv_datenquellen"
                        / "temp"
                    )
                    temp_verzeichnis.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    temp_dateiname = f"{uuid4().hex}.csv"
                    temp_pfad = temp_verzeichnis / temp_dateiname
                    temp_pfad.write_bytes(dateiinhalt)
                    kontext["csv_temp_datei"] = (
                        "csv_datenquellen/temp/"
                        f"{temp_dateiname}"
                    )

                except CsvImportFehler as fehler:
                    kontext["csv_fehler"] = (
                        "Die CSV-Struktur konnte nicht "
                        f"eindeutig erkannt werden: {fehler}"
                    )

    return render(
        request,
        "lizenzen/synchronisation_csv_hinzufuegen.html",
        kontext,
    )


@login_required
def csv_datenquelle_bearbeiten_view(
    request,
    datenquelle_id,
):
    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    if (
        datenquelle is None
        or str(
            datenquelle.get("typ", "")
        ).lower() != "csv"
    ):
        return redirect(
            "synchronisation_uebersicht"
        )

    ist_modal, template_basis = _modal_darstellung(
        request
    )

    try:
        konfiguration_info = json.loads(
            datenquelle.get(
                "konfiguration_info"
            )
            or "{}"
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        konfiguration_info = {}

    try:
        feld_mapping = json.loads(
            datenquelle.get(
                "feld_mapping"
            )
            or "{}"
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        feld_mapping = {}

    trennzeichen = (
        konfiguration_info.get(
            "trennzeichen"
        )
        or konfiguration_info.get(
            "delimiter"
        )
        or ""
    )

    trennzeichen_anzeigenamen = {
        ",": "Komma",
        ";": "Semikolon",
        "\\t": "Tabulator",
        "|": "Senkrechter Strich",
    }

    kontext = {
        "ist_modal": ist_modal,
        "template_basis": template_basis,
        "datenquelle": datenquelle,
        "dateiname": (
            konfiguration_info.get(
                "dateiname"
            )
            or konfiguration_info.get(
                "filename"
            )
            or datenquelle.get(
                "name"
            )
            or ""
        ),
        "datensatzanzahl": (
            konfiguration_info.get(
                "datensatzanzahl"
            )
            or konfiguration_info.get(
                "count"
            )
            or 0
        ),
        "kodierung": (
            konfiguration_info.get(
                "kodierung"
            )
            or konfiguration_info.get(
                "encoding"
            )
            or "utf-8-sig"
        ),
        "trennzeichen_anzeige": (
            trennzeichen_anzeigenamen.get(
                trennzeichen,
                trennzeichen or "Nicht erkannt",
            )
        ),
        "feld_mapping": feld_mapping,
        "csv_fehler": "",
        "ersatz_dateiname": "",
        "ersatz_datensatzanzahl": 0,
        "ersatz_spalten": [],
        "ersatz_vorschau": [],
        "ersatz_trennzeichen": "",
        "ersatz_trennzeichen_roh": "",
        "ersatz_temp_datei": "",
    }

    if (
        request.method == "POST"
        and request.POST.get("aktion") == "uebernehmen"
    ):
        temp_datei_relativ = request.POST.get(
            "ersatz_temp_datei",
            "",
        ).strip()

        ersatz_dateiname = request.POST.get(
            "ersatz_dateiname",
            "",
        ).strip()

        ersatz_trennzeichen_roh = request.POST.get(
            "ersatz_trennzeichen_roh",
            "",
        )

        ersatz_datensatzanzahl = request.POST.get(
            "ersatz_datensatzanzahl",
            "0",
        )

        ersatz_spalten = [
            spalte.strip()
            for spalte in request.POST.getlist(
                "ersatz_spalten"
            )
            if spalte.strip()
        ]

        benoetigte_spalten = {
            str(spalte).strip()
            for spalte in feld_mapping.values()
            if str(spalte).strip()
        }

        fehlende_spalten = sorted(
            benoetigte_spalten
            - set(ersatz_spalten)
        )

        media_root = Path(
            settings.MEDIA_ROOT
        ).resolve()

        temp_verzeichnis = (
            media_root
            / "csv_datenquellen"
            / "temp"
        ).resolve()

        temp_pfad = (
            media_root
            / temp_datei_relativ
        ).resolve()

        try:
            temp_pfad.relative_to(
                temp_verzeichnis
            )
        except ValueError:
            kontext["csv_fehler"] = (
                "Die geprüfte Ersatzdatei ist ungültig."
            )
        else:
            if fehlende_spalten:
                kontext["csv_fehler"] = (
                    "Die neue Datei enthält nicht alle "
                    "benötigten Spalten: "
                    + ", ".join(fehlende_spalten)
                )

            elif (
                not temp_pfad.is_file()
                or temp_pfad.suffix.lower() != ".csv"
            ):
                kontext["csv_fehler"] = (
                    "Die geprüfte Datei wurde nicht mehr "
                    "gefunden. Bitte prüfe sie erneut."
                )

            else:
                ziel_verzeichnis = (
                    media_root
                    / "csv_datenquellen"
                )

                ziel_verzeichnis.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                ziel_dateiname = (
                    f"{uuid4().hex}.csv"
                )

                ziel_pfad = (
                    ziel_verzeichnis
                    / ziel_dateiname
                )

                relativer_zielpfad = (
                    "csv_datenquellen/"
                    f"{ziel_dateiname}"
                )

                alter_dateipfad = (
                    media_root
                    / str(
                        datenquelle.get(
                            "endpunkt",
                            "",
                        )
                    )
                ).resolve()

                try:
                    temp_pfad.replace(
                        ziel_pfad
                    )

                    aktualisiert = (
                        csv_datenquelle_aktualisieren(
                            datenquelle_id=(
                                datenquelle_id
                            ),
                            name=datenquelle.get(
                                "name",
                                "",
                            ),
                            dateiname=(
                                ersatz_dateiname
                            ),
                            dateipfad=(
                                relativer_zielpfad
                            ),
                            trennzeichen=(
                                ersatz_trennzeichen_roh
                            ),
                            feld_mapping=(
                                feld_mapping
                            ),
                            datensatzanzahl=(
                                ersatz_datensatzanzahl
                            ),
                        )
                    )

                    if not aktualisiert:
                        raise DatenquelleFehler(
                            "Die CSV-Datenquelle konnte "
                            "nicht aktualisiert werden."
                        )

                except DatenquelleFehler as fehler:
                    if ziel_pfad.exists():
                        ziel_pfad.unlink()

                    kontext["csv_fehler"] = str(
                        fehler
                    )

                except Exception:
                    if ziel_pfad.exists():
                        ziel_pfad.unlink()

                    kontext["csv_fehler"] = (
                        "Die neue CSV-Datei konnte nicht "
                        "übernommen werden."
                    )

                else:
                    try:
                        if (
                            alter_dateipfad.is_file()
                            and alter_dateipfad != ziel_pfad
                            and (
                                media_root
                                / "csv_datenquellen"
                            ).resolve()
                            in alter_dateipfad.parents
                        ):
                            alter_dateipfad.unlink()
                    except OSError:
                        pass

                    if ist_modal:
                        payload = json.dumps(
                            {
                                "type":
                                    "datenquelle_gespeichert",
                                "datenquelle": {
                                    "id":
                                        datenquelle_id,
                                    "name":
                                        datenquelle.get(
                                            "name",
                                            "",
                                        ),
                                    "typ": "csv",
                                    "status":
                                        "verbunden",
                                },
                            },
                            ensure_ascii=False,
                        )

                        return HttpResponse(
                            """
                            <!doctype html>
                            <html lang="de">
                                <head>
                                    <meta charset="utf-8">
                                    <title>
                                        CSV aktualisiert
                                    </title>
                                </head>
                                <body>
                                    <script>
                                        window.parent.postMessage(
                                            __PAYLOAD__,
                                            window.location.origin
                                        );
                                    </script>
                                </body>
                            </html>
                            """.replace(
                                "__PAYLOAD__",
                                payload,
                            )
                        )

                    parameter = urlencode({
                        "sync_status": "erfolg",
                        "sync_meldung": (
                            "Die neue CSV-Datei wurde "
                            "erfolgreich übernommen."
                        ),
                    })

                    return redirect(
                        "/synchronisation/"
                        f"?{parameter}"
                    )

    elif request.method == "POST":
        csv_datei = request.FILES.get(
            "csv_datei"
        )

        if csv_datei is None:
            kontext["csv_fehler"] = (
                "Bitte wähle eine CSV-Datei aus."
            )

        elif csv_datei.size > 5 * 1024 * 1024:
            kontext["csv_fehler"] = (
                "Die CSV-Datei darf höchstens "
                "5 MB groß sein."
            )

        elif not csv_datei.name.lower().endswith(
            ".csv"
        ):
            kontext["csv_fehler"] = (
                "Bitte lade eine Datei mit der "
                "Endung .csv hoch."
            )

        else:
            try:
                dateiinhalt = csv_datei.read()
                analyse = csv_datei_analysieren(
                    dateiinhalt
                )

                alte_csv_temp_dateien_bereinigen()

                temp_verzeichnis = (
                    Path(settings.MEDIA_ROOT)
                    / "csv_datenquellen"
                    / "temp"
                )

                temp_verzeichnis.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                temp_dateiname = (
                    f"{uuid4().hex}.csv"
                )

                temp_pfad = (
                    temp_verzeichnis
                    / temp_dateiname
                )

                temp_pfad.write_bytes(
                    dateiinhalt
                )

                kontext.update({
                    "ersatz_dateiname":
                        csv_datei.name,
                    "ersatz_datensatzanzahl":
                        len(analyse["datensaetze"]),
                    "ersatz_spalten":
                        analyse["spalten"],
                    "ersatz_vorschau":
                        analyse["tabellen_vorschau"],
                    "ersatz_trennzeichen":
                        analyse["trennzeichen_anzeige"],
                    "ersatz_trennzeichen_roh":
                        analyse["trennzeichen"],
                    "ersatz_temp_datei": (
                        "csv_datenquellen/"
                        "temp/"
                        f"{temp_dateiname}"
                    ),
                })

            except CsvImportFehler as fehler:
                kontext["csv_fehler"] = (
                    "Die CSV-Datei konnte nicht "
                    f"geprüft werden: {fehler}"
                )

    return render(
        request,
        "lizenzen/csv_datenquelle_bearbeiten.html",
        kontext,
    )


@login_required
def synchronisation_rest_api_hinzufuegen_view(
    request,
    datenquelle_id=None,
):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    datenquelle = None
    gespeicherte_geheimnisse = {}
    bearbeitungsmodus = datenquelle_id is not None

    if bearbeitungsmodus:
        datenquelle = datenquelle_laden(
            datenquelle_id
        )

        if (
            datenquelle is None
            or str(
                datenquelle.get("typ", "")
            ).strip().lower() != "rest_api"
        ):
            return redirect(
                "/synchronisation/"
                "?sync_status=fehler"
                "&sync_meldung=REST-Datenquelle+nicht+gefunden"
            )

        datenquelle_intern = (
            datenquelle_mit_geheimnissen_laden(
                datenquelle_id
            )
        )

        if datenquelle_intern:
            gespeicherte_geheimnisse = (
                datenquelle_intern.get(
                    "geheimnisse",
                    {},
                )
            )

    feld_mapping_gespeichert = {}
    zuweisungen_feld_mapping_gespeichert = {}

    if datenquelle:
        try:
            feld_mapping_gespeichert = json.loads(
                datenquelle.get(
                    "feld_mapping"
                )
                or "{}"
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            feld_mapping_gespeichert = {}

        try:
            zuweisungen_feld_mapping_gespeichert = (
                json.loads(
                    datenquelle.get(
                        "zuweisungen_feld_mapping"
                    )
                    or "{}"
                )
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            zuweisungen_feld_mapping_gespeichert = {}

    erlaubte_auth_typen = {
        "keine",
        "api_key",
        "api_key_token_exchange",
        "basic_auth",
        "bearer_token",
        "oauth2_client_credentials",
    }

    if request.method == "POST":
        aktion = request.POST.get(
            "aktion",
            "",
        ).strip().lower()

        name = request.POST.get(
            "name",
            "",
        ).strip()

        basis_url = request.POST.get(
            "basis_url",
            "",
        ).strip()

        endpunkt = request.POST.get(
            "endpunkt",
            "",
        ).strip()

        zuweisungen_endpunkt = request.POST.get(
            "zuweisungen_endpunkt",
            "",
        ).strip()

        auth_typ = request.POST.get(
            "auth_typ",
            "oauth2_client_credentials",
        ).strip().lower()

        api_key_header = request.POST.get(
            "api_key_header",
            "",
        ).strip()

        api_key = request.POST.get(
            "api_key",
            "",
        )

        api_key_id = request.POST.get(
            "api_key_id",
            "",
        ).strip()

        basic_benutzername = request.POST.get(
            "basic_benutzername",
            "",
        ).strip()

        basic_passwort = request.POST.get(
            "basic_passwort",
            "",
        )

        bearer_token = request.POST.get(
            "bearer_token",
            "",
        )

        token_url = request.POST.get(
            "token_url",
            "",
        ).strip()

        client_id = request.POST.get(
            "client_id",
            "",
        ).strip()

        client_secret = request.POST.get(
            "client_secret",
            "",
        )

        scope = request.POST.get(
            "scope",
            "",
        ).strip()

        (
            anbieterprofil,
            endpunkt,
            token_url,
        ) = assistent_standardwerte_anwenden(
            basis_url,
            auth_typ,
            endpunkt,
            token_url,
        )

        rest_datenart = request.POST.get(
            "rest_datenart",
            "lizenzbestand",
        ).strip().lower()

        if rest_datenart not in {
            "lizenzbestand",
            "benutzer_gruppen",
            "benutzer_lizenz",
        }:
            rest_datenart = "lizenzbestand"

        zusaetzliche_header_roh = request.POST.get(
            "zusaetzliche_header",
            "[]",
        )

        if aktion not in {
            "testen",
            "speichern",
        }:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": "Unbekannte Aktion.",
                },
                status=400,
            )

        if not name:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Bitte einen Namen für die "
                        "Verbindung eingeben."
                    ),
                },
                status=400,
            )

        if not basis_url:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Bitte eine Basis-URL eingeben."
                    ),
                },
                status=400,
            )

        if not basis_url.startswith(
            (
                "https://",
                "http://",
            )
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Basis-URL muss mit "
                        "https:// oder http:// beginnen."
                    ),
                },
                status=400,
            )

        if auth_typ not in erlaubte_auth_typen:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die ausgewählte Anmeldeart "
                        "wird nicht unterstützt."
                    ),
                },
                status=400,
            )

        if (
            auth_typ != "keine"
            and basis_url.startswith("http://")
            and not (
                basis_url.startswith(
                    "http://localhost"
                )
                or basis_url.startswith(
                    "http://127.0.0.1"
                )
            )
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Anmeldedaten dürfen nur über "
                        "HTTPS übertragen werden. "
                        "HTTP ist nur für lokale Tests "
                        "mit localhost erlaubt."
                    ),
                },
                status=400,
            )

        if auth_typ in {
            "api_key",
            "api_key_token_exchange",
        }:
            vorhandener_api_key = (
                gespeicherte_geheimnisse.get(
                    "api_key",
                    "",
                )
            )

            vorhandener_api_key_header = (
                gespeicherte_geheimnisse.get(
                    "api_key_header",
                    "",
                )
            )

            if (
                not api_key_header
                and not vorhandener_api_key_header
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte den Header-Namen "
                            "für den API-Key eingeben."
                        ),
                    },
                    status=400,
                )

            if (
                not api_key
                and not vorhandener_api_key
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte den API-Key eingeben."
                        ),
                    },
                    status=400,
                )

            if (
                auth_typ
                == "api_key_token_exchange"
                and anbieterprofil
                and anbieterprofil.api_key_id_erforderlich
                and not api_key_id
                and not gespeicherte_geheimnisse.get(
                    "api_key_id",
                    "",
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            anbieterprofil.api_key_id_hinweis
                        ),
                    },
                    status=400,
                )

        if auth_typ == "basic_auth":
            vorhandener_benutzername = (
                gespeicherte_geheimnisse.get(
                    "basic_benutzername",
                    "",
                )
            )

            vorhandenes_passwort = (
                gespeicherte_geheimnisse.get(
                    "basic_passwort",
                    "",
                )
            )

            if (
                not basic_benutzername
                and not vorhandener_benutzername
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte den Benutzernamen "
                            "eingeben."
                        ),
                    },
                    status=400,
                )

            if (
                not basic_passwort
                and not vorhandenes_passwort
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte das Passwort eingeben."
                        ),
                    },
                    status=400,
                )

        if auth_typ == "bearer_token":
            vorhandenes_bearer_token = (
                gespeicherte_geheimnisse.get(
                    "bearer_token",
                    "",
                )
            )

            if (
                not bearer_token
                and not vorhandenes_bearer_token
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte das Bearer-Token "
                            "eingeben."
                        ),
                    },
                    status=400,
                )

        if auth_typ in {
            "api_key_token_exchange",
            "oauth2_client_credentials",
        }:
            anmelde_url_name = (
                "Anmelde-URL"
                if auth_typ == "api_key_token_exchange"
                else "Token-URL"
            )

            if not token_url:
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            f"Bitte die {anmelde_url_name} "
                            "eingeben."
                        ),
                    },
                    status=400,
                )

            if not token_url.startswith(
                (
                    "https://",
                    "http://",
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            f"Die {anmelde_url_name} muss "
                            "mit https:// oder http:// "
                            "beginnen."
                        ),
                    },
                    status=400,
                )

            if (
                token_url.startswith("http://")
                and not (
                    token_url.startswith(
                        "http://localhost"
                    )
                    or token_url.startswith(
                        "http://127.0.0.1"
                    )
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            f"Die {anmelde_url_name} muss "
                            "HTTPS verwenden. HTTP ist "
                            "nur für lokale Tests erlaubt."
                        ),
                    },
                    status=400,
                )

        if auth_typ == "oauth2_client_credentials":
            vorhandene_client_id = (
                gespeicherte_geheimnisse.get(
                    "client_id",
                    "",
                )
            )

            vorhandenes_client_secret = (
                gespeicherte_geheimnisse.get(
                    "client_secret",
                    "",
                )
            )

            if (
                not client_id
                and not vorhandene_client_id
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte die Client-ID "
                            "eingeben."
                        ),
                    },
                    status=400,
                )

            if (
                not client_secret
                and not vorhandenes_client_secret
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte das Client-Secret "
                            "eingeben."
                        ),
                    },
                    status=400,
                )

        try:
            header_liste = json.loads(
                zusaetzliche_header_roh
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die zusätzlichen HTTP-Header "
                        "sind ungültig."
                    ),
                },
                status=400,
            )

        if not isinstance(
            header_liste,
            list,
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die zusätzlichen HTTP-Header "
                        "sind ungültig."
                    ),
                },
                status=400,
            )

        bereinigte_header = []

        for header in header_liste:
            if not isinstance(
                header,
                dict,
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Ein zusätzlicher HTTP-Header "
                            "hat ein ungültiges Format."
                        ),
                    },
                    status=400,
                )

            header_name = str(
                header.get(
                    "name",
                    "",
                )
            ).strip()

            header_wert = str(
                header.get(
                    "wert",
                    "",
                )
            ).strip()

            if not header_name or not header_wert:
                continue

            if any(
                zeichen in header_name
                for zeichen in (
                    "\r",
                    "\n",
                    ":",
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Ein HTTP-Header-Name "
                            "enthält ungültige Zeichen."
                        ),
                    },
                    status=400,
                )

            if any(
                zeichen in header_wert
                for zeichen in (
                    "\r",
                    "\n",
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Ein HTTP-Header-Wert "
                            "enthält ungültige Zeichen."
                        ),
                    },
                    status=400,
                )

            bereinigte_header.append(
                {
                    "name": header_name,
                    "wert": header_wert,
                }
            )

        konfiguration = {
            "name": name,
            "basis_url": basis_url,
            "endpunkt": endpunkt,
            "zuweisungen_endpunkt": (
                zuweisungen_endpunkt
            ),
            "http_methode": "GET",
            "auth_typ": auth_typ,
            "api_key_header": api_key_header,
            "api_key": api_key,
            "api_key_id": api_key_id,
            "basic_benutzername": (
                basic_benutzername
            ),
            "basic_passwort": basic_passwort,
            "bearer_token": bearer_token,
            "token_url": token_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
            "rest_datenart": rest_datenart,
            "zusaetzliche_header": (
                bereinigte_header
            ),
        }

        if bearbeitungsmodus:
            for schluessel in (
                "api_key",
                "basic_passwort",
                "bearer_token",
                "client_secret",
            ):
                if not konfiguration.get(
                    schluessel
                ):
                    konfiguration[
                        schluessel
                    ] = gespeicherte_geheimnisse.get(
                        schluessel,
                        "",
                    )

            for schluessel in (
                "api_key_header",
                "api_key_id",
                "basic_benutzername",
                "client_id",
            ):
                if not konfiguration.get(
                    schluessel
                ):
                    konfiguration[
                        schluessel
                    ] = gespeicherte_geheimnisse.get(
                        schluessel,
                        "",
                    )

            if not konfiguration.get(
                "zusaetzliche_header"
            ):
                konfiguration[
                    "zusaetzliche_header"
                ] = gespeicherte_geheimnisse.get(
                    "zusaetzliche_header",
                    [],
                )

        if aktion == "testen":
            try:
                ergebnis = (
                    rest_api_verbindung_testen(
                        konfiguration
                    )
                )

                if zuweisungen_endpunkt:
                    zuweisungen_ergebnis = (
                        rest_api_endpunkt_testen(
                            konfiguration,
                            zuweisungen_endpunkt,
                        )
                    )

                    ergebnis[
                        "zuweisungen_vorschau"
                    ] = zuweisungen_ergebnis.get(
                        "vorschau"
                    )

                    ergebnis[
                        "zuweisungen_api_url"
                    ] = zuweisungen_ergebnis.get(
                        "api_url"
                    )

                    ergebnis["meldung"] = (
                        ergebnis["meldung"]
                        + " Der Zuweisungs-Endpunkt "
                        + "wurde ebenfalls erfolgreich "
                        + "getestet."
                    )

                if bearbeitungsmodus:
                    vorschau = ergebnis.get("vorschau") or {}
                    produktkandidaten = vorschau.get(
                        "produktkandidaten",
                        [],
                    )

                    if isinstance(produktkandidaten, list):
                        vorschau["produktkandidaten"] = (
                            produktkandidaten_mit_entscheidungen_laden(
                                datenquelle_id,
                                produktkandidaten,
                            )
                        )

            except RestApiFehler as fehler:
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": str(fehler),
                    },
                    status=400,
                )

            except Exception:
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Beim Verbindungstest ist "
                            "ein unerwarteter Fehler "
                            "aufgetreten."
                        ),
                    },
                    status=500,
                )

            return JsonResponse(
                ergebnis
            )

        feld_mapping_roh = request.POST.get(
            "feld_mapping",
            "{}",
        )

        zuweisungen_feld_mapping_roh = (
            request.POST.get(
                "zuweisungen_feld_mapping",
                "{}",
            )
        )

        try:
            feld_mapping = json.loads(
                feld_mapping_roh
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Feldzuordnung ist ungültig."
                    ),
                },
                status=400,
            )

        if not isinstance(
            feld_mapping,
            dict,
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Feldzuordnung ist ungültig."
                    ),
                },
                status=400,
            )

        try:
            zuweisungen_feld_mapping = (
                json.loads(
                    zuweisungen_feld_mapping_roh
                )
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Feldzuordnung für "
                        "Zuweisungen ist ungültig."
                    ),
                },
                status=400,
            )

        if not isinstance(
            zuweisungen_feld_mapping,
            dict,
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Feldzuordnung für "
                        "Zuweisungen ist ungültig."
                    ),
                },
                status=400,
            )

        produkt_zuordnungen_roh = request.POST.get(
            "produkt_zuordnungen",
            "[]",
        )

        try:
            produkt_zuordnungen = json.loads(
                produkt_zuordnungen_roh
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Auswahl der Lizenzprodukte "
                        "ist ungültig."
                    ),
                },
                status=400,
            )

        if not isinstance(
            produkt_zuordnungen,
            list,
        ):
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Auswahl der Lizenzprodukte "
                        "ist ungültig."
                    ),
                },
                status=400,
            )

        bereinigte_produkt_zuordnungen = []

        for produkt in produkt_zuordnungen:
            if not isinstance(produkt, dict):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Eine Produktzuordnung hat "
                            "ein ungültiges Format."
                        ),
                    },
                    status=400,
                )

            produktname = str(
                produkt.get(
                    "produktname",
                    "",
                )
            ).strip()

            aktion_produkt = str(
                produkt.get(
                    "aktion",
                    "",
                )
            ).strip().lower()

            externe_gruppen = produkt.get(
                "externe_gruppen",
                [],
            )

            if (
                not produktname
                or aktion_produkt not in (
                    "neu",
                    "vorhanden",
                    "ignorieren",
                )
                or not isinstance(
                    externe_gruppen,
                    list,
                )
            ):
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Eine Produktzuordnung ist "
                            "unvollständig oder ungültig."
                        ),
                    },
                    status=400,
                )

            bereinigte_gruppen = []

            for gruppe in externe_gruppen:
                gruppenname = str(
                    gruppe or ""
                ).strip()

                if (
                    gruppenname
                    and gruppenname
                    not in bereinigte_gruppen
                ):
                    bereinigte_gruppen.append(
                        gruppenname
                    )

            if not bereinigte_gruppen:
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            f"Für {produktname} wurden "
                            "keine externen Produktgruppen "
                            "übermittelt."
                        ),
                    },
                    status=400,
                )

            lizenz_id = produkt.get(
                "lizenz_id"
            )

            if aktion_produkt == "vorhanden":
                try:
                    lizenz_id = int(
                        lizenz_id
                    )

                    if lizenz_id < 1:
                        raise ValueError

                except (
                    TypeError,
                    ValueError,
                ):
                    return JsonResponse(
                        {
                            "erfolgreich": False,
                            "meldung": (
                                f"Für {produktname} wurde "
                                "keine gültige bestehende "
                                "Lizenz ausgewählt."
                            ),
                        },
                        status=400,
                    )
            else:
                lizenz_id = None

            try:
                anzahl_benutzer = max(
                    1,
                    int(
                        produkt.get(
                            "anzahl_benutzer",
                            1,
                        )
                    ),
                )
            except (
                TypeError,
                ValueError,
            ):
                anzahl_benutzer = 1

            kosten = 0.0

            if aktion_produkt == "neu":
                kosten_roh = str(
                    produkt.get(
                        "kosten",
                        0,
                    )
                ).strip().replace(",", ".")

                try:
                    kosten = float(
                        kosten_roh or 0
                    )

                    if kosten < 0:
                        raise ValueError

                except (
                    TypeError,
                    ValueError,
                ):
                    return JsonResponse(
                        {
                            "erfolgreich": False,
                            "meldung": (
                                f"Die Kosten für "
                                f"{produktname} sind "
                                "ungültig."
                            ),
                        },
                        status=400,
                    )

            bereinigte_produkt_zuordnungen.append(
                {
                    "produktname": produktname,
                    "aktion": aktion_produkt,
                    "lizenz_id": lizenz_id,
                    "anzahl_benutzer": (
                        anzahl_benutzer
                    ),
                    "kosten": kosten,
                    "externe_gruppen": (
                        bereinigte_gruppen
                    ),
                }
            )

        if rest_datenart == "benutzer_lizenz":
            hat_ziel_lizenz = any(
                produkt["aktion"] in {
                    "neu",
                    "vorhanden",
                }
                and ALLE_BENUTZER_MARKER
                in produkt["externe_gruppen"]
                for produkt in (
                    bereinigte_produkt_zuordnungen
                )
            )

            if not hat_ziel_lizenz:
                return JsonResponse(
                    {
                        "erfolgreich": False,
                        "meldung": (
                            "Bitte die erkannte Benutzerquelle "
                            "mit einer bestehenden oder neuen "
                            "Lizenz verbinden."
                        ),
                    },
                    status=400,
                )

        angelegte_lizenzen = 0
        verknuepfte_lizenzen = 0
        gespeicherte_regeln = 0
        ignorierte_gruppen = 0
        synchronisations_ergebnis = None

        try:
            rest_api_verbindung_testen(
                konfiguration
            )

            if zuweisungen_endpunkt:
                rest_api_endpunkt_testen(
                    konfiguration,
                    zuweisungen_endpunkt,
                )

            if bearbeitungsmodus:
                aktualisiert = (
                    rest_datenquelle_aktualisieren(
                        datenquelle_id,
                        konfiguration,
                        feld_mapping,
                        zuweisungen_feld_mapping,
                    )
                )

                if not aktualisiert:
                    raise DatenquelleFehler(
                        "Die Datenquelle konnte nicht "
                        "aktualisiert werden."
                    )

            else:
                datenquelle_id = (
                    rest_datenquelle_speichern(
                        konfiguration,
                        feld_mapping,
                        zuweisungen_feld_mapping,
                    )
                )

            for produkt in (
                bereinigte_produkt_zuordnungen
            ):
                produktname = produkt[
                    "produktname"
                ]

                lizenz_id = produkt[
                    "lizenz_id"
                ]

                if produkt["aktion"] == "ignorieren":
                    for gruppenname in produkt[
                        "externe_gruppen"
                    ]:
                        gruppen_mapping_entscheidung_speichern(
                            datenquelle_id=datenquelle_id,
                            gruppenname=gruppenname,
                            klassifikation="ignorieren",
                            bemerkung=(
                                "Beim Einrichten der "
                                "Datenquelle ignoriert"
                            ),
                        )
                        ignorierte_gruppen += 1

                    continue

                if produkt["aktion"] == "neu":
                    verbindung = (
                        verbindung_oeffnen()
                    )

                    vorhandene_zeile = (
                        verbindung.execute(
                            """
                            SELECT id
                            FROM lizenzen
                            WHERE LOWER(TRIM(name))
                                  = LOWER(TRIM(?))
                              AND datenquelle_id = ?
                            ORDER BY id
                            LIMIT 1
                            """,
                            (
                                produktname,
                                datenquelle_id,
                            ),
                        ).fetchone()
                    )

                    verbindung.close()

                    if vorhandene_zeile:
                        lizenz_id = int(
                            vorhandene_zeile[0]
                        )

                        verknuepfte_lizenzen += 1

                    else:
                        anbieter_name = str(
                            name or "Externe Datenquelle"
                        ).strip()

                        for suffix in (
                            " REST API",
                            " REST-API",
                            " API",
                        ):
                            if anbieter_name.lower().endswith(
                                suffix.lower()
                            ):
                                anbieter_name = anbieter_name[
                                    :-len(suffix)
                                ].strip()
                                break

                        if produktname.lower().startswith(
                            "adobe "
                        ):
                            anbieter_name = "Adobe"

                        lizenz_id = (
                            lizenz_hinzufuegen(
                                name=produktname,
                                anbieter=anbieter_name,
                                anzahl=produkt[
                                    "anzahl_benutzer"
                                ],
                                kosten=produkt[
                                    "kosten"
                                ],
                                beschreibung=(
                                    "Automatisch aus der "
                                    "Datenquelle erkannt."
                                ),
                                datenquelle="rest_api",
                                datenquelle_id=(
                                    datenquelle_id
                                ),
                                api_sync_aktiv=1,
                                externe_id=(
                                    produktname
                                ),
                                status="aktiv",
                            )
                        )

                        angelegte_lizenzen += 1

                else:
                    verbindung = (
                        verbindung_oeffnen()
                    )

                    lizenz_vorhanden = (
                        verbindung.execute(
                            """
                            SELECT id
                            FROM lizenzen
                            WHERE id = ?
                            LIMIT 1
                            """,
                            (
                                lizenz_id,
                            ),
                        ).fetchone()
                    )

                    verbindung.close()

                    if not lizenz_vorhanden:
                        raise DatenquelleFehler(
                            f"Die für {produktname} "
                            "ausgewählte Lizenz existiert "
                            "nicht mehr."
                        )

                    verknuepfte_lizenzen += 1

                for gruppenname in produkt[
                    "externe_gruppen"
                ]:
                    # Bei einer direkten Benutzerquelle beschreibt der
                    # technische Marker nur die gemeinsame Zuweisung. Er
                    # darf nicht als Produktgruppe in der Oberfläche
                    # auftauchen; die eigentlichen Gruppen/Abteilungen
                    # bleiben reine Benutzerdaten.
                    gruppen_klassifikation = (
                        "technisch"
                        if rest_datenart == "benutzer_lizenz"
                        else "produktprofil"
                    )

                    gruppen_mapping_entscheidung_speichern(
                        datenquelle_id=datenquelle_id,
                        gruppenname=gruppenname,
                        klassifikation=gruppen_klassifikation,
                        lizenz_id=lizenz_id,
                        bemerkung=(
                            "Beim Einrichten der "
                            "Datenquelle zugeordnet"
                        ),
                    )

                    regel_id = (
                        lizenz_erkennungsregel_speichern(
                            datenquelle_id=(
                                datenquelle_id
                            ),
                            muster=gruppenname,
                            lizenz_id=lizenz_id,
                            bemerkung=(
                                "Automatisch beim "
                                "Einrichten der "
                                "Datenquelle erstellt"
                            ),
                        )
                    )

                    if regel_id:
                        gespeicherte_regeln += 1

            synchronisations_ergebnis = None

            if (
                bereinigte_produkt_zuordnungen
                and konfiguration.get(
                    "rest_datenart"
                ) in {
                    "benutzer_gruppen",
                    "benutzer_lizenz",
                }
            ):
                synchronisations_ergebnis = (
                    datenquelle_synchronisieren(
                        datenquelle_id
                    )
                )

        except (
            RestApiFehler,
            DatenquelleFehler,
            SyncOrchestratorFehler,
        ) as fehler:
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": str(fehler),
                },
                status=400,
            )

        except Exception:
            logger.exception(
                "Unerwarteter Fehler beim Speichern einer REST-Datenquelle."
            )
            return JsonResponse(
                {
                    "erfolgreich": False,
                    "meldung": (
                        "Die Datenquelle konnte wegen eines "
                        "unerwarteten Fehlers nicht gespeichert werden."
                    ),
                },
                status=500,
            )

        basis_meldung = (
            "Die Datenquelle wurde erfolgreich "
            "aktualisiert."
            if bearbeitungsmodus
            else
            "Die Datenquelle wurde sicher und "
            "verschlüsselt gespeichert."
        )

        produkt_meldung = ""

        if bereinigte_produkt_zuordnungen:
            produkt_meldung = (
                f" {angelegte_lizenzen} Lizenzen "
                "wurden neu angelegt, "
                f"{verknuepfte_lizenzen} mit "
                "bestehenden Lizenzen verbunden und "
                f"{gespeicherte_regeln} "
                "Erkennungsregeln gespeichert und "
                f"{ignorierte_gruppen} Gruppen "
                "ignoriert."
            )

        sync_meldung = ""

        if synchronisations_ergebnis:
            sync_meldung = (
                " Die externen Benutzerdaten wurden direkt "
                "mit den gespeicherten Regeln geprüft."
            )

        return JsonResponse(
            {
                "erfolgreich": True,
                "datenquelle_id": datenquelle_id,
                "meldung": (
                    basis_meldung
                    + produkt_meldung
                    + sync_meldung
                ),
                "angelegte_lizenzen": (
                    angelegte_lizenzen
                ),
                "ignorierte_gruppen": (
                    ignorierte_gruppen
                ),
                "verknuepfte_lizenzen": (
                    verknuepfte_lizenzen
                ),
                "gespeicherte_regeln": (
                    gespeicherte_regeln
                ),
                "synchronisation": (
                    synchronisations_ergebnis
                ),
            }
        )

    return render(
        request,
        "lizenzen/synchronisation_rest_api_hinzufuegen.html",
        {
            "ist_modal": ist_modal,
            "template_basis": template_basis,
            "datenquelle": datenquelle,
            "bearbeitungsmodus": bearbeitungsmodus,
            "gespeicherter_api_key_header": (
                gespeicherte_geheimnisse.get(
                    "api_key_header",
                    "",
                )
            ),
            "api_key_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "api_key"
                )
            ),
            "api_key_id_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "api_key_id"
                )
            ),
            "basic_benutzername_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "basic_benutzername"
                )
            ),
            "basic_passwort_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "basic_passwort"
                )
            ),
            "bearer_token_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "bearer_token"
                )
            ),
            "client_id_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "client_id"
                )
            ),
            "client_secret_vorhanden": bool(
                gespeicherte_geheimnisse.get(
                    "client_secret"
                )
            ),
            "feld_mapping_gespeichert": (
                feld_mapping_gespeichert
            ),
            "zuweisungen_feld_mapping_gespeichert": (
                zuweisungen_feld_mapping_gespeichert
            ),
            "rest_anbieterprofile": (
                oeffentliche_assistent_profile()
            ),
            "vorhandene_lizenzen": [
                {
                    "id": lizenz[0],
                    "name": lizenz[1],
                    "anbieter": lizenz[2] or "",
                }
                for lizenz in lade_lizenzen_uebersicht()
            ],
        },
    )

@login_required
def lizenz_assistent_view(request):
    return render(request, "lizenzen/lizenz_assistent.html")
