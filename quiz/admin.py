from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Qtaker, Question, Questionnaire, Options, QuestionResult, Badge, UserBadge, Activity


@admin.register(Qtaker)
class QtakerAdmin(admin.ModelAdmin):
    list_display = ["name", "age", "email", "skill", "test_result", "date_taken"]


class AnswerInline(admin.TabularInline):
    model = Options


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = [
        "questionnaire",
        "question_preview",
        "placement",
        "is_approved",
        "created_at",
        "updated_at",
        "created_by",
    ]
    list_filter = ["is_approved", "questionnaire"]
    list_editable = ["is_approved"]
    inlines = [AnswerInline]

    def question_preview(self, obj):
        return mark_safe(obj.question)

    question_preview.short_description = "Question"


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ["title", "motif", "difficulty", "created_at", "created_by"]
    list_filter = ["motif", "difficulty"]


@admin.register(QuestionResult)
class QuestionResultAdmin(admin.ModelAdmin):
    list_display = ["qtaker", "question", "correct", "created_at"]
    list_filter = ["correct"]
    readonly_fields = ["qtaker", "question", "answer_given", "correct", "created_at"]


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "motif", "difficulty", "icon", "created_at"]
    list_filter = ["motif", "difficulty"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ["user", "badge", "awarded_at"]
    list_filter = ["badge"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "text", "created_at"]
    list_filter = ["kind"]
    readonly_fields = ["user", "kind", "badge", "text", "created_at"]
