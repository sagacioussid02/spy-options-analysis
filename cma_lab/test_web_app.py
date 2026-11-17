"""Regression tests for issue #5: the local approval UI's state-changing
POST endpoints must require the UI bearer token and reject cross-origin
requests, while read-only GETs stay open.

advisor / lab / risk_gate are stubbed in sys.modules just long enough to
import web.app — advisor's real module-level setup (journal, sessions) is
not what is under test — and sys.modules is restored afterwards so a
full-suite discover run is not poisoned by the stubs.

Run from the cma_lab/ dir:  ../.venv/bin/python -m unittest test_web_app
"""
import os
import sys
import types
import unittest

os.environ["SPY_WEB_TOKEN"] = "test-token-123"
TOKEN = os.environ["SPY_WEB_TOKEN"]

advisor = types.ModuleType("advisor")
advisor.LIVE_EXECUTION = False
advisor.HANDLERS = {}
advisor.deploy_advisor = lambda: "agent"
advisor.execute_approved = lambda e: "executed"


class _Journal:
    def pending_proposals(self):
        return []

    def get(self, eid):
        return None

    def reject(self, eid, note=""):
        pass

    def approve(self, eid, note=""):
        pass

    def _update(self, eid, **changes):
        pass

    def recent(self, n):
        return []


advisor.J = _Journal()

lab = types.ModuleType("lab")
lab.client = lambda: None
lab.ensure_robinhood_credential = lambda vault_id: None
lab.get_or_create_environment = lambda: "env"
lab.get_or_create_vault = lambda: "vault"
lab.lab_env = lambda key, default=None: os.environ.get(key, default)

risk_gate = types.ModuleType("risk_gate")


class _RiskConfig:
    max_quantity = 5
    max_notional_per_order = 1500.0
    kill_switch = False
    equity_only = True


risk_gate.load_risk_config = lambda: _RiskConfig()

_STUBS = {"advisor": advisor, "lab": lab, "risk_gate": risk_gate}
_saved = {name: sys.modules.get(name) for name in _STUBS}
sys.modules.update(_STUBS)
try:
    import web.app as web_app
finally:
    for name, prev in _saved.items():
        if prev is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prev

from fastapi.testclient import TestClient  # noqa: E402

AUTH = {"Authorization": f"Bearer {TOKEN}"}
SAME_ORIGIN = {"Origin": "http://testserver"}  # TestClient's host header
CROSS_ORIGIN = {"Origin": "https://evil.example.com"}


class WebAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(web_app.app, raise_server_exceptions=False)

    def test_reject_without_token_is_401(self):
        r = self.client.post("/api/reject", json={"id": "x"})
        self.assertEqual(r.status_code, 401)

    def test_reject_with_wrong_token_is_401(self):
        r = self.client.post("/api/reject", json={"id": "x"},
                             headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 401)

    def test_chat_without_token_is_401(self):
        r = self.client.post("/api/chat", json={"message": "hi"})
        self.assertEqual(r.status_code, 401)

    def test_reject_with_token_same_origin_is_200(self):
        r = self.client.post("/api/reject", json={"id": "x"},
                             headers={**AUTH, **SAME_ORIGIN})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})

    def test_reject_with_token_no_origin_is_200(self):
        # Non-browser clients send no Origin; the token is their credential.
        r = self.client.post("/api/reject", json={"id": "x"}, headers=AUTH)
        self.assertEqual(r.status_code, 200)

    def test_post_with_token_cross_origin_is_403(self):
        r = self.client.post("/api/reject", json={"id": "x"},
                             headers={**AUTH, **CROSS_ORIGIN})
        self.assertEqual(r.status_code, 403)

    def test_get_endpoints_stay_open(self):
        r = self.client.get("/api/risk")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["max_shares"], 5)


if __name__ == "__main__":
    unittest.main()
