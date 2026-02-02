import unittest

from core import app
import routes.public_routes  # noqa: F401
import routes.auth_routes  # noqa: F401
import routes.admin_routes  # noqa: F401


class SmokeRouteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_public_pages_load(self):
        for path in ["/", "/auth-center", "/about"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_pwa_assets_load(self):
        manifest = self.client.get("/manifest.json")
        self.assertEqual(manifest.status_code, 200)
        self.assertIn("application/manifest+json", manifest.headers.get("Content-Type", ""))

        service_worker = self.client.get("/service-worker.js")
        self.assertEqual(service_worker.status_code, 200)

    def test_states_api_works(self):
        response = self.client.get("/api/states")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("states"), list)


if __name__ == "__main__":
    unittest.main()
