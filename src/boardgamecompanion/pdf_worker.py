from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import pypdf


class WorkerLimitError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _PypdfLogCollector(logging.Handler):
    def __init__(self, *, limit: int = 100) -> None:
        super().__init__(level=logging.WARNING)
        self.limit = limit
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if len(self.messages) >= self.limit:
            return
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self.messages.append(str(message)[:1000])


def _apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:
        return
    if memory_mb > 0:
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if cpu_seconds > 0:
        soft = max(1, cpu_seconds)
        hard = soft + 2
        resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))


def _page_payload(
    *,
    page_index: int,
    text: str,
    status: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "page_index": page_index,
        "page_number": page_index + 1,
        "text": text,
        "text_sha256": digest,
        "char_count": len(text),
        "extraction_status": status,
        "diagnostics": diagnostics,
    }


def parse_pdf(
    path: Path,
    *,
    max_pages: int,
    max_chars_per_page: int,
    max_total_chars: int,
) -> dict[str, Any]:
    collector = _PypdfLogCollector()
    logger = logging.getLogger("pypdf")
    logger.addHandler(collector)
    old_level = logger.level
    logger.setLevel(logging.WARNING)

    caught: list[warnings.WarningMessage] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            reader = pypdf.PdfReader(str(path), strict=False)
            if reader.is_encrypted:
                try:
                    decrypted = reader.decrypt("")
                except Exception as exc:
                    raise WorkerLimitError(
                        "encrypted_pdf",
                        "PDF is encrypted and cannot be opened without a password",
                    ) from exc
                if not decrypted:
                    raise WorkerLimitError(
                        "encrypted_pdf",
                        "PDF is encrypted and cannot be opened without a password",
                    )

            page_count = len(reader.pages)
            if page_count > max_pages:
                raise WorkerLimitError(
                    "page_limit",
                    f"PDF has {page_count} pages; configured limit is {max_pages}",
                )

            pages: list[dict[str, Any]] = []
            total_chars = 0
            text_pages = 0
            empty_pages = 0
            error_pages = 0

            for page_index in range(page_count):
                diagnostics: dict[str, Any] = {"extraction_mode": "layout"}
                try:
                    page = reader.pages[page_index]
                    extracted = page.extract_text(extraction_mode="layout")
                    text = extracted if isinstance(extracted, str) else ""
                    if len(text) > max_chars_per_page:
                        raise WorkerLimitError(
                            "page_text_limit",
                            (
                                f"Page {page_index + 1} extracted {len(text)} characters; "
                                f"configured limit is {max_chars_per_page}"
                            ),
                        )
                    total_chars += len(text)
                    if total_chars > max_total_chars:
                        raise WorkerLimitError(
                            "document_text_limit",
                            (
                                f"Document extracted more than {max_total_chars} "
                                "characters"
                            ),
                        )
                    if text.strip():
                        status = "text"
                        text_pages += 1
                    else:
                        status = "empty"
                        empty_pages += 1
                    pages.append(
                        _page_payload(
                            page_index=page_index,
                            text=text,
                            status=status,
                            diagnostics=diagnostics,
                        )
                    )
                except WorkerLimitError:
                    raise
                except Exception as exc:
                    error_pages += 1
                    pages.append(
                        _page_payload(
                            page_index=page_index,
                            text="",
                            status="error",
                            diagnostics={
                                "extraction_mode": "layout",
                                "error_type": type(exc).__name__,
                                "error_message": str(exc)[:1000],
                            },
                        )
                    )

            warning_messages = [
                str(item.message)[:1000] for item in caught[:100]
            ]
            warning_messages.extend(collector.messages)
            warning_messages = warning_messages[:100]

            return {
                "ok": True,
                "parser_name": "pypdf",
                "parser_version": pypdf.__version__,
                "page_count": page_count,
                "text_page_count": text_pages,
                "empty_page_count": empty_pages,
                "error_page_count": error_pages,
                "total_text_chars": total_chars,
                "warning_count": len(warning_messages) + error_pages,
                "diagnostics": {
                    "encrypted": bool(reader.is_encrypted),
                    "extraction_mode": "layout",
                    "warnings": warning_messages,
                    "page_errors": error_pages,
                },
                "pages": pages,
            }
    finally:
        logger.removeHandler(collector)
        logger.setLevel(old_level)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--max-chars-per-page", type=int, required=True)
    parser.add_argument("--max-total-chars", type=int, required=True)
    parser.add_argument("--memory-mb", type=int, required=True)
    parser.add_argument("--cpu-seconds", type=int, required=True)
    args = parser.parse_args()

    try:
        _apply_limits(args.memory_mb, args.cpu_seconds)
        payload = parse_pdf(
            args.path,
            max_pages=args.max_pages,
            max_chars_per_page=args.max_chars_per_page,
            max_total_chars=args.max_total_chars,
        )
    except WorkerLimitError as exc:
        payload = {
            "ok": False,
            "error_code": exc.code,
            "error_message": str(exc)[:2000],
        }
    except MemoryError:
        payload = {
            "ok": False,
            "error_code": "memory_limit",
            "error_message": "PDF parser exceeded its memory limit",
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error_code": "parse_failed",
            "error_message": f"{type(exc).__name__}: {exc}"[:2000],
        }

    sys.stdout.write(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
