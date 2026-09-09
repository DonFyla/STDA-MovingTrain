from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="post_list"),
    path("manage/", views.my_posts, name="my_posts"),
    path("manage/new/", views.post_create, name="post_create"),
    path("manage/<slug:slug>/edit/", views.post_edit, name="post_edit"),
    path("manage/<slug:slug>/delete/", views.post_delete, name="post_delete"),
    path("<slug:slug>/", views.post_detail, name="post_detail"),
]
