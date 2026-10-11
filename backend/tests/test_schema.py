from django.test import SimpleTestCase


class SchemaEndpointTests(SimpleTestCase):
    def test_public_schema_describes_live_health_response(self):
        response = self.client.get("/api/v1/schema/")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["openapi"], "3.0.3")
        self.assertEqual(schema["paths"]["/api/v1/health/"]["get"]["operationId"], "getHealth")
        self.assertEqual(response["Cache-Control"], "no-store")
        health = self.client.get("/api/v1/health/").json()
        specification = schema["components"]["schemas"]["Health"]
        self.assertEqual(set(health), set(specification["required"]))
        self.assertIn(health["status"], specification["properties"]["status"]["enum"])

    def test_schema_rejects_state_changing_requests(self):
        self.assertEqual(self.client.post("/api/v1/schema/").status_code, 405)
