import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from markitdown_web import __version__, create_app
from markitdown_web.config import Settings

TEXT = b"The quick brown fox jumps over the lazy dog.\n"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        max_files=3,
        max_file_bytes=4096,
        max_total_bytes=8192,
        max_markdown_chars=100_000,
    )


@pytest.fixture
def client(settings) -> TestClient:
    # base_url drives the Host header; the app only accepts loopback hosts.
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as test_client:
        yield test_client


def _upload(files):
    return {"files": files}


def test_health_reports_version_and_limits(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == __version__
    assert payload["limits"]["max_files"] == 3
    assert payload["limits"]["max_file_bytes"] == 4096


def test_index_serves_the_web_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "markitdown-web" in response.text
    assert "static/app.js" in response.text


def test_static_assets_are_served(client):
    for path in ("/static/app.js", "/static/i18n.js", "/static/styles.css"):
        assert client.get(path).status_code == 200


def test_security_headers_are_set(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_non_loopback_host_is_rejected(settings):
    with TestClient(
        create_app(settings), base_url="http://evil.example"
    ) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 403


def test_loopback_check_can_be_disabled(settings):
    app = create_app(settings, local_only=False)
    with TestClient(app, base_url="http://evil.example") as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200


def test_convert_multiple_files(client):
    response = client.post(
        "/api/convert",
        files=[
            ("files", ("first.txt", TEXT, "text/plain")),
            ("files", ("second.txt", TEXT, "text/plain")),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {"total": 2, "succeeded": 2, "failed": 0}
    assert [item["output_name"] for item in payload["results"]] == [
        "first.md",
        "second.md",
    ]
    for item in payload["results"]:
        assert item["ok"] is True
        assert "quick brown fox" in item["markdown"]


def test_convert_uses_unique_output_names(client):
    response = client.post(
        "/api/convert",
        files=[
            ("files", ("notes.txt", TEXT, "text/plain")),
            ("files", ("notes.txt", TEXT, "text/plain")),
        ],
    )
    names = [item["output_name"] for item in response.json()["results"]]
    assert names == ["notes.md", "notes_2.md"]


def test_convert_reports_unsupported_file(client):
    response = client.post(
        "/api/convert",
        files=[("files", ("blob.xyz", bytes(range(256)) * 4, None))],
    )
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["ok"] is False
    assert item["error_type"] == "unsupported_format"
    assert item["error"]
    assert response.json()["summary"]["failed"] == 1


def test_convert_rejects_empty_file(client):
    response = client.post(
        "/api/convert", files=[("files", ("empty.txt", b"", "text/plain"))]
    )
    item = response.json()["results"][0]
    assert item["ok"] is False
    assert item["error_type"] == "empty_file"


def test_convert_rejects_too_many_files(client):
    response = client.post(
        "/api/convert",
        files=[("files", (f"f{i}.txt", TEXT, "text/plain")) for i in range(4)],
    )
    assert response.status_code == 413


def test_convert_rejects_oversized_file(client):
    response = client.post(
        "/api/convert", files=[("files", ("big.txt", b"x" * 5000, "text/plain"))]
    )
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]


def test_convert_rejects_oversized_batch(client):
    files = [("files", (f"f{i}.txt", b"y" * 4000, "text/plain")) for i in range(3)]
    response = client.post("/api/convert", files=files)
    assert response.status_code == 413


def test_convert_requires_at_least_one_file(client):
    response = client.post("/api/convert", files=[])
    assert response.status_code == 422


def test_zip_endpoint_returns_archive(client):
    response = client.post(
        "/api/zip",
        json={
            "files": [
                {"filename": "one.md", "markdown": "# one"},
                {"filename": "two.md", "markdown": "# two"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"one.md", "two.md", "manifest.json"} <= names
        assert archive.read("one.md").decode("utf-8") == "# one"
        manifest = json.loads(archive.read("manifest.json"))
        assert [entry["filename"] for entry in manifest] == ["one.md", "two.md"]


def test_zip_endpoint_truncates_overlong_markdown(settings):
    small = Settings(
        max_files=settings.max_files,
        max_file_bytes=settings.max_file_bytes,
        max_total_bytes=settings.max_total_bytes,
        max_markdown_chars=10,
    )
    app = create_app(small, local_only=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        response = test_client.post(
            "/api/zip",
            json={"files": [{"filename": "big.md", "markdown": "x" * 500}]},
        )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        content = archive.read("big.md").decode("utf-8")
    assert content.startswith("x" * 10)
    assert "truncated" in content


def test_zip_endpoint_rejects_oversized_payload(client):
    # Budget is max_markdown_chars * max_files = 100_000 * 3.
    response = client.post(
        "/api/zip",
        json={"files": [{"filename": "big.md", "markdown": "x" * 400_000}]},
    )
    assert response.status_code == 413


def test_zip_endpoint_validates_shape(client):
    assert (
        client.post("/api/zip", json={"files": [{"filename": ""}]}).status_code == 422
    )
    assert client.post("/api/zip", json={"nope": []}).status_code == 422
