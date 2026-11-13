# Lizenzmanagement · Django-Portfolio

**[Live-Demo öffnen](https://lizenzmanagement-django.onrender.com/)** ·
ohne Anmeldung, mit fiktiven Daten und serverseitigem Schreibschutz.

Eine webbasierte Anwendung zur Verwaltung von Softwarelizenzen, Benutzern,
Geräten, Kosten und Datenquellen. Entwickelt von **Muhammed Hicyorulmazlar**
im Umfeld des Deutschen Primatenzentrums (DPZ).

Diese eigenständige öffentliche Ausgabe zeigt den echten Django-Anwendungscode
mit neu erzeugten, vollständig fiktiven Daten. Sie enthält keine internen
Datenbanken, Zugangsdaten, Serverkonfigurationen oder frühere Git-Historie.
Die Verwendung des DPZ-Brandings erfolgt mit Freigabe. Die Demo ist kein
Produktivsystem und bietet keinen Zugang zu internen DPZ-Systemen.

## Funktionen

- Dashboard mit Kosten, Auslastung und verfügbaren Kapazitäten
- Lizenzverwaltung mit Detailansichten und Änderungshistorie
- Benutzerbestand mit Suche, Filtern und CSV-/PDF-Export
- Gerätebestand mit Filtern, Sortierung und Seitennavigation
- Darstellung von Datenquellen; externe Verbindungen bleiben deaktiviert

Die interne Anwendung unterstützt zusätzlich Bearbeitung, Lizenzzuweisung,
Teamverwaltung und Synchronisation. In der öffentlichen Ausgabe sind diese
Aktionen serverseitig gesperrt. Der Demo-Zugang erfolgt automatisch als
„Demo Gast“, ohne Registrierung oder gemeinsames Passwort.

## Technik

Python 3.14 · Django 6 · SQLite · HTML/CSS/JavaScript · Gunicorn · WhiteNoise

Die fachlichen Services liegen in den Python-Modulen im Projektstamm,
Django-Views und Templates unter `lizenzen/`. `demo/` ergänzt ausschließlich
die synthetischen Beispieldaten und die Schutzmaßnahmen für die öffentliche
Ausgabe. Der Fachbestand und Django-Authentifizierung/Historie verwenden
getrennte SQLite-Datenbanken.

## Lokal starten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py collectstatic --no-input
bash start-demo.sh
```

Anschließend `http://127.0.0.1:8000` öffnen. Beim ersten Start entstehen
5 fiktive Lizenzprodukte, 24 fiktive Personen und 36 fiktive Geräte.
Alle E-Mail-Adressen verwenden `example.org`, Gerätenummern sind als
`DEMO` beziehungsweise `FAKE` gekennzeichnet. Nutzungswerte der fiktiven
Verträge sind von den lokal dargestellten Beispielzuweisungen getrennt.

## Kostenlos auf Render betreiben

`render.yaml` beschreibt einen einzelnen Python-Webservice im Tarif **Free**.
Alternativ ein öffentliches Git-Repository als Web Service verbinden und setzen:

- Build: `pip install -r requirements.txt && python manage.py collectstatic --no-input`
- Start: `bash start-demo.sh`
- Instance Type: **Free**
- `DJANGO_SECRET_KEY`: zufälliger geheimer Wert, nur bei Render speichern

Es werden keine kostenpflichtige Datenbank und kein persistentes Laufwerk
benötigt. Render kann kostenlose Dienste nach 15 Minuten ohne Aufruf
anhalten; der nächste Aufruf benötigt dann ungefähr eine Minute.
Lokale Daten gehen bei Neustarts verloren und werden deshalb aus dem
synthetischen Generator wiederhergestellt.

## Schutz der Demo

- Nur ausdrücklich erlaubte lesende Seiten sind zugänglich.
- Schreibmethoden sowie Verwaltungs- und Synchronisationsrouten sind gesperrt,
  auch wenn eine ältere Route Änderungen über GET auslösen könnte.
- Während des Webbetriebs werden beide Datenbanken im SQLite-Lesemodus geöffnet.
- Der Demo-Benutzer hat keine Administratorrechte und kein nutzbares Passwort.
- Keine aktiven API-/AD-Verbindungen, keine E-Mail-Zustellung und keine Uploads.
- Keine internen Daten, persönlichen Exporte oder Geheimnisse im Repository.

Quellcode ansehen bedeutet bei einem öffentlichen GitHub-Repository nicht,
dass Besucher ihn dort verändern können. Änderungen im Repository sind nur
für berechtigte Konten möglich. DPZ-Logo und Markenrechte verbleiben bei den
jeweiligen Rechteinhabern; eine freie Nutzungslizenz wird nicht erteilt.
