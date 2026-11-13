from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


STANDARD_WEITERLEITUNG = "/dashboard/"


def _sichere_weiterleitung(request, ziel):
    ziel = str(ziel or "").strip()

    if url_has_allowed_host_and_scheme(
        url=ziel,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ziel

    return STANDARD_WEITERLEITUNG


def login_view(request):
    fehler = ""
    next_url = _sichere_weiterleitung(
        request,
        request.GET.get("next", STANDARD_WEITERLEITUNG),
    )

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        next_url = _sichere_weiterleitung(
            request,
            request.POST.get("next", STANDARD_WEITERLEITUNG),
        )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None and getattr(user, "is_active", True):
            login(request, user)
            return redirect(next_url)

        fehler = (
            "Benutzername oder Passwort ist falsch oder das Benutzerkonto "
            "ist noch nicht aktiviert."
        )

    return render(
        request,
        "lizenzen/login.html",
        {
            "fehler": fehler,
            "next": next_url,
        },
    )


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def startseite(request):
    return redirect("dashboard")
