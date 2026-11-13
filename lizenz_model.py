from datetime import datetime, timedelta
from kosten_service import berechne_monatskosten


class LizenzStammdaten:
    def __init__(self, id, name, anbieter):
        self.id = id
        self.name = name
        self.anbieter = anbieter


class LizenzKlassifikation:
    def __init__(self, lizenzklasse="unbekannt", technologiebereich="allgemein"):
        self.lizenzklasse = lizenzklasse or "unbekannt"
        self.technologiebereich = technologiebereich or "allgemein"

    def beschreibung(self):
        beschreibungen = {
            "saas": "SaaS-/Cloud-Lizenz",
            "cal": "Client-Access-Lizenz / Zugriffslizenz",
            "geraet": "Gerätegebundene Lizenz",
            "server": "Server-/Infrastruktur-Lizenz",
            "security": "Sicherheitssoftware-Lizenz",
            "mdm": "Mobile-Device-Management-Lizenz",
            "account": "Account-/Service-Berechtigung",
            "admin_tool": "Administrationswerkzeug-Lizenz",
            "ki_dienst": "KI-Dienst-Lizenz",
            "produktsoftware": "Produktivitätssoftware-Lizenz",
            "remote_access": "Remote-Access-/VPN-Lizenz",
            "unbekannt": "Nicht klassifizierte Lizenz",
        }

        return beschreibungen.get(self.lizenzklasse, "Nicht klassifizierte Lizenz")


class LizenzKostenmodell:
    def __init__(self, kosten=0, kostenmodell="monatlich"):
        self.kosten = self._zu_float(kosten)
        self.kostenmodell = kostenmodell or "monatlich"

    def _zu_float(self, wert):
        try:
            return float(str(wert).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def monatskosten(self, menge):
        return berechne_monatskosten(
            self.kosten,
            self.kostenmodell,
            menge
        )


class LizenzZuweisungsmodell:
    def __init__(self, zuweisungsart="benutzer"):
        self.zuweisungsart = zuweisungsart or "benutzer"

    def beschreibung(self):
        beschreibungen = {
            "benutzer": "Diese Lizenz wird Benutzern zugewiesen.",
            "geraet": "Diese Lizenz wird Geräten zugewiesen.",
            "server": "Diese Lizenz wird Servern oder Cores zugeordnet.",
            "account": "Diese Lizenz wird Accounts oder Dienstzugängen zugeordnet.",
            "organisation": "Diese Lizenz gilt organisations- oder abteilungsweit.",
            "concurrent": "Diese Lizenz begrenzt die gleichzeitige Nutzung.",
        }

        return beschreibungen.get(self.zuweisungsart, "Allgemeines Zuweisungsmodell.")


class LizenzNutzungsmodell:
    def __init__(self, anzahl=0, vergeben=0):
        self.anzahl = anzahl or 0
        self.vergeben = vergeben or 0

    def freie_lizenzen(self):
        return max(self.anzahl - self.vergeben, 0)

    def ist_ueberbucht(self):
        return self.vergeben > self.anzahl


class LizenzVertragsdaten:
    def __init__(self, ablaufdatum=None, verlaengerungsdatum=None):
        self.ablaufdatum = ablaufdatum
        self.verlaengerungsdatum = verlaengerungsdatum

    def laeuft_bald_ab(self, tage=30):
        if not self.ablaufdatum:
            return False

        try:
            ablauf = datetime.strptime(self.ablaufdatum, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return False

        heute = datetime.today().date()
        return heute <= ablauf <= heute + timedelta(days=tage)


class Lizenz:
    def __init__(
        self,
        stammdaten,
        klassifikation,
        kostenmodell,
        zuweisungsmodell,
        nutzungsmodell,
        vertragsdaten
    ):
        self.stammdaten = stammdaten
        self.klassifikation = klassifikation
        self.kostenmodell = kostenmodell
        self.zuweisungsmodell = zuweisungsmodell
        self.nutzungsmodell = nutzungsmodell
        self.vertragsdaten = vertragsdaten

    def freie_lizenzen(self):
        if self.zuweisungsmodell.zuweisungsart == "organisation":
            return None

        return self.nutzungsmodell.freie_lizenzen()

    def ist_ueberbucht(self):
        if self.zuweisungsmodell.zuweisungsart == "organisation":
            return False

        return self.nutzungsmodell.ist_ueberbucht()

    def monatskosten(self):
        return self.kostenmodell.monatskosten(self.nutzungsmodell.vergeben)

    def als_dashboard_dict(self):
        freie_lizenzen = self.freie_lizenzen()

        if freie_lizenzen is None:
            freie_lizenzen = "—"

        return {
            "id": self.stammdaten.id,
            "name": self.stammdaten.name,
            "anbieter": self.stammdaten.anbieter,
            "lizenzklasse": self.klassifikation.lizenzklasse,
            "lizenzklasse_text": self.klassifikation.beschreibung(),
            "technologiebereich": self.klassifikation.technologiebereich,
            "zuweisungsart": self.zuweisungsmodell.zuweisungsart,
            "zuweisungsart_text": self.zuweisungsmodell.beschreibung(),
            "gesamt": self.nutzungsmodell.anzahl,
            "vergeben": self.nutzungsmodell.vergeben,
            "frei": freie_lizenzen,
            "kosten": f"{self.kostenmodell.kosten:.2f}",
            "gesamt_kosten": f"{self.monatskosten():.2f}",
            "ueberbucht": self.ist_ueberbucht(),
            "laeuft_bald_ab": self.vertragsdaten.laeuft_bald_ab(),
        }