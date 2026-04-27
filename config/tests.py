from django.test import TestCase


class ApiDocsCompatibilityTest(TestCase):
    def test_legacy_swagger_json_redirects_to_openapi_spec(self):
        response = self.client.get("/api-docs/swagger.json")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/api/openapi.json")

    def test_openapi_json_remains_available(self):
        response = self.client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_other_api_docs_paths_remain_not_found(self):
        response = self.client.get("/api-docs/unknown")

        self.assertEqual(response.status_code, 404)
