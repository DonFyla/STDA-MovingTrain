from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from .models import Post


def _make_user(email, coach=False):
    return User.objects.create_user(
        email=email,
        username=email.split("@")[0],
        password="testpass123",
        is_coach=coach,
        is_student=not coach,
    )


def _make_post(author, title="Sample Post", status=Post.STATUS_PUBLISHED):
    post = Post.objects.create(
        author=author,
        title=title,
        excerpt="A short summary.",
        body="<p>Body text.</p>",
    )
    if status == Post.STATUS_PUBLISHED:
        post.publish()
        post.save()
    return post


class BlogPublicViewTests(TestCase):
    def setUp(self):
        self.coach = _make_user("coach@example.com", coach=True)

    def test_list_shows_published_posts(self):
        _make_post(self.coach, title="Published One")
        response = self.client.get(reverse("blog:post_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published One")

    def test_list_hides_drafts(self):
        _make_post(self.coach, title="Secret Draft", status=Post.STATUS_DRAFT)
        response = self.client.get(reverse("blog:post_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secret Draft")

    def test_detail_renders_published_post(self):
        post = _make_post(self.coach)
        response = self.client.get(reverse("blog:post_detail", args=[post.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, post.title)

    def test_detail_returns_404_for_draft(self):
        post = _make_post(self.coach, status=Post.STATUS_DRAFT)
        response = self.client.get(reverse("blog:post_detail", args=[post.slug]))
        self.assertEqual(response.status_code, 404)


class BlogManageViewTests(TestCase):
    def setUp(self):
        self.coach = _make_user("author@example.com", coach=True)
        self.other_coach = _make_user("other@example.com", coach=True)

    def _create_payload(self, **overrides):
        data = {
            "title": "My New Post",
            "excerpt": "Summary here.",
            "body": "<p>Hello world.</p>",
            "action": "publish",
        }
        data.update(overrides)
        return data

    def test_coach_can_publish_post(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("blog:post_create"), self._create_payload()
        )
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(title="My New Post")
        self.assertEqual(post.author, self.coach)
        self.assertTrue(post.is_published)
        self.assertIsNotNone(post.published_at)

    def test_save_as_draft_keeps_unpublished(self):
        self.client.force_login(self.coach)
        self.client.post(
            reverse("blog:post_create"), self._create_payload(action="draft")
        )
        post = Post.objects.get(title="My New Post")
        self.assertFalse(post.is_published)
        self.assertIsNone(post.published_at)

    def test_edit_own_post(self):
        post = _make_post(self.coach, title="Original Title")
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("blog:post_edit", args=[post.slug]),
            self._create_payload(title="Renamed Title"),
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.title, "Renamed Title")

    def test_cannot_edit_others_post(self):
        post = _make_post(self.other_coach)
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("blog:post_edit", args=[post.slug]),
            self._create_payload(title="Hijacked"),
        )
        self.assertEqual(response.status_code, 404)
        post.refresh_from_db()
        self.assertNotEqual(post.title, "Hijacked")

    def test_cannot_delete_others_post(self):
        post = _make_post(self.other_coach)
        self.client.force_login(self.coach)
        response = self.client.post(reverse("blog:post_delete", args=[post.slug]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())

    def test_delete_own_post(self):
        post = _make_post(self.coach)
        self.client.force_login(self.coach)
        response = self.client.post(reverse("blog:post_delete", args=[post.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_manage_views_require_login(self):
        response = self.client.get(reverse("blog:my_posts"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    @override_settings(BLOG_ALLOW_STUDENT_POSTS=False)
    def test_student_blocked_when_flag_off(self):
        student = _make_user("student@example.com")
        self.client.force_login(student)
        response = self.client.get(reverse("blog:post_create"))
        self.assertEqual(response.status_code, 403)

    @override_settings(BLOG_ALLOW_STUDENT_POSTS=True)
    def test_student_allowed_when_flag_on(self):
        student = _make_user("student2@example.com")
        self.client.force_login(student)
        response = self.client.get(reverse("blog:post_create"))
        self.assertEqual(response.status_code, 200)


class BlogModelTests(TestCase):
    def setUp(self):
        self.coach = _make_user("slugger@example.com", coach=True)

    def test_slug_generated_from_title(self):
        post = _make_post(self.coach, title="Hello Chess World")
        self.assertEqual(post.slug, "hello-chess-world")

    def test_slug_unique_on_collision(self):
        first = _make_post(self.coach, title="Same Title")
        second = _make_post(self.coach, title="Same Title")
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(second.slug.startswith("same-title"))

    def test_publish_sets_published_at_once(self):
        post = _make_post(self.coach, status=Post.STATUS_DRAFT)
        post.publish()
        post.save()
        first_time = post.published_at
        self.assertIsNotNone(first_time)
        post.publish()
        post.save()
        self.assertEqual(post.published_at, first_time)
