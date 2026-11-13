from database import verbindung_oeffnen


def lade_server_uebersicht():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            hostname,
            ip_adresse,
            betriebssystem,
            status
        FROM server
        ORDER BY name
    """)

    daten = cursor.fetchall()
    verbindung.close()

    return daten


def server_hinzufuegen(name, hostname, ip_adresse, betriebssystem):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        INSERT INTO server
            (name, hostname, ip_adresse, betriebssystem, status)
        VALUES (?, ?, ?, ?, ?)
    """, (
        name,
        hostname,
        ip_adresse,
        betriebssystem,
        "aktiv"
    ))

    verbindung.commit()
    verbindung.close()


def lade_server_details(server_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            hostname,
            ip_adresse,
            betriebssystem,
            status
        FROM server
        WHERE id = ?
    """, (server_id,))

    server = cursor.fetchone()
    verbindung.close()

    return server

def server_aktualisieren(server_id, name, hostname, ip_adresse, betriebssystem, status):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE server
        SET
            name = ?,
            hostname = ?,
            ip_adresse = ?,
            betriebssystem = ?,
            status = ?
        WHERE id = ?
    """, (
        name,
        hostname,
        ip_adresse,
        betriebssystem,
        status,
        server_id
    ))

    verbindung.commit()
    verbindung.close()


def server_loeschen(server_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        DELETE FROM lizenz_zuweisungen
        WHERE ziel_typ = 'server'
          AND ziel_id = ?
    """, (server_id,))

    cursor.execute("""
        DELETE FROM server
        WHERE id = ?
    """, (server_id,))

    verbindung.commit()
    verbindung.close()