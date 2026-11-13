"""Gemeinsame Aufbereitung fuer Benutzerexporte."""


def name_aufteilen(name):
    """Teilt einen Anzeigenamen pragmatisch in Vor- und Nachname auf."""
    teile = str(name or "").strip().split()

    if len(teile) <= 1:
        return "", teile[0] if teile else "-"

    return teile[0], " ".join(teile[1:])
