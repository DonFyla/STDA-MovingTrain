from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PostForm
from .models import Post
from .utils import can_publish_blog


def _published_posts():
    return Post.objects.filter(status=Post.STATUS_PUBLISHED).select_related("author")


def _require_author(user):
    if not can_publish_blog(user):
        raise PermissionDenied


def _apply_submit_action(post, action):
    if action == "publish":
        post.publish()
    else:
        post.status = Post.STATUS_DRAFT


# ---------- Public views ----------

def post_list(request):
    posts = _published_posts()
    paginator = Paginator(posts, 6)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "blog/list.html", {"page_obj": page_obj})


def post_detail(request, slug):
    post = get_object_or_404(_published_posts(), slug=slug)
    more_posts = _published_posts().exclude(pk=post.pk)[:3]
    return render(
        request,
        "blog/detail.html",
        {"post": post, "more_posts": more_posts},
    )


# ---------- Author (manage) views ----------

@login_required
def my_posts(request):
    _require_author(request.user)
    posts = Post.objects.filter(author=request.user)
    return render(request, "blog/manage_list.html", {"posts": posts})


@login_required
def post_create(request):
    _require_author(request.user)
    form = PostForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        _apply_submit_action(post, request.POST.get("action"))
        post.save()
        if post.is_published:
            messages.success(request, "Your post is now live.")
        else:
            messages.success(request, "Draft saved.")
        return redirect("blog:my_posts")
    return render(
        request,
        "blog/form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def post_edit(request, slug):
    _require_author(request.user)
    post = get_object_or_404(Post, slug=slug, author=request.user)
    form = PostForm(request.POST or None, request.FILES or None, instance=post)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        _apply_submit_action(post, request.POST.get("action"))
        post.save()
        if post.is_published:
            messages.success(request, "Post updated.")
        else:
            messages.success(request, "Draft saved.")
        return redirect("blog:my_posts")
    return render(
        request,
        "blog/form.html",
        {"form": form, "is_edit": True, "post": post},
    )


@login_required
@require_POST
def post_delete(request, slug):
    _require_author(request.user)
    post = get_object_or_404(Post, slug=slug, author=request.user)
    post.delete()
    messages.success(request, "Post deleted.")
    return redirect("blog:my_posts")
