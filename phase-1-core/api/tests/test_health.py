import socket

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_ok() -> None:
    """Healthz ok."""
    client = TestClient(create_app())
    assert client.get("/healthz").json() == {"status": "ok"}


class _Down:
    """Stands in for Postgres and Redis when both are unreachable."""

    def connect(self) -> None:
        """Fail like a database that is down."""
        raise OSError("down")

    async def ping(self) -> None:
        """Fail like Redis that is down."""
        raise OSError("down")


def test_readyz_503_when_dependencies_down() -> None:
    """Readyz 503 when dependencies down."""
    app = create_app()
    app.state.db = _Down()
    app.state.redis = _Down()
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_unexpected_error_is_generic_500_and_secret_stays_out_of_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected error is generic 500 and secret stays out of log."""
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        """A route that crashes with a secret in the error."""
        raise RuntimeError("password=hunter2")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "RuntimeError" in caplog.text
    assert "hunter2" not in caplog.text
    assert "hunter2" not in response.text


def test_api_docs_hidden_by_default() -> None:
    """Api docs hidden by default."""
    client = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def _port_open(port: int) -> bool:
    """Whether a local port is open."""
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@pytest.mark.skipif(
    not (_port_open(15432) and _port_open(16379)),
    reason="tunnels not open: run make db-tunnel and make redis-tunnel",
)
def test_readyz_ok_against_beta() -> None:
    """Readyz ok against beta."""
    with TestClient(create_app()) as client:
        response = client.get("/readyz")
    assert response.status_code == 200, response.json()
