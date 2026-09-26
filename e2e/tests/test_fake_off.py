"""The Open Food Facts stand-in answers like the real API v3."""

import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

from fake_off.app import app

KNOWN = "2000000000015"


@pytest.fixture(scope="module")
def fake_off() -> Iterator[httpx.Client]:
    """The stand-in served over HTTP on a free loopback port, as the app would reach it."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the fake Open Food Facts server did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.parametrize("suffix", [".json", ""])
def test_known_barcode_returns_the_fixture(fake_off: httpx.Client, suffix: str) -> None:
    response = fake_off.get(f"/api/v3/product/{KNOWN}{suffix}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["result"]["id"] == "product_found"
    assert body["product"]["code"] == KNOWN


@pytest.mark.parametrize("barcode", ["4006381333931", "..", "not-a-barcode"])
def test_other_barcodes_return_the_not_found_envelope(fake_off: httpx.Client, barcode: str) -> None:
    response = fake_off.get(f"/api/v3/product/{barcode}.json")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "failure"
    assert body["result"]["id"] == "product_not_found"
    assert body["errors"][0]["field"] == {"id": "code", "value": barcode}
