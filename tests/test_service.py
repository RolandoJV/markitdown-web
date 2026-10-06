import io
import zipfile

import pytest

from markitdown_web.config import Settings
from markitdown_web.service import (
    ConversionOutcome,
    ConversionService,
    build_zip,
    reserve_output_name,
    sanitize_filename,
)
from markitdown_web.service import _normalize_mimetype


@pytest.fixture
def settings() -> Settings:
    return Settings(
        max_files=5,
        max_file_bytes=1024 * 1024,
        max_total_bytes=4 * 1024 * 1024,
        max_markdown_chars=64,
    )


def test_sanitize_filename_strips_directories_and_controls():
    assert sanitize_filename("C:\\Users\\me\\report.pdf") == "report.pdf"
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("bad\x00name.txt") == "badname.txt"
    assert sanitize_filename("") == ""
    assert sanitize_filename(None) == ""


def test_reserve_output_name_deduplicates():
    used: set = set()
    assert reserve_output_name("notes.txt", used) == "notes.md"
    assert reserve_output_name("notes.txt", used) == "notes_2.md"
    assert reserve_output_name("notes.txt", used) == "notes_3.md"


def test_normalize_mimetype_drops_useless_values():
    assert _normalize_mimetype(None) is None
    assert _normalize_mimetype("application/octet-stream") is None
    assert _normalize_mimetype("text/plain; charset=utf-8") == "text/plain"
    assert _normalize_mimetype("not-a-mimetype") is None


def test_convert_text_file(settings):
    service = ConversionService(settings)
    outcome = service.convert_upload(
        filename="sample.txt",
        content_type="text/plain",
        data=("hello world\n" * 5).encode("utf-8"),
    )
    assert outcome.ok is True
    assert outcome.output_name == "sample.md"
    assert "hello world" in outcome.markdown
    assert outcome.error is None


def test_convert_rejects_empty_file(settings):
    service = ConversionService(settings)
    outcome = service.convert_upload(
        filename="empty.txt", content_type="text/plain", data=b""
    )
    assert outcome.ok is False
    assert outcome.error_type == "empty_file"


def test_convert_rejects_oversized_file(settings):
    service = ConversionService(settings)
    outcome = service.convert_upload(
        filename="big.txt",
        content_type="text/plain",
        data=b"x" * (settings.max_file_bytes + 1),
    )
    assert outcome.ok is False
    assert outcome.error_type == "too_large"


def test_convert_reports_unsupported_format(settings):
    service = ConversionService(settings)
    outcome = service.convert_upload(
        filename="blob.xyz",
        content_type=None,
        data=bytes(range(256)) * 4,
    )
    assert outcome.ok is False
    assert outcome.error_type == "unsupported_format"


def test_convert_truncates_long_output(settings):
    service = ConversionService(settings)
    outcome = service.convert_upload(
        filename="long.txt",
        content_type="text/plain",
        data=(("a" * 40 + "\n") * 100).encode("utf-8"),
    )
    assert outcome.ok is True
    assert outcome.truncated is True
    assert len(outcome.markdown) <= settings.max_markdown_chars + 120
    assert "truncated" in outcome.markdown


def test_unexpected_converter_error_is_reported(settings):
    class ExplodingConverter:
        def convert_stream(self, *args, **kwargs):
            raise RuntimeError("boom")

    service = ConversionService(settings)
    service._converter = ExplodingConverter()
    outcome = service.convert_upload(
        filename="doc.txt", content_type="text/plain", data=b"content"
    )
    assert outcome.ok is False
    assert outcome.error_type == "internal_error"


def test_convert_all_keeps_output_names_unique(settings):
    service = ConversionService(settings)
    outcomes = service.convert_all(
        [
            {"filename": "a.txt", "content_type": "text/plain", "data": b"one"},
            {"filename": "a.txt", "content_type": "text/plain", "data": b"two"},
        ]
    )
    assert [outcome.output_name for outcome in outcomes] == ["a.md", "a_2.md"]


def test_build_zip_contains_markdown_manifest_and_errors(settings):
    outcomes = [
        ConversionOutcome(
            filename="ok.txt",
            output_name="ok.md",
            ok=True,
            size_bytes=3,
            elapsed_ms=1,
            markdown="# hi",
        ),
        ConversionOutcome(
            filename="bad.xyz",
            output_name="bad.md",
            ok=False,
            size_bytes=3,
            elapsed_ms=1,
            error="No converter recognized this file.",
            error_type="unsupported_format",
        ),
    ]
    archive_bytes = build_zip(outcomes)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        assert "ok.md" in names
        assert "manifest.json" in names
        assert "conversion-errors.txt" in names
        assert "bad.md" not in names
        assert archive.read("ok.md").decode("utf-8") == "# hi"
