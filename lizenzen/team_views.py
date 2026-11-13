import hashlib
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import (
    get_user_model,
    login,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import BenutzerEinladung
from .view_helpers import _modal_darstellung, _modal_nachricht_response


User = get_user_model()
EINLADUNG_GUELTIGKEIT_TAGE = 7


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ist_team_admin(user):
    return user.is_authenticated and user.is_active and user.is_staff


def _ist_gueltige_email(email):
    try:
        validate_email(email)
    except ValidationError:
        return False
    return True


@login_required
@require_http_methods(["GET", "POST"])
def team_verwalten(request):
    if not _ist_team_admin(request.user):
        return HttpResponseForbidden(
            "Nur Administratoren dürfen Benutzer einladen."
        )

    fehler = ""
    erfolg = ""
    einladungslink = ""
    ist_modal, template_basis = _modal_darstellung(request)

    if request.method == "POST":
        token = secrets.token_urlsafe(32)
        BenutzerEinladung.objects.create(
            eingeladen_von=request.user,
            token_hash=_token_hash(token),
            gueltig_bis=(
                timezone.now()
                + timedelta(days=EINLADUNG_GUELTIGKEIT_TAGE)
            ),
        )
        einladungslink = request.build_absolute_uri(
            reverse("einladung_annehmen", args=[token])
        )
        erfolg = (
            "Ein neuer Einladungslink wurde erstellt. "
            "Er ist sieben Tage gültig und nur einmal verwendbar."
        )

    return render(
        request,
        "lizenzen/team.html",
        {
            "benutzer_liste": User.objects.order_by(
                "-is_active", "-is_superuser", "-is_staff", "username"
            ),
            "fehler": fehler,
            "erfolg": erfolg,
            "einladungslink": einladungslink,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
@require_http_methods(["POST"])
def benutzer_loeschen(request, user_id):
    if not _ist_team_admin(request.user):
        return HttpResponseForbidden(
            "Nur Administratoren dürfen Benutzer löschen."
        )

    benutzer = get_object_or_404(User, pk=user_id)

    if benutzer.pk == request.user.pk:
        messages.error(
            request,
            "Du kannst dein eigenes Benutzerkonto hier nicht löschen.",
        )
    elif benutzer.is_superuser and not request.user.is_superuser:
        messages.error(
            request,
            "Nur ein Admin darf einen anderen Admin löschen.",
        )
    elif (
        benutzer.is_staff
        and benutzer.is_active
        and User.objects.filter(is_staff=True, is_active=True).count() <= 1
    ):
        messages.error(
            request,
            "Der letzte aktive Administrator kann nicht gelöscht werden.",
        )
    else:
        anzeigename = benutzer.get_full_name() or benutzer.username
        benutzer.delete()
        messages.success(
            request,
            f"{anzeigename} wurde aus dem Team entfernt.",
        )

    ziel = reverse("team_verwalten")
    if request.POST.get("modal") == "1":
        ziel = f"{ziel}?modal=1"
    return redirect(ziel)


@login_required
@require_http_methods(["POST"])
def benutzer_zum_superuser_machen(request, user_id):
    if not request.user.is_active or not request.user.is_superuser:
        return HttpResponseForbidden(
            "Nur ein vorhandener Admin darf diese Berechtigung vergeben."
        )

    benutzer = get_object_or_404(User, pk=user_id)

    if benutzer.pk == request.user.pk:
        messages.info(request, "Dein Konto ist bereits ein Admin.")
    elif benutzer.is_superuser:
        messages.info(
            request,
            "Dieses Benutzerkonto ist bereits ein Admin.",
        )
    elif not benutzer.is_active:
        messages.error(
            request,
            "Ein inaktives Benutzerkonto kann nicht hochgestuft werden.",
        )
    else:
        benutzer.is_staff = True
        benutzer.is_superuser = True
        benutzer.save(update_fields=["is_staff", "is_superuser"])
        anzeigename = benutzer.get_full_name() or benutzer.username
        messages.success(
            request,
            f"{anzeigename} ist jetzt Admin.",
        )

    ziel = reverse("team_verwalten")
    if request.POST.get("modal") == "1":
        ziel = f"{ziel}?modal=1"
    return redirect(ziel)


@login_required
@require_http_methods(["GET", "POST"])
def profil_bearbeiten(request):
    ist_modal, template_basis = _modal_darstellung(request)
    fehler = ""
    erfolg = ""

    formular_daten = {
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "email": request.user.email,
    }
    loginname_folgt_email = bool(request.user.email) and (
        request.user.username.casefold()
        == request.user.email.casefold()
    )

    if request.method == "POST":
        formular_daten = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
        }
        aktuelles_passwort = request.POST.get("current_password", "")
        neues_passwort = request.POST.get("new_password", "")
        passwort_bestaetigung = request.POST.get(
            "new_password_confirm", ""
        )
        passwort_wird_geaendert = bool(
            aktuelles_passwort
            or neues_passwort
            or passwort_bestaetigung
        )

        if loginname_folgt_email and not formular_daten["email"]:
            fehler = (
                "Die E-Mail-Adresse ist zugleich dein Anmeldename und "
                "darf nicht leer sein."
            )
        elif formular_daten["email"] and not _ist_gueltige_email(
            formular_daten["email"]
        ):
            fehler = "Bitte eine gültige E-Mail-Adresse angeben."
        elif (
            formular_daten["email"]
            and User.objects.filter(
                email__iexact=formular_daten["email"]
            ).exclude(pk=request.user.pk).exists()
        ):
            fehler = "Diese E-Mail-Adresse wird bereits verwendet."
        elif (
            loginname_folgt_email
            and User.objects.filter(
                username__iexact=formular_daten["email"]
            ).exclude(pk=request.user.pk).exists()
        ):
            fehler = "Diese E-Mail-Adresse wird bereits verwendet."
        elif passwort_wird_geaendert and not request.user.check_password(
            aktuelles_passwort
        ):
            fehler = "Das aktuelle Passwort ist nicht korrekt."
        elif passwort_wird_geaendert and not neues_passwort:
            fehler = "Bitte ein neues Passwort eingeben."
        elif passwort_wird_geaendert and (
            neues_passwort != passwort_bestaetigung
        ):
            fehler = "Die neuen Passwörter stimmen nicht überein."
        elif passwort_wird_geaendert:
            try:
                validate_password(
                    neues_passwort,
                    user=request.user,
                )
            except ValidationError as validation_fehler:
                fehler = " ".join(validation_fehler.messages)

        if not fehler:
            request.user.first_name = formular_daten["first_name"]
            request.user.last_name = formular_daten["last_name"]
            request.user.email = formular_daten["email"]
            zu_speichern = ["first_name", "last_name", "email"]

            if loginname_folgt_email:
                request.user.username = formular_daten["email"]
                zu_speichern.append("username")

            if passwort_wird_geaendert:
                request.user.set_password(neues_passwort)
                zu_speichern.append("password")

            request.user.save(update_fields=zu_speichern)

            if passwort_wird_geaendert:
                update_session_auth_hash(request, request.user)

            if ist_modal:
                return _modal_nachricht_response("profil_gespeichert")

            erfolg = "Dein Profil wurde gespeichert."

    return render(
        request,
        "lizenzen/profil.html",
        {
            "fehler": fehler,
            "erfolg": erfolg,
            "formular_daten": formular_daten,
            "loginname_folgt_email": loginname_folgt_email,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@require_http_methods(["GET", "POST"])
def einladung_annehmen(request, token):
    einladung = BenutzerEinladung.objects.select_related("user").filter(
        token_hash=_token_hash(token)
    ).first()
    fehler = ""
    formular_daten = {
        "first_name": "",
        "last_name": "",
        "email": "",
    }

    if einladung is None or not einladung.ist_gueltig:
        return render(
            request,
            "lizenzen/einladung_annehmen.html",
            {
                "einladung": None,
                "fehler": (
                    "Diese Einladung ist ungültig, abgelaufen oder wurde "
                    "bereits verwendet."
                ),
            },
            status=400,
        )

    if request.method == "POST":
        formular_daten = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
        }
        passwort = request.POST.get("password", "")
        passwort_bestaetigung = request.POST.get(
            "password_confirm", ""
        )

        bestehender_benutzer = einladung.user
        benutzer_abfrage = User.objects.all()
        if bestehender_benutzer is not None:
            benutzer_abfrage = benutzer_abfrage.exclude(
                pk=bestehender_benutzer.pk
            )

        if not all(formular_daten.values()):
            fehler = "Bitte Vorname, Nachname und E-Mail-Adresse angeben."
        elif not _ist_gueltige_email(formular_daten["email"]):
            fehler = "Bitte eine gültige E-Mail-Adresse angeben."
        elif benutzer_abfrage.filter(
            email__iexact=formular_daten["email"]
        ).exists():
            fehler = "Für diese E-Mail-Adresse existiert bereits ein Konto."
        elif (
            bestehender_benutzer is None
            and benutzer_abfrage.filter(
                username__iexact=formular_daten["email"]
            ).exists()
        ):
            fehler = "Für diese E-Mail-Adresse existiert bereits ein Konto."
        elif not passwort:
            fehler = "Bitte ein Passwort eingeben."
        elif passwort != passwort_bestaetigung:
            fehler = "Die eingegebenen Passwörter stimmen nicht überein."
        else:
            pruef_benutzer = bestehender_benutzer or User(
                username=formular_daten["email"],
                email=formular_daten["email"],
            )
            pruef_benutzer.first_name = formular_daten["first_name"]
            pruef_benutzer.last_name = formular_daten["last_name"]
            try:
                validate_password(passwort, user=pruef_benutzer)
            except ValidationError as validation_fehler:
                fehler = " ".join(validation_fehler.messages)

        if not fehler:
            try:
                with transaction.atomic():
                    aktuelle_einladung = (
                        BenutzerEinladung.objects.select_for_update()
                        .select_related("user")
                        .get(pk=einladung.pk)
                    )

                    if not aktuelle_einladung.ist_gueltig:
                        fehler = (
                            "Diese Einladung wurde inzwischen bereits "
                            "verwendet oder ist abgelaufen."
                        )
                    else:
                        user = aktuelle_einladung.user
                        if user is None:
                            user = User(
                                username=formular_daten["email"],
                                is_staff=False,
                                is_superuser=False,
                            )

                        user.first_name = formular_daten["first_name"]
                        user.last_name = formular_daten["last_name"]
                        user.email = formular_daten["email"]
                        user.is_active = True
                        user.set_password(passwort)
                        user.save()

                        aktuelle_einladung.user = user
                        aktuelle_einladung.angenommen_am = timezone.now()
                        aktuelle_einladung.save(
                            update_fields=["user", "angenommen_am"]
                        )
            except IntegrityError:
                fehler = (
                    "Für diese E-Mail-Adresse existiert inzwischen bereits "
                    "ein Konto."
                )

            if not fehler:
                login(request, user)
                return redirect("dashboard")

    return render(
        request,
        "lizenzen/einladung_annehmen.html",
        {
            "einladung": einladung,
            "fehler": fehler,
            "formular_daten": formular_daten,
        },
    )
