# SPDX-FileCopyrightText: markitdown-web is an unofficial companion package.
# The underlying MarkItDown library is (c) Microsoft Corporation, MIT License.

from __future__ import annotations

import io
import json
import logging
import ntpath
import posixpath
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from markitdown import (
    FileConversionException,
    MarkItDown,
    MarkItDownException,
    MissingDependencyException,
    StreamInfo,
    UnsupportedFormatException,
)

from .config import Settings

logger = logging.getLogger(__name__)

_TRUNCATION_NOTICE = (
    "\n\n<!-- markitdown-web: output truncated at {limit} characters -->\n"
)

ERROR_MISSING_DEPENDENCY = "missing_dependency"
ERROR_UNSUPPORTED = "unsupported_format"
ERROR_CONVERSION = "conversion_failed"
ERROR_TOO_LARGE = "too_large"
ERROR_EMPTY = "empty_file"
ERROR_INTERNAL = "internal_error"

_RESERVED_ZIP_NAMES = {"manifest.json", "conversion-errors.txt"}


@dataclass(frozen=True, kw_only=True)
class ConversionOutcome:
    """Result of converting a single uploaded file."""

    filename: str
    output_name: str
    ok: bool
    size_bytes: int
    elapsed_ms: int
    markdown: str = ""
    title: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    truncated: bool = False

    def to_public_dict(self) -> dict:
        """Serialize for the JSON API (keeps the markdown payload)."""
        return {
            "filename": self.filename,
            "output_name": self.output_name,
            "ok": self.ok,
            "size_bytes": self.size_bytes,
            "elapsed_ms": self.elapsed_ms,
            "markdown": self.markdown,
            "title": self.title,
            "error": self.error,
            "error_type": self.error_type,
            "truncated": self.truncated,
        }

    def to_manifest_dict(self) -> dict:
        """Serialize without the markdown payload (used inside the ZIP)."""
        data = self.to_public_dict()
        data.pop("markdown")
        data["markdown_chars"] = len(self.markdown)
        return data


class ConversionService:
    """Thin wrapper around MarkItDown that is safe to call from the web layer.

    A single MarkItDown instance is reused (constructing one loads the magika
    model) and every conversion is serialized behind a lock, because the
    upstream library makes no thread-safety guarantees.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()
        self._lock = threading.Lock()
        self._converter: Optional[MarkItDown] = None

    @property
    def converter(self) -> MarkItDown:
        converter = self._converter
        if converter is None:
            converter = MarkItDown(enable_plugins=self.settings.enable_plugins)
            self._converter = converter
        return converter

    def convert_upload(
        self,
        *,
        filename: str,
        content_type: Optional[str],
        data: bytes,
        used_names: Optional[set] = None,
    ) -> ConversionOutcome:
        display_name = sanitize_filename(filename) or "upload.bin"
        size_bytes = len(data)
        started = time.perf_counter()
        used = used_names if used_names is not None else set()

        def outcome(ok: bool, output_name: str, **kwargs) -> ConversionOutcome:
            return ConversionOutcome(
                filename=display_name,
                output_name=output_name,
                ok=ok,
                size_bytes=size_bytes,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                **kwargs,
            )

        pending_name = pending_output_name(display_name)

        if size_bytes == 0:
            return outcome(
                False,
                pending_name,
                error="The uploaded file is empty.",
                error_type=ERROR_EMPTY,
            )

        if size_bytes > self.settings.max_file_bytes:
            return outcome(
                False,
                pending_name,
                error=f"File exceeds the {self.settings.max_file_bytes} byte limit.",
                error_type=ERROR_TOO_LARGE,
            )

        stream_info = StreamInfo(
            filename=display_name,
            extension=_extension_of(display_name),
            mimetype=_normalize_mimetype(content_type),
        )

        try:
            with self._lock:
                result = self.converter.convert_stream(
                    io.BytesIO(data), stream_info=stream_info
                )
        except MissingDependencyException as exc:
            return outcome(
                False,
                pending_name,
                error=str(exc),
                error_type=ERROR_MISSING_DEPENDENCY,
            )
        except UnsupportedFormatException:
            return outcome(
                False,
                pending_name,
                error="No converter recognized this file. Check the format or the "
                "file extension.",
                error_type=ERROR_UNSUPPORTED,
            )
        except (FileConversionException, MarkItDownException) as exc:
            return outcome(
                False,
                pending_name,
                error=_public_message(exc),
                error_type=ERROR_CONVERSION,
            )
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            return outcome(
                False,
                pending_name,
                error=_public_message(exc),
                error_type=ERROR_CONVERSION,
            )
        except Exception:  # noqa: BLE001 - boundary between library and HTTP layer
            logger.exception("Unexpected failure while converting %s", display_name)
            return outcome(
                False,
                pending_name,
                error="Unexpected server error while converting this file.",
                error_type=ERROR_INTERNAL,
            )

        markdown = result.markdown or ""
        truncated = False
        limit = self.settings.max_markdown_chars
        if len(markdown) > limit:
            markdown = markdown[:limit] + _TRUNCATION_NOTICE.format(limit=limit)
            truncated = True

        return outcome(
            True,
            reserve_output_name(display_name, used),
            markdown=markdown,
            title=result.title,
            truncated=truncated,
        )

    def convert_all(self, uploads: Sequence[dict]) -> List[ConversionOutcome]:
        """Convert a batch of uploads, keeping successful output names unique."""
        used_names: set = set()
        outcomes: List[ConversionOutcome] = []
        for upload in uploads:
            outcomes.append(
                self.convert_upload(
                    filename=upload["filename"],
                    content_type=upload.get("content_type"),
                    data=upload["data"],
                    used_names=used_names,
                )
            )
        return outcomes


def build_zip(outcomes: Iterable[ConversionOutcome]) -> bytes:
    """Bundle successful conversions into a ZIP with a manifest and error log."""
    buffer = io.BytesIO()
    used: set = set(_RESERVED_ZIP_NAMES)
    manifest = []
    errors: List[str] = []

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for outcome in outcomes:
            manifest.append(outcome.to_manifest_dict())
            if not outcome.ok:
                errors.append(f"{outcome.filename}: {outcome.error}")
                continue
            name = reserve_output_name(outcome.output_name, used)
            archive.writestr(name, outcome.markdown.encode("utf-8"))

        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        if errors:
            archive.writestr("conversion-errors.txt", "\n".join(errors).encode("utf-8"))

    return buffer.getvalue()


def sanitize_filename(raw: Optional[str]) -> str:
    """Strip directories and control characters from a client-provided name."""
    if not raw:
        return ""
    name = str(raw).replace("\x00", "")
    name = ntpath.basename(name)
    name = posixpath.basename(name)
    name = "".join(ch for ch in name if ch.isprintable())
    return name.strip().strip(".")[:255]


def pending_output_name(filename: str) -> str:
    """Default `*.md` name for a file, without reserving it in a batch."""
    stem, _ = posixpath.splitext(sanitize_filename(filename) or "output")
    return f"{stem or 'output'}.md"


def reserve_output_name(filename: str, used: set) -> str:
    """Return a collision-free `*.md` name and reserve it in `used`."""
    candidate = pending_output_name(filename)
    stem = candidate[: -len(".md")]
    counter = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{counter}.md"
        counter += 1
    used.add(candidate.lower())
    return candidate


def _extension_of(filename: str) -> Optional[str]:
    _, ext = posixpath.splitext(filename)
    return ext.lower() if ext else None


def _normalize_mimetype(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    value = content_type.split(";", 1)[0].strip().lower()
    if value in ("", "application/octet-stream", "binary/octet-stream"):
        return None
    if value.count("/") != 1:
        return None
    return value


def _public_message(exc: BaseException) -> str:
    """Convert an exception into a short, non-leaky message for the client."""
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return message.splitlines()[0].strip()[:500]
