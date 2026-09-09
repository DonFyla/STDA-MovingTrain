from django.http import Http404
from django.shortcuts import render
from scheduling.models import Coach
from .data import (
    TUTORS,
    EVENTS,
    GALLERY,
    COURSES,
    TESTIMONIALS,
    COURSE_CURRICULA,
)


def home(request):
    featured_coaches = Coach.objects.filter(featured_order__isnull=False).order_by("featured_order")[:4]
    context = {
        "courses": COURSES[:3],
        "tutors": TUTORS,
        "coaches": featured_coaches,
        "testimonials": TESTIMONIALS,
        "gallery": GALLERY[:6],
        "hero_cards": GALLERY[6:10],
    }
    return render(request, "web/home.html", context)


def courses(request):
    return render(request, "web/courses.html", {"courses": COURSES})


def tutors(request):
    special_coaches = Coach.objects.filter(is_special=True).order_by("featured_order", "name")
    normal_coaches = Coach.objects.filter(is_special=False).order_by("featured_order", "name")
    return render(request, "web/tutors.html", {
        "special_coaches": special_coaches,
        "normal_coaches": normal_coaches,
    })


def gallery(request):
    return render(request, "web/gallery.html", {"gallery": GALLERY, "events": EVENTS})


def _coach_initials(name):
    parts = [p for p in name.split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[1][0]).upper()


def course_detail(request, slug):
    course = COURSE_CURRICULA.get(slug)
    if not course:
        raise Http404("Course not found")

    colors = ["violet", "blue", "emerald", "pink", "amber", "purple", "orange"]
    instructors = []
    for index, coach in enumerate(Coach.objects.all().order_by("featured_order", "name")):
        instructors.append({
            "coach": coach,
            "initials": _coach_initials(coach.name),
            "color": colors[index % len(colors)],
        })

    context = {
        "course": course,
        "instructors": instructors,
        "slug": slug,
    }
    return render(request, "web/course_detail.html", context)
