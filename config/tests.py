from django.test import TestCase
from django.urls import reverse


class RootRedirectTests(TestCase):
    def test_root_redirect(self):
        response = self.client.get(reverse('root_redirect'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard-home'))
