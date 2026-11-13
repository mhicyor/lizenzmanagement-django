from django.conf import settings
from django.db import models
from django.utils import timezone


class BenutzerEinladung(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lizenzmanagement_einladung",
    )
    eingeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versendete_lizenzmanagement_einladungen",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateTimeField()
    angenommen_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-erstellt_am",)
        verbose_name = "Benutzereinladung"
        verbose_name_plural = "Benutzereinladungen"

    @property
    def ist_gueltig(self):
        return (
            self.angenommen_am is None
            and (
                self.user is None
                or not self.user.is_active
            )
            and self.gueltig_bis > timezone.now()
        )


class LizenzAenderung(models.Model):
    AKTION_ERSTELLT = "erstellt"
    AKTION_BEARBEITET = "bearbeitet"
    AKTIONEN = (
        (AKTION_ERSTELLT, "Lizenz angelegt"),
        (AKTION_BEARBEITET, "Lizenz bearbeitet"),
    )

    lizenz_id = models.PositiveIntegerField(db_index=True)
    lizenz_name = models.CharField(max_length=255)
    aktion = models.CharField(max_length=20, choices=AKTIONEN)
    ausgefuehrt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lizenz_aenderungen",
    )
    ausgefuehrt_von_name = models.CharField(max_length=255)
    aenderungen = models.JSONField(default=dict, blank=True)
    erstellt_am = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-erstellt_am", "-id")
        verbose_name = "Lizenzänderung"
        verbose_name_plural = "Lizenzänderungen"

    def __str__(self):
        return (
            f"{self.get_aktion_display()}: {self.lizenz_name} "
            f"({self.ausgefuehrt_von_name})"
        )
