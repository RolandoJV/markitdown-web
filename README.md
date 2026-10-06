# markitdown-web

Unofficial **web UI** for [MarkItDown](https://github.com/microsoft/markitdown): upload
several files at once, preview the converted Markdown and download the results
individually or as a single ZIP archive.

> **Attribution / Atribución**
>
> The conversion engine is **MarkItDown**, created by **Adam Fourney** and
> **Microsoft Corporation** and released under the
> [MIT License](https://github.com/microsoft/markitdown/blob/main/LICENSE).
> **All credit for the library and the conversion achievement belongs to them.**
>
> This repository contributes **one thing only: a web interface**, so MarkItDown can be
> used from a browser instead of the command line (multi-file upload, preview, ZIP
> download). It consumes the public `markitdown` package from PyPI, does not modify the
> upstream library and redistributes none of its source code.
>
> El motor de conversión es **MarkItDown**, creado por **Adam Fourney** y **Microsoft
> Corporation** (licencia MIT): **todo el mérito es suyo**. Este repositorio solo aporta
> la interfaz web para usarlo desde el navegador en lugar de la consola. No modifica la
> librería original ni redistribuye su código fuente.

## Features

- Multi-file upload (drag & drop or file picker).
- Per-file status, error messages and Markdown preview.
- Individual `.md` download, plus a batch ZIP with `manifest.json` and `conversion-errors.txt`.
- Spanish/English UI (auto-detected, toggleable, persisted).
- Conservative defaults: loopback-only binding, request size limits, output truncation,
  security headers and no permissive CORS.

## Installation

Requires Python 3.10–3.14.

```bash
git clone https://github.com/RolandoJV/markitdown-web.git
cd markitdown-web
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[test]"
```

The upstream library (`markitdown[all]`, by Adam Fourney / Microsoft) is pulled from
PyPI automatically as a dependency.

## Usage

```bash
markitdown-web                 # http://127.0.0.1:8000
markitdown-web --port 9000
markitdown-web --host 0.0.0.0  # prints a loud security warning first
```

## HTTP API

| Method | Path           | Description                                                        |
| ------ | -------------- | ------------------------------------------------------------------ |
| `GET`  | `/`            | Web UI                                                             |
| `GET`  | `/api/health`  | Version and active limits                                          |
| `POST` | `/api/convert` | `multipart/form-data` field `files` (repeatable) → JSON results    |
| `POST` | `/api/zip`     | `{"files":[{"filename","markdown"}]}` → `application/zip`          |

`/api/convert` returns `results[]` with `filename`, `output_name`, `ok`, `markdown`,
`title`, `error`, `error_type`, `truncated`, `size_bytes` and `elapsed_ms`, plus a
`summary` counter.

## Configuration (environment variables)

| Variable                          | Default    | Meaning                                   |
| --------------------------------- | ---------- | ----------------------------------------- |
| `MARKITDOWN_WEB_MAX_FILES`        | `20`       | Files per request                         |
| `MARKITDOWN_WEB_MAX_FILE_BYTES`   | `52428800` | 50 MB per file                            |
| `MARKITDOWN_WEB_MAX_TOTAL_BYTES`  | `209715200`| 200 MB per request                        |
| `MARKITDOWN_WEB_MAX_MARKDOWN_CHARS`| `2000000` | Output cap per file (guards zip bombs)    |
| `MARKITDOWN_WEB_ENABLE_PLUGINS`   | `false`    | Enable 3rd-party MarkItDown plugins       |
| `MARKITDOWN_WEB_LOCAL_ONLY`       | `true`     | Reject non-loopback `Host` headers        |
| `MARKITDOWN_WEB_API_DOCS`         | `true`     | Expose `/api/docs`                        |

## Security notes

- The server binds to `127.0.0.1` by default and refuses requests whose `Host` header is
  not loopback (DNS-rebinding mitigation). Binding to a public interface requires an
  explicit `--host` and prints a warning: there is **no authentication**.
- Files are only ever converted through `convert_stream()` on in-memory uploads, so
  clients cannot ask the server to read arbitrary paths or fetch arbitrary URLs.
- Uploads are read in chunks and rejected as soon as a limit is exceeded; converted
  output is truncated past `MARKITDOWN_WEB_MAX_MARKDOWN_CHARS`.
- Conversions run in a thread pool and are serialized behind a lock because the upstream
  library makes no thread-safety guarantees.

## Tests

```bash
pytest
```

## License

MIT — the same license as MarkItDown.

- **This repository (the web front-end):** MIT, © markitdown-web contributors.
- **MarkItDown (the conversion engine):** MIT, © Adam Fourney and Microsoft Corporation.
  See the [upstream LICENSE](https://github.com/microsoft/markitdown/blob/main/LICENSE).
