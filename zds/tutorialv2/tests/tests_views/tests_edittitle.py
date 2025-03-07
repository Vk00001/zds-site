from datetime import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from zds.tutorialv2.models.database import PublishableContent
from zds.tutorialv2.views.contents import EditTitleForm, EditTitle
from zds.tutorialv2.tests import TutorialTestMixin, override_for_contents
from zds.tutorialv2.tests.factories import PublishableContentFactory
from zds.member.tests.factories import ProfileFactory, StaffProfileFactory


@override_for_contents()
class PermissionTests(TutorialTestMixin, TestCase):
    """Test permissions and associated behaviors, such as redirections and status codes."""

    def setUp(self):
        # Create users
        self.author = ProfileFactory().user
        self.staff = StaffProfileFactory().user
        self.outsider = ProfileFactory().user

        # Create a content
        self.content = PublishableContentFactory(author_list=[self.author])

        # Get information to be reused in tests
        self.form_url = reverse("content:edit-title", kwargs={"pk": self.content.pk})
        self.form_data = {"title": self.content.title}  # avoids changing the slug
        self.content_data = {"pk": self.content.pk, "slug": self.content.slug}
        self.content_url = reverse("content:view", kwargs=self.content_data)
        self.login_url = reverse("member-login") + "?next=" + self.form_url

    def test_not_authenticated(self):
        """Test that on form submission, unauthenticated users are redirected to the login page."""
        self.client.logout()  # ensure no user is authenticated
        response = self.client.post(self.form_url, self.form_data)
        self.assertRedirects(response, self.login_url)

    def test_authenticated_author(self):
        """Test that on form submission, authors are redirected to the content page."""
        self.client.force_login(self.author)
        response = self.client.post(self.form_url, self.form_data)
        self.assertRedirects(response, self.content_url)

    def test_authenticated_staff(self):
        """Test that on form submission, staffs are redirected to the content page."""
        self.client.force_login(self.staff)
        response = self.client.post(self.form_url, self.form_data)
        self.assertRedirects(response, self.content_url)

    def test_authenticated_outsider(self):
        """Test that on form submission, unauthorized users get a 403."""
        self.client.force_login(self.outsider)
        response = self.client.post(self.form_url, self.form_data)
        self.assertEqual(response.status_code, 403)


@override_for_contents()
class WorkflowTests(TutorialTestMixin, TestCase):
    """Test the workflow of the form, such as validity errors and success messages."""

    def setUp(self):
        # Create a user
        self.author = ProfileFactory()

        # Create a content
        self.content = PublishableContentFactory(author_list=[self.author.user])

        # Get information to be reused in tests
        self.form_url = reverse("content:edit-title", kwargs={"pk": self.content.pk})
        self.error_messages = EditTitleForm.declared_fields["title"].error_messages
        self.success_message = EditTitle.success_message

        # Log in with an authorized user (e.g the author of the content)
        self.client.force_login(self.author.user)

    def get_test_cases(self):
        special_char_for_slug = "/"
        max_length = PublishableContent._meta.get_field("title").max_length
        too_long = "a" * (max_length + 1)
        return {
            "empty_form": {"inputs": {}, "expected_outputs": [self.success_message]},
            "empty_fields": {"inputs": {"title": ""}, "expected_outputs": [self.success_message]},
            "basic_success": {"inputs": {"title": "Titre"}, "expected_outputs": [self.success_message]},
            "stripped_to_empty": {"inputs": {"title": " "}, "expected_outputs": [self.success_message]},
            "too_long": {
                "inputs": {"title": too_long},
                "expected_outputs": [_("Assurez-vous que cette valeur comporte au plus")],
            },
            "invalid_slug": {
                "inputs": {"title": special_char_for_slug},
                "expected_outputs": [EditTitleForm.error_messages["bad_slug"].format(special_char_for_slug)],
            },
        }

    def test_form_workflow(self):
        test_cases = self.get_test_cases()
        for case_name, case in test_cases.items():
            with self.subTest(msg=case_name):
                response = self.client.post(self.form_url, case["inputs"], follow=True)
                for msg in case["expected_outputs"]:
                    self.assertContains(response, escape(msg))


@override_for_contents()
class FunctionalTests(TutorialTestMixin, TestCase):
    """Test the detailed behavior of the feature, such as updates of the database or repositories."""

    def setUp(self):
        self.author = ProfileFactory()
        self.content = PublishableContentFactory(author_list=[self.author.user])
        self.form_url = reverse("content:edit-title", kwargs={"pk": self.content.pk})
        self.client.force_login(self.author.user)

    def test_normal(self):
        self.assertEqual(self.content.title, self.content.gallery.title)
        start_date = datetime.now()
        self.assertTrue(self.content.update_date < start_date)

        new_title = "Ceci n'est pas un ancien titre"
        response = self.client.post(self.form_url, {"title": new_title}, follow=True)
        self.assertEqual(response.status_code, 200)

        self.content.refresh_from_db()

        self.assertEqual(self.content.title, new_title)
        self.assertTrue(self.content.update_date > start_date)
        self.assertEqual(self.content.title, self.content.gallery.title)

        # Update in repository
        versioned_content = self.content.load_version()
        self.assertEqual(self.content.title, versioned_content.title)

        # Reachable with new slug
        response = self.client.get(reverse("content:view", kwargs={"pk": self.content.pk, "slug": self.content.slug}))
        self.assertEqual(response.status_code, 200)

    def test_empty(self):
        empty_title = ""
        default_when_empty = "Titre par défaut"
        response = self.client.post(self.form_url, {"title": empty_title}, follow=True)

        self.assertEqual(response.status_code, 200)

        self.content.refresh_from_db()
        self.assertEqual(self.content.title, default_when_empty)
