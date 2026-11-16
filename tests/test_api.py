import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.controllers.api import app


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_ok(self):
        with patch("src.controllers.api.declare_voting_exchange") as declare_exchange:
            with TestClient(app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        declare_exchange.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
