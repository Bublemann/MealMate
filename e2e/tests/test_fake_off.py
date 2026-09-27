"""The Open Food Facts stand-in answers like the real API v3."""

import subprocess
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

from fake_off.app import app
from support import fake_off as fake_off_support
from support.fake_off import HOST_GATEWAY, bridge_gateway, serve_fake_off

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


@pytest.mark.parametrize(
    ("version", "suffix"), [("v3", ".json"), ("v3", ""), ("v3.4", ""), ("v3.4", ".json")]
)
def test_known_barcode_returns_the_fixture(
    fake_off: httpx.Client, version: str, suffix: str
) -> None:
    response = fake_off.get(f"/api/{version}/product/{KNOWN}{suffix}", params={"fields": "code"})

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


def test_unknown_versions_are_not_served(fake_off: httpx.Client) -> None:
    assert fake_off.get(f"/api/v2/product/{KNOWN}").status_code == 404


def test_the_slow_barcode_answers_late(
    fake_off: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_OFF_SLOW_SECONDS", "0.3")
    started = time.monotonic()

    response = fake_off.get("/api/v3.4/product/2000000000053")

    assert response.status_code == 200
    assert time.monotonic() - started >= 0.3
    assert response.json()["product"]["product_name_de"] == "Rote Linsen"


def test_the_suite_serves_it_on_the_docker_bridge_only() -> None:
    """Not on all interfaces: only the app container, through the bridge, should reach it."""
    gateway = bridge_gateway()
    if gateway is None:
        pytest.skip("this host has no Docker bridge address; the fallback is all interfaces")
    with serve_fake_off() as served, httpx.Client(trust_env=False, timeout=5) as client:
        assert served.host_address == gateway
        path = f"/api/v3/product/{KNOWN}"
        assert client.get(f"http://{gateway}:{served.port}{path}").status_code == 200
        with pytest.raises(httpx.ConnectError):
            client.get(f"http://127.0.0.1:{served.port}{path}")


@pytest.mark.parametrize(
    "answer",
    [
        FileNotFoundError("docker"),
        subprocess.CompletedProcess([], 0, stdout="null"),
        subprocess.CompletedProcess([], 0, stdout="[]"),
        subprocess.CompletedProcess([], 0, stdout='[{"Subnet": "172.17.0.0/16"}]'),
        subprocess.CompletedProcess([], 0, stdout='[{"Gateway": "fd00::1"}]'),
        # A gateway that is no address of this host (Docker Desktop, rootless Docker).
        subprocess.CompletedProcess([], 0, stdout='[{"Gateway": "192.0.2.1"}]'),
    ],
)
def test_without_a_bridge_address_it_falls_back_to_host_gateway(
    monkeypatch: pytest.MonkeyPatch, answer: Exception | subprocess.CompletedProcess[str]
) -> None:
    def docker(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(fake_off_support.subprocess, "run", docker)

    assert bridge_gateway() is None
    with serve_fake_off() as served:
        assert served.host_address == HOST_GATEWAY
