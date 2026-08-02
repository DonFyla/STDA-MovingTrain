from datetime import datetime, time
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core import signing
from django.http import JsonResponse
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_POST
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from .emails import send_verification_email
from .forms import CustomUserCreationForm
from .models import User
from .tokens import email_verification_token


RATELIMIT_GROUP = "accounts"


def _parse_session_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_session_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except ValueError:
        return None


def _get_dashboard_url(user):
    """Return the appropriate dashboard URL based on user role."""
    if user.is_coach:
        return "scheduling:coach_dashboard"
    return "accounts:dashboard"


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(_get_dashboard_url(user))
    else:
        form = AuthenticationForm()
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("home")


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="ip", rate="10/d", method="POST", block=True)
def signup_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            _create_profile_for_user(user)
            _send_verification_link(request, user)
            return redirect("accounts:signup_done")
    else:
        form = CustomUserCreationForm(
            initial={"form_ts": signing.dumps(str(timezone.now().timestamp()))}
        )
    return render(request, "accounts/signup.html", {"form": form})


def _send_verification_link(request, user):
    """Build the verification URL and email it to the user."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", args=[uid, token])
    )
    send_verification_email(user, verify_url)


def signup_done(request):
    return render(request, "accounts/signup_done.html")


def verify_email(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and user.is_active:
        messages.info(request, "Your email is already verified. You can log in.")
        return redirect("accounts:login")

    if user is not None and email_verification_token.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        login(request, user)
        return redirect(_get_dashboard_url(user))

    return render(request, "accounts/verify_email_invalid.html")


@ratelimit(key="ip", rate="3/m", method="POST", block=True)
def resend_verification(request):
    sent = False
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        user = User.objects.filter(email__iexact=email, is_active=False).first()
        if user is not None:
            _send_verification_link(request, user)
        # Always show the same confirmation to avoid leaking which emails exist.
        sent = True
    return render(request, "accounts/resend_verification.html", {"sent": sent})


def _create_profile_for_user(user):
    """Create a scheduling app profile for a newly registered user."""
    from scheduling.models import Coach, Student

    if user.is_coach:
        Coach.objects.get_or_create(
            user=user,
            defaults={
                "name": user.full_name or user.username or user.email,
                "email": user.email,
            },
        )
    elif user.is_student:
        Student.objects.get_or_create(
            user=user,
            defaults={"parent_phone": user.phone},
        )


@login_required
def dashboard_view(request):
    user = request.user
    today = timezone.now().date()

    if user.is_coach:
        return redirect("scheduling:coach_dashboard")

    # Student dashboard
    from scheduling.models import Booking, FlexibleBooking, SpecialBooking
    from quiz.models import Qtaker
    from payments.points_service import get_balance

    bookings = Booking.objects.filter(student_email=user.email).order_by("-created_at")
    pending_bookings = bookings.filter(status="pending")
    confirmed_bookings = bookings.filter(status="confirmed")
    rejected_bookings = bookings.filter(status="rejected")

    special_bookings = SpecialBooking.objects.filter(student=user).order_by("-created_at")
    pending_special_bookings = special_bookings.filter(status="pending_payment")

    flexible_bookings = FlexibleBooking.objects.filter(user=user).order_by("-session_date", "-start_time")
    upcoming_flexible = flexible_bookings.filter(session_date__gte=today, status__in=["confirmed", "completed"])
    past_flexible = flexible_bookings.filter(session_date__lt=today, status__in=["confirmed", "completed"])
    cancelled_flexible = flexible_bookings.filter(status="cancelled")

    # Build a unified list of upcoming sessions from both recurring and points bookings
    upcoming_sessions = []

    for booking in confirmed_bookings:
        for session in booking.recurring_dates or []:
            session_date = _parse_session_date(session.get("date"))
            if session_date and session_date >= today:
                upcoming_sessions.append({
                    "type": "recurring",
                    "coach": booking.coach,
                    "session_date": session_date,
                    "start_time": _parse_session_time(session.get("start_time")),
                    "end_time": _parse_session_time(session.get("end_time")),
                    "booking": booking,
                })

    for booking in upcoming_flexible:
        upcoming_sessions.append({
            "type": "points",
            "coach": booking.coach,
            "session_date": booking.session_date,
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "booking": booking,
        })

    upcoming_sessions.sort(key=lambda s: (s["session_date"], s["start_time"] or time.min))

    quiz_history = Qtaker.objects.filter(email=user.email).order_by("-date_taken")[:5]

    context = {
        "user": user,
        "bookings": bookings,
        "pending_bookings": pending_bookings,
        "confirmed_bookings": confirmed_bookings,
        "rejected_bookings": rejected_bookings,
        "special_bookings": special_bookings,
        "pending_special_bookings": pending_special_bookings,
        "flexible_bookings": flexible_bookings,
        "past_flexible": past_flexible,
        "cancelled_flexible": cancelled_flexible,
        "upcoming_sessions": upcoming_sessions,
        "user_balance": get_balance(user),
        "quiz_history": quiz_history,
    }
    return render(request, "accounts/dashboard_student.html", context)


@login_required
@require_POST
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def mark_tour_seen(request):
    """Persist or reset the user's role-specific onboarding tour state."""
    user = request.user
    tour = request.POST.get("tour", "")
    seen = request.POST.get("seen", "true").lower() == "true"

    if tour == "student" and not user.is_coach:
        user.student_tour_seen = seen
        user.save(update_fields=["student_tour_seen"])
    elif tour == "coach" and user.is_coach:
        user.coach_tour_seen = seen
        user.save(update_fields=["coach_tour_seen"])
    else:
        return JsonResponse(
            {"success": False, "error": "Invalid tour for this user."},
            status=400,
        )

    return JsonResponse({"success": True, "tour": tour, "seen": seen})
