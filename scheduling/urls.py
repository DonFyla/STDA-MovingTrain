from django.urls import path
from . import views

app_name = "scheduling"

urlpatterns = [
    path("", views.schedule_index, name="index"),
    path("coach/dashboard/", views.coach_dashboard_view, name="coach_dashboard"),
    path("book/<uuid:coach_id>/", views.book_coach_view, name="book_coach"),
    path("book/confirmation/<uuid:booking_id>/", views.booking_confirmation_view, name="booking_confirmation"),
    path("book/flexible-confirmation/<uuid:booking_id>/", views.flexible_booking_confirmation_view, name="flexible_booking_confirmation"),
    path("book/special-confirmation/<uuid:booking_id>/", views.special_booking_confirmation_view, name="special_booking_confirmation"),
    path("book/retry-payment/<uuid:booking_id>/", views.retry_booking_payment_view, name="retry_booking_payment"),
    path("book/retry-special-payment/<uuid:booking_id>/", views.retry_special_payment_view, name="retry_special_payment"),
]
