from django.contrib import admin
from .models import (
    Coach,
    Student,
    AvailabilitySlot,
    Booking,
    FlexibleBooking,
    SpecialBooking,
    CoachBlockedDate,
    SessionNote,
)


class AvailabilitySlotInline(admin.TabularInline):
    model = AvailabilitySlot
    extra = 1


class CoachBlockedDateInline(admin.TabularInline):
    model = CoachBlockedDate
    extra = 1


@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "email",
        "is_admin",
        "is_special",
        "points_cost",
        "featured_order",
        "created_at",
    ]
    list_filter = ["is_admin", "is_special"]
    search_fields = ["name", "email", "specialization"]
    inlines = [AvailabilitySlotInline, CoachBlockedDateInline]


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ["coach", "day_of_week", "start_time", "end_time"]
    list_filter = ["day_of_week", "coach"]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "student_name",
        "coach",
        "booking_date",
        "status",
        "payment_status",
        "subscription_status",
        "next_billing_date",
        "created_at",
    ]
    list_filter = ["status", "payment_status", "subscription_status", "course_type", "coach"]
    search_fields = ["student_name", "student_email"]
    readonly_fields = ["flutterwave_payment_plan_id", "flutterwave_subscription_id"]
    actions = ["cancel_selected_subscriptions"]

    @admin.action(description="Cancel selected active subscriptions on Flutterwave")
    def cancel_selected_subscriptions(self, request, queryset):
        from payments.flutterwave_service import cancel_subscription, cancel_payment_plan

        cancelled = 0
        for booking in queryset.filter(subscription_status="active"):
            if booking.flutterwave_subscription_id:
                result = cancel_subscription(booking.flutterwave_subscription_id)
            elif booking.flutterwave_payment_plan_id:
                result = cancel_payment_plan(booking.flutterwave_payment_plan_id)
            else:
                continue

            if result["success"]:
                booking.subscription_status = "cancelled"
                booking.status = "cancelled"
                booking.save(update_fields=["subscription_status", "status"])
                cancelled += 1
            else:
                self.message_user(
                    request,
                    f"Failed to cancel subscription for {booking}: {result['message']}",
                    level="error",
                )

        self.message_user(request, f"Cancelled {cancelled} subscription(s).")


@admin.register(FlexibleBooking)
class FlexibleBookingAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "coach",
        "session_date",
        "start_time",
        "points_used",
        "status",
    ]
    list_filter = ["status", "coach"]
    search_fields = ["user__email", "coach__name"]


@admin.register(SpecialBooking)
class SpecialBookingAdmin(admin.ModelAdmin):
    list_display = [
        "student_name",
        "coach",
        "total_sessions",
        "status",
        "total_amount",
        "created_at",
    ]
    list_filter = ["status", "coach"]
    search_fields = ["student_name", "student_email"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "parent_name",
        "school",
        "chess_rating",
        "created_at",
    ]
    list_filter = ["school"]
    search_fields = ["user__email", "user__full_name", "parent_name", "school"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CoachBlockedDate)
class CoachBlockedDateAdmin(admin.ModelAdmin):
    list_display = ["coach", "blocked_date", "start_time", "end_time", "reason"]
    list_filter = ["coach", "blocked_date"]


@admin.register(SessionNote)
class SessionNoteAdmin(admin.ModelAdmin):
    list_display = ["student", "coach", "session_date", "created_at"]
    list_filter = ["coach", "session_date"]
    search_fields = ["student__email", "student__full_name", "content"]
    readonly_fields = ["created_at", "updated_at"]
