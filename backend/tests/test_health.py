from django.test import SimpleTestCase


class HealthEndpointTests(SimpleTestCase):
    def test_health_is_public_and_does_not_expose_configuration(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_health_does_not_accept_state_changing_requests(self):
        response = self.client.post("/api/v1/health/")
        self.assertEqual(response.status_code, 405)
