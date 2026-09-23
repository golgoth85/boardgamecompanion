from __future__ import annotations

import hashlib
import socket
import ssl
from pathlib import Path

import pytest

from boardgamecompanion.rulebook_fetch import (
    PinnedHTTPTransport,
    RulebookFetcher,
    RulebookFetchFailureCode,
    RulebookFetchPolicy,
    _atomic_noreplace_rename,
    _open_numeric_socket,
    _wrap_tls_socket,
)
from boardgamecompanion.rulebooks import RulebookCandidate, RulebookSource

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PUBLIC_V4 = "8.8.8.8"
PUBLIC_V4_ALT = "1.1.1.1"
PUBLIC_V6 = "2606:4700:4700::1111"


class FakeResponse:
    def __init__(
        self,
        *,
        status=200,
        body=b"",
        headers=None,
        reason=None,
        fail_after=None,
    ):
        self.status = status
        self.reason = reason
        self.body = body
        self.headers = {
            str(key).lower(): str(value)
            for key, value in (headers or {}).items()
        }
        self.fail_after = fail_after
        self.position = 0
        self.closed = False
        self.read_calls = 0

    def read(self, amount):
        self.read_calls += 1
        if self.fail_after is not None and self.position >= self.fail_after:
            raise OSError("simulated stream failure")
        if self.position >= len(self.body):
            return b""
        end = min(self.position + amount, len(self.body))
        if self.fail_after is not None:
            end = min(end, self.fail_after)
        chunk = self.body[self.position:end]
        self.position = end
        return chunk

    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self, routes):
        self.routes = {
            url: list(responses)
            for url, responses in routes.items()
        }
        self.requests = []

    def request(
        self,
        target,
        request_target,
        headers,
        *,
        connect_timeout,
        read_timeout,
    ):
        self.requests.append(
            {
                "target": target,
                "request_target": request_target,
                "headers": dict(headers),
                "connect_timeout": connect_timeout,
                "read_timeout": read_timeout,
            }
        )
        queue = self.routes.get(target.url)
        if not queue:
            raise AssertionError(f"No fake response registered for {target.url}")
        response = queue.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeResolver:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def resolve(self, hostname, port):
        self.calls.append((hostname, port))
        answer = self.answers[hostname]
        if callable(answer):
            answer = answer()
        if isinstance(answer, BaseException):
            raise answer
        return tuple(answer)


def candidate(url="https://rules.example/manual.pdf"):
    return RulebookCandidate(
        provider="test-provider",
        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
        url=url,
        language="it",
        official=True,
        bgg_id=123,
        game_title="Example Game",
        metadata={"source_id": "manual-123"},
    )


def pdf_response(
    body=PDF,
    *,
    content_type="application/pdf",
    content_length=True,
    extra_headers=None,
):
    headers = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    if content_length is True:
        headers["Content-Length"] = str(len(body))
    elif isinstance(content_length, str):
        headers["Content-Length"] = content_length
    if extra_headers:
        headers.update(extra_headers)
    return FakeResponse(status=200, body=body, headers=headers)


def redirect(location, *, status=302):
    return FakeResponse(status=status, headers={"Location": location})


def fetcher(
    tmp_path,
    *,
    resolver,
    transport,
    max_bytes=1024,
    max_redirects=5,
    chunk_size=8,
):
    return RulebookFetcher(
        manuals_dir=tmp_path,
        resolver=resolver,
        transport=transport,
        policy=RulebookFetchPolicy(
            max_bytes=max_bytes,
            max_redirects=max_redirects,
            chunk_size=chunk_size,
            connect_timeout_seconds=1.25,
            read_timeout_seconds=2.5,
        ),
    )


def failure_code(result):
    assert result.failure is not None
    return result.failure.code


def test_public_hostname_is_resolved_and_pinned(tmp_path):
    resolver = FakeResolver({"rules.example": (PUBLIC_V4,)})
    transport = FakeTransport(
        {"https://rules.example/manual.pdf": [pdf_response()]}
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert result.ok
    assert resolver.calls == [("rules.example", 443)]
    assert transport.requests[0]["target"].addresses == (PUBLIC_V4,)


@pytest.mark.parametrize(
    "unsafe",
    [
        "127.0.0.1",
        "10.0.0.8",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "240.0.0.1",
        "192.0.0.8",
        "64:ff9b:1::1",
        "2002::1",
    ],
)
def test_runtime_dns_rejects_non_public_addresses(tmp_path, unsafe):
    resolver = FakeResolver({"rules.example": (unsafe,)})
    transport = FakeTransport({})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.SSRF_BLOCKED
    assert transport.requests == []


def test_runtime_dns_rejects_mixed_public_and_private_answers(tmp_path):
    resolver = FakeResolver(
        {"rules.example": (PUBLIC_V4, PUBLIC_V6, "10.0.0.1")}
    )
    transport = FakeTransport({})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.SSRF_BLOCKED
    assert transport.requests == []


def test_runtime_dns_accepts_multiple_public_a_and_aaaa_answers(tmp_path):
    resolver = FakeResolver(
        {"rules.example": (PUBLIC_V6, PUBLIC_V4_ALT, PUBLIC_V4)}
    )
    transport = FakeTransport(
        {"https://rules.example/manual.pdf": [pdf_response()]}
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert result.ok
    assert set(transport.requests[0]["target"].addresses) == {
        PUBLIC_V4,
        PUBLIC_V4_ALT,
        PUBLIC_V6,
    }


def test_runtime_dns_rejects_ipv4_mapped_ipv6(tmp_path):
    resolver = FakeResolver({"rules.example": ("::ffff:8.8.8.8",)})
    transport = FakeTransport({})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.SSRF_BLOCKED


def test_runtime_dns_rejects_empty_answer(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": ()}),
        transport=FakeTransport({}),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.DNS_EMPTY


def test_runtime_dns_reports_resolution_failure(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver(
            {"rules.example": socket.gaierror("simulated dns failure")}
        ),
        transport=FakeTransport({}),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.DNS_FAILURE


def test_runtime_dns_rejects_invalid_resolver_payload(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": ("not-an-ip",)}),
        transport=FakeTransport({}),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.DNS_INVALID_RESPONSE


def test_dns_rebinding_second_answer_is_never_used_after_validation(tmp_path):
    answers = iter(((PUBLIC_V4,), ("127.0.0.1",)))
    resolver = FakeResolver({"rules.example": lambda: next(answers)})
    transport = FakeTransport(
        {"https://rules.example/manual.pdf": [pdf_response()]}
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate())

    assert result.ok
    assert resolver.calls == [("rules.example", 443)]
    assert transport.requests[0]["target"].addresses == (PUBLIC_V4,)


def test_redirect_to_other_public_host_is_revalidated(tmp_path):
    start = "https://rules.example/manual.pdf"
    final = "https://cdn.example/rules/manual.pdf"
    resolver = FakeResolver(
        {
            "rules.example": (PUBLIC_V4,),
            "cdn.example": (PUBLIC_V4_ALT,),
        }
    )
    transport = FakeTransport(
        {
            start: [redirect(final)],
            final: [
                pdf_response(
                    extra_headers={
                        "ETag": '"abc"',
                        "Last-Modified": "Tue, 01 Jan 2030 00:00:00 GMT",
                    }
                )
            ],
        }
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate(start))

    assert result.ok
    assert result.final_url == final
    assert [(hop.from_url, hop.to_url) for hop in result.redirect_chain] == [
        (start, final)
    ]
    assert resolver.calls == [
        ("rules.example", 443),
        ("cdn.example", 443),
    ]
    assert transport.requests[1]["headers"]["Host"] == "cdn.example"
    assert result.http_metadata["etag"] == '"abc"'


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (
            "https://localhost/manual.pdf",
            RulebookFetchFailureCode.SSRF_BLOCKED,
        ),
        (
            "https://127.0.0.1/manual.pdf",
            RulebookFetchFailureCode.SSRF_BLOCKED,
        ),
        (
            "ftp://public.example/manual.pdf",
            RulebookFetchFailureCode.INVALID_REDIRECT,
        ),
        (
            "https://user:secret@public.example/manual.pdf",
            RulebookFetchFailureCode.INVALID_REDIRECT,
        ),
        (
            "https://[::1",
            RulebookFetchFailureCode.INVALID_REDIRECT,
        ),
    ],
)
def test_redirect_rejects_unsafe_or_malformed_locations(
    tmp_path,
    location,
    expected,
):
    start = "https://rules.example/manual.pdf"
    resolver = FakeResolver({"rules.example": (PUBLIC_V4,)})
    transport = FakeTransport({start: [redirect(location)]})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate(start))

    assert failure_code(result) == expected
    assert len(transport.requests) == 1


def test_redirect_hostname_resolving_private_is_blocked(tmp_path):
    start = "https://rules.example/manual.pdf"
    target = "https://evil.example/manual.pdf"
    resolver = FakeResolver(
        {
            "rules.example": (PUBLIC_V4,),
            "evil.example": ("10.0.0.4",),
        }
    )
    transport = FakeTransport({start: [redirect(target)]})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate(start))

    assert failure_code(result) == RulebookFetchFailureCode.SSRF_BLOCKED
    assert len(transport.requests) == 1


def test_redirect_chain_limit_is_enforced(tmp_path):
    start = "https://rules.example/manual.pdf"
    second = "https://cdn.example/one.pdf"
    third = "https://files.example/two.pdf"
    resolver = FakeResolver(
        {
            "rules.example": (PUBLIC_V4,),
            "cdn.example": (PUBLIC_V4_ALT,),
        }
    )
    transport = FakeTransport(
        {
            start: [redirect(second)],
            second: [redirect(third)],
        }
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
        max_redirects=1,
    ).fetch(candidate(start))

    assert failure_code(result) == RulebookFetchFailureCode.REDIRECT_LIMIT
    assert len(result.redirect_chain) == 1


def test_redirect_loop_is_detected(tmp_path):
    start = "https://rules.example/manual.pdf"
    resolver = FakeResolver({"rules.example": (PUBLIC_V4,)})
    transport = FakeTransport({start: [redirect(start)]})

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate(start))

    assert failure_code(result) == RulebookFetchFailureCode.REDIRECT_LOOP


def test_https_to_http_redirect_is_rejected_by_default(tmp_path):
    start = "https://rules.example/manual.pdf"
    resolver = FakeResolver({"rules.example": (PUBLIC_V4,)})
    transport = FakeTransport(
        {start: [redirect("http://rules.example/manual.pdf")]}
    )

    result = fetcher(
        tmp_path,
        resolver=resolver,
        transport=transport,
    ).fetch(candidate(start))

    assert failure_code(result) == RulebookFetchFailureCode.DOWNGRADE_REDIRECT


def test_content_length_below_limit_succeeds(tmp_path):
    response = pdf_response()
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
        max_bytes=len(PDF) + 1,
    ).fetch(candidate())

    assert result.ok
    assert result.byte_size == len(PDF)


def test_content_length_above_limit_is_rejected_before_streaming(tmp_path):
    response = pdf_response(content_length="9999")
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
        max_bytes=64,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.CONTENT_TOO_LARGE
    assert response.read_calls == 0


def test_missing_content_length_is_bounded_by_streaming_limit(tmp_path):
    response = pdf_response(content_length=False)
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
    ).fetch(candidate())

    assert result.ok
    assert result.byte_size == len(PDF)


def test_chunked_style_body_exceeding_limit_is_rejected_and_cleaned(tmp_path):
    body = PDF + b"x" * 64
    response = pdf_response(
        body,
        content_length=False,
        extra_headers={"Transfer-Encoding": "chunked"},
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
        max_bytes=len(PDF) + 8,
        chunk_size=7,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.CONTENT_TOO_LARGE
    assert list(Path(tmp_path).glob("*.part")) == []


def test_body_can_exceed_limit_despite_false_small_content_length(tmp_path):
    body = PDF + b"x" * 64
    response = pdf_response(body, content_length="10")
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
        max_bytes=len(PDF) + 8,
        chunk_size=9,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.CONTENT_TOO_LARGE


def test_partial_download_is_cleaned_after_stream_failure(tmp_path):
    response = FakeResponse(
        status=200,
        body=PDF + b"x" * 20,
        headers={"Content-Type": "application/pdf"},
        fail_after=8,
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
        chunk_size=8,
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.NETWORK_ERROR
    assert list(Path(tmp_path).glob("*.part")) == []
    assert list(Path(tmp_path).glob("*.pdf")) == []


def test_valid_pdf_is_persisted_atomically_with_hash(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [pdf_response()]}
        ),
    ).fetch(candidate())

    expected_hash = hashlib.sha256(PDF).hexdigest()
    assert result.ok
    assert result.sha256 == expected_hash
    assert result.local_path == str(Path(tmp_path) / f"{expected_hash}.pdf")
    assert Path(result.local_path).read_bytes() == PDF
    assert list(Path(tmp_path).glob("*.part")) == []


def test_pdf_mime_with_non_pdf_body_is_rejected(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {
                "https://rules.example/manual.pdf": [
                    pdf_response(b"not a pdf", content_type="application/pdf")
                ]
            }
        ),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.PDF_MAGIC_MISMATCH
    assert list(Path(tmp_path).glob("*.pdf")) == []


def test_pdf_with_generic_binary_mime_is_allowed(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {
                "https://rules.example/manual.pdf": [
                    pdf_response(
                        content_type="application/octet-stream",
                    )
                ]
            }
        ),
    ).fetch(candidate())

    assert result.ok
    assert result.content_type == "application/octet-stream"


def test_html_error_page_is_rejected_before_body_download(tmp_path):
    response = pdf_response(
        b"<html>error</html>",
        content_type="text/html; charset=utf-8",
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.CONTENT_TYPE_REJECTED
    assert response.read_calls == 0


def test_zero_byte_response_is_rejected(tmp_path):
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {
                "https://rules.example/manual.pdf": [
                    pdf_response(b"")
                ]
            }
        ),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.EMPTY_BODY


def test_compressed_content_is_rejected_to_avoid_decompression_bombs(tmp_path):
    response = pdf_response(
        extra_headers={"Content-Encoding": "gzip"}
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
    ).fetch(candidate())

    assert (
        failure_code(result)
        == RulebookFetchFailureCode.UNSUPPORTED_CONTENT_ENCODING
    )
    assert response.read_calls == 0


def test_content_length_mismatch_is_rejected(tmp_path):
    response = pdf_response(content_length=str(len(PDF) + 1))
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
    ).fetch(candidate())

    assert (
        failure_code(result)
        == RulebookFetchFailureCode.CONTENT_LENGTH_MISMATCH
    )


def test_request_preserves_host_query_timeouts_and_safe_headers(tmp_path):
    url = "https://rules.example:8443/manual.pdf?token=%7e"
    transport = FakeTransport({url: [pdf_response()]})
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=transport,
    ).fetch(candidate(url))

    assert result.ok
    request = transport.requests[0]
    assert request["target"].hostname == "rules.example"
    assert request["target"].addresses == (PUBLIC_V4,)
    assert request["headers"]["Host"] == "rules.example:8443"
    assert request["request_target"] == "/manual.pdf?token=%7e"
    assert request["headers"]["Accept-Encoding"] == "identity"
    assert "Authorization" not in request["headers"]
    assert "Cookie" not in request["headers"]
    assert request["connect_timeout"] == 1.25
    assert request["read_timeout"] == 2.5


def test_default_tls_context_requires_hostname_and_certificate_validation():
    transport = PinnedHTTPTransport()

    assert transport.ssl_context.check_hostname is True
    assert transport.ssl_context.verify_mode == ssl.CERT_REQUIRED


def test_numeric_socket_connects_to_validated_ip_without_hostname_resolution(
    monkeypatch,
):
    calls = []

    class FakeSocket:
        def settimeout(self, value):
            calls.append(("timeout", value))

        def connect(self, endpoint):
            calls.append(("connect", endpoint))

        def close(self):
            calls.append(("close", None))

    def fake_socket(family, kind):
        calls.append(("socket", (family, kind)))
        return FakeSocket()

    monkeypatch.setattr(
        "boardgamecompanion.rulebook_fetch.socket.socket",
        fake_socket,
    )

    sock = _open_numeric_socket(PUBLIC_V4, 443, 3.0)

    assert sock is not None
    assert ("socket", (socket.AF_INET, socket.SOCK_STREAM)) in calls
    assert ("connect", (PUBLIC_V4, 443)) in calls


def test_tls_wrapper_uses_original_hostname_for_sni():
    calls = []

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname):
            calls.append((sock, server_hostname))
            return "wrapped"

    raw = object()
    result = _wrap_tls_socket(raw, FakeContext(), "rules.example")

    assert result == "wrapped"
    assert calls == [(raw, "rules.example")]


def test_provenance_survives_redirect_and_download(tmp_path):
    start = "https://rules.example/manual.pdf"
    final = "https://cdn.example/manual.pdf"
    item = candidate(start)
    transport = FakeTransport(
        {
            start: [redirect(final, status=307)],
            final: [
                pdf_response(
                    content_type="application/pdf",
                    extra_headers={
                        "Content-Disposition": 'attachment; filename="rules.pdf"',
                    },
                )
            ],
        }
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver(
            {
                "rules.example": (PUBLIC_V4,),
                "cdn.example": (PUBLIC_V4_ALT,),
            }
        ),
        transport=transport,
    ).fetch(item)

    assert result.ok
    assert result.candidate is item
    assert result.provider == "test-provider"
    assert result.source_kind == RulebookSource.OFFICIAL_PUBLISHER
    assert result.requested_url == start
    assert result.final_url == final
    assert result.redirect_chain == (
        result.redirect_chain[0],
    )
    assert result.redirect_chain[0].status_code == 307
    assert result.byte_size == len(PDF)
    assert result.sha256 == hashlib.sha256(PDF).hexdigest()
    assert result.content_type == "application/pdf"
    assert "content-disposition" in result.http_metadata


def test_existing_content_addressed_file_is_reused_without_overwrite(tmp_path):
    digest = hashlib.sha256(PDF).hexdigest()
    existing = Path(tmp_path) / f"{digest}.pdf"
    existing.write_bytes(PDF)
    before = existing.stat().st_mtime_ns

    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [pdf_response()]}
        ),
    ).fetch(candidate())

    assert result.ok
    assert existing.read_bytes() == PDF
    assert existing.stat().st_mtime_ns == before


def test_existing_hash_named_file_with_wrong_content_is_not_overwritten(tmp_path):
    digest = hashlib.sha256(PDF).hexdigest()
    existing = Path(tmp_path) / f"{digest}.pdf"
    existing.write_bytes(b"corrupt")
    response = pdf_response()

    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [response]}
        ),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.STORAGE_CONFLICT
    assert existing.read_bytes() == b"corrupt"
    assert list(Path(tmp_path).glob("*.part")) == []


def test_fetcher_rejects_non_candidate_input(tmp_path):
    instance = fetcher(
        tmp_path,
        resolver=FakeResolver({}),
        transport=FakeTransport({}),
    )

    with pytest.raises(TypeError, match="RulebookCandidate"):
        instance.fetch(object())



def test_atomic_noreplace_rename_never_overwrites_existing_destination(tmp_path):
    source = Path(tmp_path) / "source.part"
    destination = Path(tmp_path) / "manual.pdf"
    source.write_bytes(b"new")
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        _atomic_noreplace_rename(source, destination)

    assert source.read_bytes() == b"new"
    assert destination.read_bytes() == b"existing"


def test_partial_file_creation_error_is_reported_as_storage_failure(
    tmp_path,
    monkeypatch,
):
    def fail_named_temporary_file(*args, **kwargs):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(
        "boardgamecompanion.rulebook_fetch.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )
    result = fetcher(
        tmp_path,
        resolver=FakeResolver({"rules.example": (PUBLIC_V4,)}),
        transport=FakeTransport(
            {"https://rules.example/manual.pdf": [pdf_response()]}
        ),
    ).fetch(candidate())

    assert failure_code(result) == RulebookFetchFailureCode.STORAGE_ERROR
    assert list(Path(tmp_path).glob("*.part")) == []
    assert list(Path(tmp_path).glob("*.pdf")) == []