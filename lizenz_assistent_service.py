def analysiere_lizenz_eingabe(eingabe, anbieter=""):
    eingabe = (eingabe or "").strip()
    anbieter = (anbieter or "").strip()

    prueftext = f"{eingabe} {anbieter}".lower()

    ergebnis = {
        "eingabe": eingabe,
        "name_vorschlag": eingabe,
        "anbieter_vorschlag": anbieter,
        "zielarten": ["benutzer", "geraet", "server"],
        "primaere_lizenzklasse": "",
        "einordnung_text": "Bitte einordnen",
        "hinweis": "Die App konnte keine eindeutige Lizenzart erkennen. Bitte wähle aus, wofür die Lizenz verwendet werden kann.",
        "kostenmodell_vorschlag": "fortlaufend",
        "multi_access": True,
    }

    if not eingabe:
        ergebnis["hinweis"] = "Bitte gib zuerst einen Lizenznamen oder ein Produkt ein."
        return ergebnis

    if any(wort in prueftext for wort in [
        "adobe", "acrobat", "creative cloud", "photoshop", "illustrator", "indesign"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or "Adobe",
            "zielarten": ["benutzer"],
            "primaere_lizenzklasse": "benutzer",
            "einordnung_text": "Personenlizenz erkannt",
            "hinweis": "Diese Lizenz wird wahrscheinlich einzelnen Personen oder Benutzerkonten zugeordnet.",
            "multi_access": False,
        })

    elif any(wort in prueftext for wort in [
        "microsoft 365", "office 365", "m365", "office", "deepl", "zoom"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or ("DeepL" if "deepl" in prueftext else "Microsoft"),
            "zielarten": ["benutzer"],
            "primaere_lizenzklasse": "benutzer",
            "einordnung_text": "Personenlizenz erkannt",
            "hinweis": "Diese Lizenz wird wahrscheinlich einzelnen Personen oder Benutzerkonten zugeordnet.",
            "multi_access": False,
        })

    elif any(wort in prueftext for wort in [
        "cal", "client access license", "core cal", "user cal", "device cal"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or "Microsoft",
            "zielarten": ["benutzer", "geraet"],
            "primaere_lizenzklasse": "",
            "einordnung_text": "Mehrere Zielarten möglich",
            "hinweis": "CALs können je nach Vertrag für Personen oder Geräte gelten. Bitte wähle aus, wofür diese Lizenz gelten kann und wie sie primär gespeichert werden soll.",
            "multi_access": True,
        })

    elif any(wort in prueftext for wort in [
        "sophos", "endpoint", "antivirus", "endpoint security"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or "Sophos",
            "zielarten": ["geraet", "benutzer"],
            "primaere_lizenzklasse": "",
            "einordnung_text": "Mehrere Zielarten möglich",
            "hinweis": "Endpoint-Produkte können je nach Vertrag geräte- oder personenbezogen geführt werden.",
            "multi_access": True,
        })

    elif any(wort in prueftext for wort in [
        "jamf", "intune", "mdm", "endpoint manager"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or ("Jamf" if "jamf" in prueftext else "Microsoft"),
            "zielarten": ["geraet"],
            "primaere_lizenzklasse": "geraet",
            "einordnung_text": "Gerätelizenz erkannt",
            "hinweis": "Diese Lizenz wird wahrscheinlich Geräten zugeordnet.",
            "multi_access": False,
        })

    elif any(wort in prueftext for wort in [
        "windows server", "sql server", "exchange server", "server", "backup", "veeam"
    ]):
        ergebnis.update({
            "anbieter_vorschlag": anbieter or "Microsoft",
            "zielarten": ["server"],
            "primaere_lizenzklasse": "server",
            "einordnung_text": "Serverlizenz erkannt",
            "hinweis": "Diese Lizenz gehört wahrscheinlich zu Servern oder Infrastruktur.",
            "multi_access": False,
        })

    return ergebnis