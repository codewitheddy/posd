from django.test import TestCase
from accounting import api

class ApiTest(TestCase):
    def test_status(self):
        self.assertTrue(api.get_module_status()["is_ready"])
