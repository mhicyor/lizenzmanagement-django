from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from sync_orchestrator_service import (
    faellige_synchronisationen_ausfuehren,
)


class Command(BaseCommand):
    help = (
        "Führt alle aktuell fälligen automatischen "
        "Synchronisationen aus."
    )

    def handle(self, *args, **options):
        ergebnis = (
            faellige_synchronisationen_ausfuehren()
        )

        gefunden = int(
            ergebnis.get("gefunden", 0) or 0
        )

        self.stdout.write(
            f"{gefunden} fällige "
            "Synchronisation(en) gefunden."
        )

        for eintrag in ergebnis.get(
            "ergebnisse",
            [],
        ):
            name = (
                str(
                    eintrag.get("name")
                    or "Unbekannte Datenquelle"
                ).strip()
            )

            meldung = (
                str(
                    eintrag.get("meldung")
                    or "Keine Meldung vorhanden."
                ).strip()
            )

            naechster_lauf = (
                eintrag.get(
                    "naechste_synchronisation"
                )
                or "nicht geplant"
            )

            planungsfehler = str(
                eintrag.get("planungsfehler")
                or ""
            ).strip()

            if planungsfehler:
                meldung += (
                    " Planung fehlgeschlagen: "
                    f"{planungsfehler}"
                )

            if eintrag.get("erfolgreich"):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{name}: erfolgreich – "
                        f"{meldung} "
                        f"Nächster Lauf: "
                        f"{naechster_lauf}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"{name}: fehlgeschlagen – "
                        f"{meldung} "
                        f"Nächster Lauf: "
                        f"{naechster_lauf}"
                    )
                )

        if gefunden == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Aktuell ist keine automatische "
                    "Synchronisation fällig."
                )
            )
            return

        fehlgeschlagen = int(
            ergebnis.get(
                "fehlgeschlagen",
                0,
            )
            or 0
        )

        planungsfehler = int(
            ergebnis.get(
                "planungsfehler",
                0,
            )
            or 0
        )

        erfolgreich = int(
            ergebnis.get(
                "erfolgreich",
                0,
            )
            or 0
        )

        self.stdout.write(
            (
                f"Abgeschlossen: {erfolgreich} erfolgreich, "
                f"{fehlgeschlagen} fehlgeschlagen, "
                f"{planungsfehler} Planungsfehler."
            )
        )

        if fehlgeschlagen or planungsfehler:
            raise CommandError(
                "Mindestens eine automatische "
                "Synchronisation oder Neuplanung "
                "ist fehlgeschlagen."
            )
