"""Create synthetic data from scratch, never copy an internal database."""
import os
from datetime import date, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lizenz_web.settings")
import django
django.setup()

from django.contrib.auth.models import User
from database import datenbank_erstellen, verbindung_oeffnen, spalte_hinzufuegen_wenn_fehlt
from lizenzen.models import LizenzAenderung


def main():
    datenbank_erstellen()
    demo, _ = User.objects.get_or_create(username="demo")
    demo.first_name, demo.last_name = "Demo", "Gast"
    demo.email = "demo@example.org"
    demo.is_staff = demo.is_superuser = False
    demo.set_unusable_password()
    demo.save()
    with verbindung_oeffnen() as db:
        # The original app evolved on an existing database. Complete the
        # optional connector columns for this newly generated demo database.
        for column in ("basis_url", "endpunkt", "token_url", "scope", "feld_mapping", "auth_daten_verschluesselt"):
            spalte_hinzufuegen_wenn_fehlt(db.cursor(), "datenquellen", column, "TEXT")
        for column in ("zuweisungen_verarbeitet", "zuweisungen_neu", "zuweisungen_reaktiviert", "zuweisungen_bereits_aktiv", "zuweisungen_deaktiviert", "zuweisungen_fehlerhaft", "zuweisungen_nicht_gefunden", "zuweisungen_mehrdeutig"):
            spalte_hinzufuegen_wenn_fehlt(db.cursor(), "synchronisationslaeufe", column, "INTEGER NOT NULL DEFAULT 0")
        spalte_hinzufuegen_wenn_fehlt(db.cursor(), "synchronisationslaeufe", "konfliktdetails_json", "TEXT")
        db.commit()
        if db.execute("SELECT COUNT(*) FROM lizenzen").fetchone()[0]:
            print("Synthetic demo data already present.")
            return
        today = date.today()
        people = [
            ("Mila", "Wald"), ("Jonas", "Feld"), ("Lina", "Berg"),
            ("Finn", "Ufer"), ("Nora", "Linde"), ("Emil", "Stern"),
            ("Leni", "Falk"), ("Noah", "Heide"), ("Emma", "Klee"),
            ("Theo", "Sand"), ("Lea", "Wiese"), ("Paul", "Hain"),
            ("Ella", "Moor"), ("Oskar", "See"), ("Clara", "Tann"),
            ("Leon", "Tal"), ("Ida", "Licht"), ("Ben", "Hafen"),
            ("Frieda", "Blatt"), ("Anton", "Fels"), ("Alma", "Wolke"),
            ("Felix", "Regen"), ("Juna", "Sommer"), ("Mats", "Winter"),
        ]
        departments = ["Forschung · Demo", "IT · Demo", "Verwaltung · Demo", "Kommunikation · Demo"]
        for i, (first, last) in enumerate(people, 1):
            username = f"{first}.{last}".lower()
            db.execute("""INSERT INTO benutzer
                (id,name,benutzername,email,abteilung,aktiv,vorname,nachname,quelle,deaktivierungsgrund)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                    i, f"{first} {last}", username, f"{username}@example.org",
                    departments[(i-1) % 4], int(i <= 21), first, last,
                    "manuell", "manuell_deaktiviert" if i > 21 else None,
                ))
        db.execute("UPDATE datenquellen SET aktiv=0,demo_modus=1,letzte_meldung='In der öffentlichen Demo nicht verbunden.'")
        db.execute("""INSERT INTO datenquellen (name,typ,status,aktiv,demo_modus,letzte_meldung)
            VALUES ('Beispiel-API · ohne Verbindung','rest_api','nicht_eingerichtet',0,1,
            'Reine Darstellung mit erfundenen Daten. Keine externe Verbindung eingerichtet.')""")
        licenses = [
            ("Microsoft 365 Business", "Microsoft", 100, 82, 12.0, "benutzer"),
            ("Adobe Creative Cloud", "Adobe", 25, 20, 55.0, "benutzer"),
            ("Sophos Endpoint", "Sophos", 120, 96, 4.5, "geraet"),
            ("SoSafe Awareness", "SoSafe", 50, 40, 3.9, "benutzer"),
            ("Zoom Workplace", "Zoom", 20, 12, 9.8, "benutzer"),
        ]
        db.execute("INSERT INTO anbieter (name,beschreibung,aktiv) SELECT 'SoSafe','Beispielanbieter',1 WHERE NOT EXISTS (SELECT 1 FROM anbieter WHERE name='SoSafe')")
        for i, (name, vendor, total, used, cost, target) in enumerate(licenses, 1):
            db.execute("""INSERT INTO lizenzen
                (id,name,anbieter,anzahl,lizenztyp,kosten,kostenmodell,zuweisungsart,
                 lizenzklasse,status,beschreibung,ablaufdatum,datenquelle,
                 externer_verbrauch,verbrauch_gemeldet_am)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    i,name,vendor,total,"Abonnement",cost,"fortlaufend",target,
                    target,"aktiv","Fiktiver Vertrag für die öffentliche Portfolio-Demo.",
                    str(today + timedelta(days=20 if i == 2 else 240)),"manuell",
                    used,today.isoformat(),
                ))
            if target == "benutzer":
                for user_id in range(1, min(used, 24)+1):
                    db.execute("INSERT INTO zuweisungen (benutzer_id,lizenz_id,zuweisungsdatum,status) VALUES (?,?,?,'aktiv')", (user_id,i,today.isoformat()))
        for i in range(1,37):
            db.execute("""INSERT INTO geraete
                (id,name,inventarnummer,seriennummer,geraetetyp,status,quelle,erstellt_am)
                VALUES (?,?,?,?,?,?,?,?)""", (
                    i,f"DEMO-{'MAC' if i % 3 == 0 else 'PC'}-{i:03}",f"DEMO-{i:04}",
                    f"FAKE-SERIAL-{i:05}","computer","inaktiv" if i % 8 == 0 else "aktiv",
                    "manuell",f"{today - timedelta(days=i)} 09:30:00",
                ))
            if i <= 30:
                db.execute("INSERT INTO lizenz_zuweisungen (lizenz_id,ziel_typ,ziel_id,zuweisungsdatum,status) VALUES (3,'geraet',?,?,'aktiv')", (i,today.isoformat()))
        db.commit()
    for i, (name, *_) in enumerate(licenses,1):
        LizenzAenderung.objects.create(
            lizenz_id=i,lizenz_name=name,aktion="erstellt",
            ausgefuehrt_von=demo,ausgefuehrt_von_name="Demo Gast",
            aenderungen={},
        )
    print("Created 5 fictitious licenses, 24 people and 36 devices.")


if __name__ == "__main__":
    main()
