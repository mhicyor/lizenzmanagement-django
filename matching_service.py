from database import verbindung_oeffnen


def normalisiere_wert(wert):
    if wert is None:
        return ""

    return str(wert).strip().lower()


def finde_benutzer_fuer_api_daten(email=None, benutzername=None, externe_id=None):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    email = normalisiere_wert(email)
    benutzername = normalisiere_wert(benutzername)
    externe_id = normalisiere_wert(externe_id)

    if email:
        cursor.execute("""
            SELECT id, name, benutzername, email, abteilung, aktiv, quelle, externe_id
            FROM benutzer
            WHERE LOWER(TRIM(email)) = ?
            LIMIT 1
        """, (email,))

        benutzer = cursor.fetchone()

        if benutzer:
            verbindung.close()
            return {
                "id": benutzer[0],
                "name": benutzer[1],
                "benutzername": benutzer[2],
                "email": benutzer[3],
                "abteilung": benutzer[4],
                "aktiv": benutzer[5],
                "quelle": benutzer[6],
                "externe_id": benutzer[7],
                "matching_methode": "E-Mail",
            }

    if benutzername:
        cursor.execute("""
            SELECT id, name, benutzername, email, abteilung, aktiv, quelle, externe_id
            FROM benutzer
            WHERE LOWER(TRIM(benutzername)) = ?
            LIMIT 1
        """, (benutzername,))

        benutzer = cursor.fetchone()

        if benutzer:
            verbindung.close()
            return {
                "id": benutzer[0],
                "name": benutzer[1],
                "benutzername": benutzer[2],
                "email": benutzer[3],
                "abteilung": benutzer[4],
                "aktiv": benutzer[5],
                "quelle": benutzer[6],
                "externe_id": benutzer[7],
                "matching_methode": "Benutzername",
            }

    if externe_id:
        cursor.execute("""
            SELECT id, name, benutzername, email, abteilung, aktiv, quelle, externe_id
            FROM benutzer
            WHERE LOWER(TRIM(externe_id)) = ?
            LIMIT 1
        """, (externe_id,))

        benutzer = cursor.fetchone()

        if benutzer:
            verbindung.close()
            return {
                "id": benutzer[0],
                "name": benutzer[1],
                "benutzername": benutzer[2],
                "email": benutzer[3],
                "abteilung": benutzer[4],
                "aktiv": benutzer[5],
                "quelle": benutzer[6],
                "externe_id": benutzer[7],
                "matching_methode": "Externe ID",
            }

    verbindung.close()
    return None


def pruefe_api_benutzer_abgleich(api_benutzer_liste):
    zugeordnet = []
    nicht_zugeordnet = []
    deaktivierte_treffer = []

    for api_benutzer in api_benutzer_liste:
        lokaler_benutzer = finde_benutzer_fuer_api_daten(
            email=api_benutzer.get("email"),
            benutzername=api_benutzer.get("benutzername"),
            externe_id=api_benutzer.get("externe_id"),
        )

        if lokaler_benutzer:
            eintrag = {
                "api_benutzer": api_benutzer,
                "lokaler_benutzer": lokaler_benutzer,
                "matching_methode": lokaler_benutzer.get("matching_methode", ""),
            }

            zugeordnet.append(eintrag)

            if lokaler_benutzer.get("aktiv") == 0:
                deaktivierte_treffer.append(eintrag)
        else:
            nicht_zugeordnet.append(api_benutzer)

    return {
        "zugeordnet": zugeordnet,
        "nicht_zugeordnet": nicht_zugeordnet,
        "deaktivierte_treffer": deaktivierte_treffer,
        "anzahl_api_benutzer": len(api_benutzer_liste),
        "anzahl_zugeordnet": len(zugeordnet),
        "anzahl_nicht_zugeordnet": len(nicht_zugeordnet),
        "anzahl_deaktivierte_treffer": len(deaktivierte_treffer),
    }