import hashlib
from datetime import timedelta
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login
from django.db import transaction
from django.utils import timezone
from .models import LoginAttempt


class RequestBoundaryMiddleware:
    """Reject oversized requests before parsing and keep health pages out of caches."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.http import HttpResponse

        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (ValueError, TypeError):
            return HttpResponse("Invalid request length.", status=400)
        if length < 0 or length > 12 * 1024 * 1024:
            return HttpResponse("Request exceeds 12 MB limit.", status=413)
        response = self.get_response(request)
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "private, no-store"
            response["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; worker-src 'self'; "
                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
            )
            response["Permissions-Policy"] = "geolocation=(), microphone=()"
        return response


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not (
            request.path in ["/login/", "/health", "/manifest.webmanifest", "/sw.js"]
            or request.path.startswith("/static/")
        ):
            return redirect("/login/")
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        from .models import Profile

        try:
            name = (
                Profile.objects.filter(user=request.user)
                .values_list("timezone", flat=True)
                .first()
                if request.user.is_authenticated
                else None
            )
            timezone.activate(ZoneInfo(name)) if name else timezone.deactivate()
        except (ZoneInfoNotFoundError, ValueError):
            timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()


def login_view(request):
    error = ""
    if request.method == "POST":
        key = hashlib.sha256(
            request.META.get("REMOTE_ADDR", "unknown").encode()
        ).hexdigest()
        with transaction.atomic():
            row, _ = LoginAttempt.objects.select_for_update().get_or_create(key=key)
            if row.window < timezone.now() - timedelta(minutes=15):
                row.count = 0
                row.window = timezone.now()
            if row.count >= 5:
                return render(
                    request,
                    "core/login.html",
                    {"error": "Too many attempts. Try again in 15 minutes."},
                    status=429,
                )
            row.count += 1
            row.save()
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user:
            login(request, user)
            LoginAttempt.objects.filter(key=key).delete()
            return redirect("/")
        error = "Username or password is incorrect."
    return render(request, "core/login.html", {"error": error})
