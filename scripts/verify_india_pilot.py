"""Verify workbook export, dashboard rendering and the five-role contract."""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from scripts.india_agents import ROOT, run


def verify_data(payload):
    dashboard = payload["dashboard"]
    tenders = payload["tenders"]
    prices = payload["price_intelligence"]
    assert dashboard["lookback_months"] == 24
    assert len(tenders) == dashboard["tender_count"] > 0
    assert len(prices) == dashboard["price_row_count"]
    assert all(row["tender_date"] >= dashboard["archive_start"] for row in tenders)
    tender_ids = {str(row["tender_id"]).strip() for row in tenders}
    assert all(str(row["tender_id"]).strip() in tender_ids for row in prices)


def verify_agents(payload):
    calls = []

    def fake(model, task, data):
        calls.append((model, task, tuple(data["worker_reports"])))
        evidence = data["evidence"]
        findings = [{"observation": "test", "next_action": "test", "evidence": [evidence[0]["id"]]}] if evidence else []
        return {"findings": findings, "gaps": []}

    report = run(payload, request=fake)
    workers = ("country", "operators", "registration", "tenders")
    assert tuple(report["reports"]) == (*workers, "supervisor")
    assert len(calls) == 5
    assert all(call[0] == report["models"]["workers"] for call in calls[:4])
    assert calls[-1][0] == report["models"]["supervisor"]
    assert calls[-1][2] == workers


def verify_browser(payload):
    from playwright.sync_api import sync_playwright

    handler = partial(SimpleHTTPRequestHandler, directory=ROOT / "docs")
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                page.get_by_text("veri yüklendi", exact=True).wait_for()
                checks = [
                    ("Tender Register", "tblTender", "tenders"),
                    ("Price Intelligence", "tblPrice", "price_intelligence"),
                ]
                for label, table, key in checks:
                    page.get_by_role("button", name=label, exact=True).click()
                    assert page.locator(f"#{table} tbody tr td:first-child:not([colspan])").count() == len(payload[key])
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    payload = json.loads((ROOT / "docs/data.json").read_text(encoding="utf-8"))
    verify_data(payload)
    verify_agents(payload)
    verify_browser(payload)
    print("Workbook, dashboard and five-role orchestration verified.")
