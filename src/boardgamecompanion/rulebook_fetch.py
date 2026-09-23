from __future__ import annotations

import ctypes
import errno
import hashlib
import http.client
import ipaddress
import os
import queue
import socket
import ssl
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from urllib.parse import quote, urljoin, urlsplit

from boardgamecompanion.network_security import is_disallowed_public_ip
from boardgamecompanion.rulebooks import RulebookCandidate, canonical_http_url

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SAFE_HTTP_METADATA = (
    "etag",
    "last-modified",
    "content-disposition",
    "cache-control",
    "accept-ranges",
)
_DEFAULT_ALLOWED_CONTENT_TYPES = (
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
    "binary/octet-stream",
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class RulebookFetchFailureCode(StrEnum):
    DNS_FAILURE = "dns_failure"
    DNS_EMPTY = "dns_empty"
    DNS_INVALID_RESPONSE = "dns_invalid_response"
    SSRF_BLOCKED = "ssrf_blocked"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_ERROR = "network_error"
    TLS_ERROR = "tls_error"
    HTTP_STATUS = "http_status"
    REDIRECT_LIMIT = "redirect_limit"
    REDIRECT_LOOP = "redirect_loop"
    INVALID_REDIRECT = "invalid_redirect"
    DOWNGRADE_REDIRECT = "downgrade_redirect"
    INVALID_CONTENT_LENGTH = "invalid_content_length"
    CONTENT_TOO_LARGE = "content_too_large"
    CONTENT_LENGTH_MISMATCH = "content_length_mismatch"
    UNSUPPORTED_CONTENT_ENCODING = "unsupported_content_encoding"
    CONTENT_TYPE_REJECTED = "content_type_rejected"
    EMPTY_BODY = "empty_body"
    PDF_MAGIC_MISMATCH = "pdf_magic_mismatch"
    STORAGE_CONFLICT = "storage_conflict"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class RulebookFetchPolicy:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 15.0
    fetch_timeout_seconds: float = 300.0
    max_bytes: int = 32 * 1024 * 1024
    max_redirects: int = 5
    chunk_size: int = 64 * 1024
    allow_https_to_http_redirect: bool = False
    allowed_content_types: tuple[str, ...] = _DEFAULT_ALLOWED_CONTENT_TYPES

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        if self.read_timeout_seconds <= 0:
            raise ValueError("read_timeout_seconds must be positive")
        if self.fetch_timeout_seconds <= 0:
            raise ValueError("fetch_timeout_seconds must be positive")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        normalized = tuple(
            dict.fromkeys(
                value.strip().lower()
                for value in self.allowed_content_types
                if value.strip()
            )
        )
        if not normalized:
            raise ValueError("allowed_content_types must not be empty")
        object.__setattr__(self, "allowed_content_types", normalized)


@dataclass(frozen=True, slots=True)
class ValidatedHTTPSTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    host_header: str
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RedirectHop:
    status_code: int
    from_url: str
    to_url: str


@dataclass(frozen=True, slots=True)
class RulebookFetchFailure:
    code: RulebookFetchFailureCode
    message: str
    url: str
    status_code: int | None = None
    attempted_redirect_url: str | None = None


@dataclass(frozen=True, slots=True)
class RulebookFetchResult:
    candidate: RulebookCandidate
    requested_url: str
    final_url: str | None
    redirect_chain: tuple[RedirectHop, ...] = ()
    status_code: int | None = None
    content_type: str | None = None
    byte_size: int = 0
    sha256: str | None = None
    local_path: str | None = None
    http_metadata: Mapping[str, str] = field(default_factory=dict)
    failure: RulebookFetchFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "http_metadata",
            MappingProxyType(dict(self.http_metadata)),
        )

    @property
    def ok(self) -> bool:
        return self.failure is None and self.sha256 is not None

    @property
    def provider(self) -> str:
        return self.candidate.provider

    @property
    def source_kind(self):
        return self.candidate.source_kind


@runtime_checkable
class AddressResolver(Protocol):
    def resolve(
        self,
        hostname: str,
        port: int,
        *,
        timeout: float,
    ) -> Sequence[str]:
        ...


class SocketAddressResolver:
    # Bound unresolved libc/OS resolver calls globally. A timed-out getaddrinfo()
    # may continue in its daemon worker, but cannot create unbounded worker growth.
    _resolution_slots = threading.BoundedSemaphore(8)

    def resolve(
        self,
        hostname: str,
        port: int,
        *,
        timeout: float,
    ) -> Sequence[str]:
        if timeout <= 0:
            raise TimeoutError("DNS resolution deadline exceeded")
        started = time.monotonic()
        if not self._resolution_slots.acquire(timeout=timeout):
            raise TimeoutError("DNS resolution deadline exceeded")

        result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def run_resolution() -> None:
            try:
                records = socket.getaddrinfo(
                    hostname,
                    port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                )
                result: tuple[bool, object] = (
                    True,
                    tuple(record[4][0] for record in records),
                )
            except OSError as exc:
                result = (False, exc)
            finally:
                self._resolution_slots.release()
            result_queue.put(result)

        worker = threading.Thread(target=run_resolution, daemon=True)
        try:
            worker.start()
        except RuntimeError:
            self._resolution_slots.release()
            raise
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("DNS resolution deadline exceeded")
        try:
            succeeded, value = result_queue.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("DNS resolution deadline exceeded") from exc
        if not succeeded:
            assert isinstance(value, Exception)
            raise value
        assert isinstance(value, tuple)
        return value


@runtime_checkable
class HTTPResponseStream(Protocol):
    status: int
    reason: str | None
    headers: Mapping[str, str]

    def read(self, amount: int) -> bytes:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class HTTPTransport(Protocol):
    def request(
        self,
        target: ValidatedHTTPSTarget,
        request_target: str,
        headers: Mapping[str, str],
        *,
        connect_timeout: float,
        read_timeout: float,
        deadline: float | None = None,
    ) -> HTTPResponseStream:
        ...


def _remaining_timeout(deadline: float | None, phase_limit: float) -> float:
    if deadline is None:
        return phase_limit
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Rulebook fetch deadline exceeded")
    return min(phase_limit, remaining)


def _deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _start_deadline_timer(
    close_callback: Callable[[], None],
    deadline: float | None,
) -> threading.Timer | None:
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Rulebook fetch deadline exceeded")
    timer = threading.Timer(remaining, close_callback)
    timer.daemon = True
    timer.start()
    return timer


def _open_numeric_socket(address: str, port: int, timeout: float):
    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        endpoint = (
            (parsed.compressed, port, 0, 0)
            if parsed.version == 6
            else (parsed.compressed, port)
        )
        sock.connect(endpoint)
        return sock
    except Exception:
        sock.close()
        raise


def _wrap_tls_socket(sock, context: ssl.SSLContext, hostname: str):
    return context.wrap_socket(sock, server_hostname=hostname)


def _atomic_noreplace_rename(source: Path, destination: Path) -> None:
    """Atomically publish source at destination without replacing an existing file."""
    renameat2 = None
    if os.name == "posix":
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
        except OSError:
            renameat2 = None

    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            _AT_FDCWD,
            os.fsencode(source),
            _AT_FDCWD,
            os.fsencode(destination),
            _RENAME_NOREPLACE,
        )
        if result == 0:
            return
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError(error_number, os.strerror(error_number), destination)
        fallback_errors = {
            errno.ENOSYS,
            errno.EINVAL,
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if error_number not in fallback_errors:
            raise OSError(error_number, os.strerror(error_number), destination)

    # Same-directory hard-link publication is atomic and no-replace, and is used
    # only when renameat2(RENAME_NOREPLACE) is unavailable on the runtime/filesystem.
    os.link(source, destination)
    source.unlink()


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        *,
        address: str,
        connect_timeout: float,
        read_timeout: float,
        deadline: float | None,
    ):
        super().__init__(hostname, port=port, timeout=connect_timeout)
        self._validated_address = address
        self._read_timeout = read_timeout
        self._deadline = deadline

    def connect(self) -> None:
        self.timeout = _remaining_timeout(self._deadline, self.timeout)
        self.sock = _open_numeric_socket(
            self._validated_address,
            self.port,
            self.timeout,
        )
        self.sock.settimeout(
            _remaining_timeout(self._deadline, self._read_timeout)
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        *,
        address: str,
        connect_timeout: float,
        read_timeout: float,
        deadline: float | None,
        context: ssl.SSLContext,
    ):
        super().__init__(
            hostname,
            port=port,
            timeout=connect_timeout,
            context=context,
        )
        self._validated_address = address
        self._read_timeout = read_timeout
        self._deadline = deadline

    def connect(self) -> None:
        self.timeout = _remaining_timeout(self._deadline, self.timeout)
        self.sock = _open_numeric_socket(
            self._validated_address,
            self.port,
            self.timeout,
        )
        try:
            self.sock.settimeout(
                _remaining_timeout(self._deadline, self.timeout)
            )
            self.sock = _wrap_tls_socket(
                self.sock,
                self._context,
                self.host,
            )
            self.sock.settimeout(
                _remaining_timeout(self._deadline, self._read_timeout)
            )
        except Exception:
            if self.sock is not None:
                self.sock.close()
            raise


class _LiveHTTPResponse:
    def __init__(
        self,
        connection: http.client.HTTPConnection,
        response: http.client.HTTPResponse,
        *,
        read_timeout: float,
        deadline: float | None,
        deadline_timer: threading.Timer | None,
    ):
        self._connection = connection
        self._response = response
        self._read_timeout = read_timeout
        self._deadline = deadline
        self._deadline_timer = deadline_timer
        self.status = response.status
        self.reason = response.reason
        normalized: dict[str, str] = {}
        for key, value in response.getheaders():
            lower_key = key.lower()
            if lower_key in normalized:
                normalized[lower_key] = f"{normalized[lower_key]}, {value}"
            else:
                normalized[lower_key] = value
        self.headers = MappingProxyType(normalized)

    def read(self, amount: int) -> bytes:
        if self._connection.sock is not None:
            self._connection.sock.settimeout(
                _remaining_timeout(self._deadline, self._read_timeout)
            )
        try:
            data = self._response.read1(amount)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            if _deadline_expired(self._deadline):
                raise TimeoutError("Rulebook fetch deadline exceeded") from exc
            raise
        if _deadline_expired(self._deadline):
            raise TimeoutError("Rulebook fetch deadline exceeded")
        return data

    def close(self) -> None:
        if self._deadline_timer is not None:
            self._deadline_timer.cancel()
        try:
            self._response.close()
        finally:
            self._connection.close()


class PinnedHTTPTransport:
    def __init__(self, *, ssl_context: ssl.SSLContext | None = None):
        context = ssl_context or ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError(
                "TLS context must require certificate verification and hostname checking"
            )
        self.ssl_context = context

    def request(
        self,
        target: ValidatedHTTPSTarget,
        request_target: str,
        headers: Mapping[str, str],
        *,
        connect_timeout: float,
        read_timeout: float,
        deadline: float | None = None,
    ) -> HTTPResponseStream:
        last_error: BaseException | None = None
        for address in target.addresses:
            effective_connect_timeout = _remaining_timeout(
                deadline,
                connect_timeout,
            )
            connection: http.client.HTTPConnection
            if target.scheme == "https":
                connection = _PinnedHTTPSConnection(
                    target.hostname,
                    target.port,
                    address=address,
                    connect_timeout=effective_connect_timeout,
                    read_timeout=read_timeout,
                    deadline=deadline,
                    context=self.ssl_context,
                )
            else:
                connection = _PinnedHTTPConnection(
                    target.hostname,
                    target.port,
                    address=address,
                    connect_timeout=effective_connect_timeout,
                    read_timeout=read_timeout,
                    deadline=deadline,
                )
            deadline_timer = _start_deadline_timer(connection.close, deadline)
            try:
                connection.request(
                    "GET",
                    request_target,
                    headers=dict(headers),
                )
                if connection.sock is not None:
                    connection.sock.settimeout(
                        _remaining_timeout(deadline, read_timeout)
                    )
                response = connection.getresponse()
                if deadline_timer is not None:
                    deadline_timer.cancel()
                if _deadline_expired(deadline):
                    response.close()
                    raise TimeoutError("Rulebook fetch deadline exceeded")
                deadline_timer = _start_deadline_timer(response.close, deadline)
                return _LiveHTTPResponse(
                    connection,
                    response,
                    read_timeout=read_timeout,
                    deadline=deadline,
                    deadline_timer=deadline_timer,
                )
            except (OSError, ValueError, http.client.HTTPException) as exc:
                if deadline_timer is not None:
                    deadline_timer.cancel()
                connection.close()
                if _deadline_expired(deadline):
                    raise TimeoutError("Rulebook fetch deadline exceeded") from exc
                last_error = exc
        if last_error is None:
            raise OSError("No validated address available for connection")
        raise last_error


class _FetchAbort(RuntimeError):
    def __init__(
        self,
        code: RulebookFetchFailureCode,
        message: str,
        *,
        url: str,
        status_code: int | None = None,
        attempted_redirect_url: str | None = None,
        content_type: str | None = None,
        byte_size: int = 0,
        sha256: str | None = None,
        http_metadata: Mapping[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.url = url
        self.status_code = status_code
        self.attempted_redirect_url = attempted_redirect_url
        self.content_type = content_type
        self.byte_size = byte_size
        self.sha256 = sha256
        self.http_metadata = dict(http_metadata or {})


class RulebookFetcher:
    def __init__(
        self,
        *,
        manuals_dir: str | Path = "/data/manuals",
        resolver: AddressResolver | None = None,
        transport: HTTPTransport | None = None,
        policy: RulebookFetchPolicy | None = None,
    ):
        self.manuals_dir = Path(manuals_dir)
        self.resolver = resolver or SocketAddressResolver()
        self.transport = transport or PinnedHTTPTransport()
        self.policy = policy or RulebookFetchPolicy()

    def fetch(self, candidate: RulebookCandidate) -> RulebookFetchResult:
        if not isinstance(candidate, RulebookCandidate):
            raise TypeError("RulebookFetcher accepts only RulebookCandidate instances")

        requested_url = candidate.url
        current_url = requested_url
        redirects: list[RedirectHop] = []
        visited = {current_url}
        deadline = time.monotonic() + self.policy.fetch_timeout_seconds

        try:
            while True:
                self._ensure_deadline(deadline, current_url)
                target = self._validated_target(current_url, deadline=deadline)
                response = self.transport.request(
                    target,
                    self._request_target(current_url),
                    self._request_headers(target),
                    connect_timeout=self.policy.connect_timeout_seconds,
                    read_timeout=self.policy.read_timeout_seconds,
                    deadline=deadline,
                )
                try:
                    if response.status in _REDIRECT_STATUSES:
                        if len(redirects) >= self.policy.max_redirects:
                            raise _FetchAbort(
                                RulebookFetchFailureCode.REDIRECT_LIMIT,
                                "Maximum redirect count exceeded",
                                url=current_url,
                                status_code=response.status,
                            )
                        next_url = self._redirect_target(
                            current_url,
                            response.headers.get("location"),
                            status_code=response.status,
                        )
                        hop = RedirectHop(
                            status_code=response.status,
                            from_url=current_url,
                            to_url=next_url,
                        )
                        redirects.append(hop)
                        if next_url in visited:
                            raise _FetchAbort(
                                RulebookFetchFailureCode.REDIRECT_LOOP,
                                "Redirect loop detected",
                                url=next_url,
                                status_code=response.status,
                            )
                        visited.add(next_url)
                        current_url = next_url
                        continue

                    if response.status != 200:
                        raise _FetchAbort(
                            RulebookFetchFailureCode.HTTP_STATUS,
                            f"Unexpected HTTP status {response.status}",
                            url=current_url,
                            status_code=response.status,
                            content_type=self._normalized_content_type(
                                response.headers.get("content-type")
                            ),
                            http_metadata=self._http_metadata(response.headers),
                        )

                    return self._consume_pdf_response(
                        candidate,
                        requested_url=requested_url,
                        final_url=current_url,
                        redirects=tuple(redirects),
                        response=response,
                        deadline=deadline,
                    )
                finally:
                    response.close()
        except _FetchAbort as exc:
            if (
                exc.status_code is None
                and redirects
                and current_url == redirects[-1].to_url
            ):
                exc.status_code = redirects[-1].status_code
                if exc.attempted_redirect_url is None:
                    exc.attempted_redirect_url = current_url
            return self._failure_result(
                candidate,
                requested_url,
                current_url,
                tuple(redirects),
                exc,
            )
        except ssl.SSLError as exc:
            return self._failure_result(
                candidate,
                requested_url,
                current_url,
                tuple(redirects),
                _FetchAbort(
                    RulebookFetchFailureCode.TLS_ERROR,
                    str(exc) or exc.__class__.__name__,
                    url=current_url,
                ),
            )
        except TimeoutError as exc:
            return self._failure_result(
                candidate,
                requested_url,
                current_url,
                tuple(redirects),
                _FetchAbort(
                    RulebookFetchFailureCode.NETWORK_TIMEOUT,
                    str(exc) or exc.__class__.__name__,
                    url=current_url,
                ),
            )
        except (OSError, http.client.HTTPException) as exc:
            return self._failure_result(
                candidate,
                requested_url,
                current_url,
                tuple(redirects),
                _FetchAbort(
                    RulebookFetchFailureCode.NETWORK_ERROR,
                    str(exc) or exc.__class__.__name__,
                    url=current_url,
                ),
            )

    @staticmethod
    def _ensure_deadline(deadline: float, url: str) -> None:
        if time.monotonic() >= deadline:
            raise _FetchAbort(
                RulebookFetchFailureCode.NETWORK_TIMEOUT,
                "Rulebook fetch deadline exceeded",
                url=url,
            )

    def _validated_target(
        self,
        url: str,
        *,
        deadline: float,
    ) -> ValidatedHTTPSTarget:
        self._ensure_deadline(deadline, url)
        try:
            canonical = canonical_http_url(url)
        except ValueError as exc:
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                str(exc),
                url=url,
            ) from exc

        parts = urlsplit(canonical)
        hostname = parts.hostname
        if hostname is None:
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                "HTTP target has no hostname",
                url=canonical,
            )
        port = parts.port or (443 if parts.scheme == "https" else 80)

        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None

        if literal is not None:
            raw_addresses: Sequence[str] = (literal.compressed,)
        else:
            try:
                raw_addresses = self.resolver.resolve(
                    hostname,
                    port,
                    timeout=_remaining_timeout(
                        deadline,
                        self.policy.fetch_timeout_seconds,
                    ),
                )
            except TimeoutError as exc:
                raise _FetchAbort(
                    RulebookFetchFailureCode.NETWORK_TIMEOUT,
                    str(exc) or "DNS resolution deadline exceeded",
                    url=canonical,
                ) from exc
            except OSError as exc:
                raise _FetchAbort(
                    RulebookFetchFailureCode.DNS_FAILURE,
                    str(exc) or "DNS resolution failed",
                    url=canonical,
                ) from exc
            except Exception as exc:
                raise _FetchAbort(
                    RulebookFetchFailureCode.DNS_FAILURE,
                    str(exc) or exc.__class__.__name__,
                    url=canonical,
                ) from exc

        self._ensure_deadline(deadline, canonical)

        if not raw_addresses:
            raise _FetchAbort(
                RulebookFetchFailureCode.DNS_EMPTY,
                "DNS resolution returned no addresses",
                url=canonical,
            )

        validated: dict[tuple[int, bytes], str] = {}
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(str(raw_address))
            except ValueError as exc:
                raise _FetchAbort(
                    RulebookFetchFailureCode.DNS_INVALID_RESPONSE,
                    "DNS resolution returned a non-IP address",
                    url=canonical,
                ) from exc
            if is_disallowed_public_ip(address):
                raise _FetchAbort(
                    RulebookFetchFailureCode.SSRF_BLOCKED,
                    f"Resolved address is not public: {address.compressed}",
                    url=canonical,
                )
            validated[(address.version, address.packed)] = address.compressed

        ordered_addresses = tuple(
            validated[key]
            for key in sorted(validated)
        )
        return ValidatedHTTPSTarget(
            url=canonical,
            scheme=parts.scheme,
            hostname=hostname,
            port=port,
            host_header=parts.netloc,
            addresses=ordered_addresses,
        )

    def _redirect_target(
        self,
        current_url: str,
        location: str | None,
        *,
        status_code: int,
    ) -> str:
        if location is None or not location:
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                "Redirect response is missing a Location header",
                url=current_url,
                status_code=status_code,
            )
        if len(location) > 8192:
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                "Redirect Location is too long",
                url=current_url,
                status_code=status_code,
            )
        if (
            "\\" in location
            or any(
                char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F
                for char in location
            )
        ):
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                "Redirect Location contains whitespace, controls, or backslashes",
                url=current_url,
                status_code=status_code,
            )

        try:
            joined = urljoin(current_url, location)
        except (ValueError, TypeError) as exc:
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_REDIRECT,
                str(exc) or "Invalid redirect target",
                url=current_url,
                status_code=status_code,
            ) from exc

        attempted_redirect_url = self._safe_attempted_redirect_url(joined)
        try:
            next_url = canonical_http_url(joined)
        except (ValueError, TypeError) as exc:
            message = str(exc)
            code = (
                RulebookFetchFailureCode.SSRF_BLOCKED
                if "non-public" in message or "localhost" in message
                else RulebookFetchFailureCode.INVALID_REDIRECT
            )
            raise _FetchAbort(
                code,
                message or "Invalid redirect target",
                url=attempted_redirect_url or current_url,
                status_code=status_code,
                attempted_redirect_url=attempted_redirect_url,
            ) from exc

        current_scheme = urlsplit(current_url).scheme
        next_scheme = urlsplit(next_url).scheme
        if (
            current_scheme == "https"
            and next_scheme == "http"
            and not self.policy.allow_https_to_http_redirect
        ):
            raise _FetchAbort(
                RulebookFetchFailureCode.DOWNGRADE_REDIRECT,
                "HTTPS to HTTP redirect is not allowed",
                url=next_url,
                status_code=status_code,
                attempted_redirect_url=next_url,
            )
        return next_url

    @staticmethod
    def _safe_attempted_redirect_url(value: str) -> str | None:
        try:
            parts = urlsplit(value)
        except ValueError:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        return value

    @staticmethod
    def _request_target(url: str) -> str:
        parts = urlsplit(url)
        path = quote(
            parts.path or "/",
            safe="/:@!$&'()*+,;=-._~%",
            encoding="utf-8",
            errors="strict",
        )
        target = path
        if "?" in url.partition("#")[0]:
            query = quote(
                parts.query,
                safe="/?:@!$&'()*+,;=-._~%",
                encoding="utf-8",
                errors="strict",
            )
            target += f"?{query}"
        return target

    @staticmethod
    def _request_headers(target: ValidatedHTTPSTarget) -> Mapping[str, str]:
        return {
            "Host": target.host_header,
            "Accept": "application/pdf, application/octet-stream;q=0.8",
            "Accept-Encoding": "identity",
            "User-Agent": "BoardGameCompanion/0.1 guarded-rulebook-fetch",
            "Connection": "close",
        }

    def _consume_pdf_response(
        self,
        candidate: RulebookCandidate,
        *,
        requested_url: str,
        final_url: str,
        redirects: tuple[RedirectHop, ...],
        response: HTTPResponseStream,
        deadline: float,
    ) -> RulebookFetchResult:
        headers = response.headers
        content_type = self._normalized_content_type(headers.get("content-type"))
        http_metadata = self._http_metadata(headers)
        content_encoding = headers.get("content-encoding", "").strip().lower()
        if content_encoding not in {"", "identity"}:
            raise _FetchAbort(
                RulebookFetchFailureCode.UNSUPPORTED_CONTENT_ENCODING,
                f"Unsupported Content-Encoding: {content_encoding}",
                url=final_url,
                status_code=response.status,
                content_type=content_type,
                http_metadata=http_metadata,
            )
        if (
            content_type is not None
            and content_type not in self.policy.allowed_content_types
        ):
            raise _FetchAbort(
                RulebookFetchFailureCode.CONTENT_TYPE_REJECTED,
                f"Content-Type is not allowed for a PDF rulebook: {content_type}",
                url=final_url,
                status_code=response.status,
                content_type=content_type,
                http_metadata=http_metadata,
            )

        declared_length = self._content_length(headers.get("content-length"), final_url)
        if declared_length is not None and declared_length > self.policy.max_bytes:
            raise _FetchAbort(
                RulebookFetchFailureCode.CONTENT_TOO_LARGE,
                "Content-Length exceeds the configured download limit",
                url=final_url,
                status_code=response.status,
                content_type=content_type,
                http_metadata=http_metadata,
            )

        try:
            self.manuals_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _FetchAbort(
                RulebookFetchFailureCode.STORAGE_ERROR,
                str(exc) or "Unable to create the manuals directory",
                url=final_url,
                status_code=response.status,
                content_type=content_type,
                http_metadata=http_metadata,
            ) from exc

        temp_path: Path | None = None
        byte_size = 0
        prefix = bytearray()
        digest = hashlib.sha256()

        try:
            with ExitStack() as stack:
                try:
                    handle = stack.enter_context(
                        tempfile.NamedTemporaryFile(
                            mode="wb",
                            prefix=".bgc-rulebook-",
                            suffix=".part",
                            dir=self.manuals_dir,
                            delete=False,
                        )
                    )
                except OSError as exc:
                    raise _FetchAbort(
                        RulebookFetchFailureCode.STORAGE_ERROR,
                        str(exc) or "Unable to create a partial manual file",
                        url=final_url,
                        status_code=response.status,
                        content_type=content_type,
                        http_metadata=http_metadata,
                    ) from exc

                temp_path = Path(handle.name)
                while True:
                    self._ensure_deadline(deadline, final_url)
                    chunk = response.read(self.policy.chunk_size)
                    self._ensure_deadline(deadline, final_url)
                    if not chunk:
                        break
                    byte_size += len(chunk)
                    if byte_size > self.policy.max_bytes:
                        raise _FetchAbort(
                            RulebookFetchFailureCode.CONTENT_TOO_LARGE,
                            "Response body exceeded the configured download limit",
                            url=final_url,
                            status_code=response.status,
                            content_type=content_type,
                            byte_size=byte_size,
                            http_metadata=http_metadata,
                        )
                    if len(prefix) < 8:
                        prefix.extend(chunk[: 8 - len(prefix)])
                    digest.update(chunk)
                    try:
                        handle.write(chunk)
                    except OSError as exc:
                        raise _FetchAbort(
                            RulebookFetchFailureCode.STORAGE_ERROR,
                            str(exc) or "Unable to write the partial manual file",
                            url=final_url,
                            status_code=response.status,
                            content_type=content_type,
                            byte_size=byte_size,
                            http_metadata=http_metadata,
                        ) from exc
                try:
                    handle.flush()
                    os.fsync(handle.fileno())
                except OSError as exc:
                    raise _FetchAbort(
                        RulebookFetchFailureCode.STORAGE_ERROR,
                        str(exc) or "Unable to flush the partial manual file",
                        url=final_url,
                        status_code=response.status,
                        content_type=content_type,
                        byte_size=byte_size,
                        sha256=digest.hexdigest() if byte_size else None,
                        http_metadata=http_metadata,
                    ) from exc

            if byte_size == 0:
                raise _FetchAbort(
                    RulebookFetchFailureCode.EMPTY_BODY,
                    "Response body is empty",
                    url=final_url,
                    status_code=response.status,
                    content_type=content_type,
                    byte_size=byte_size,
                    http_metadata=http_metadata,
                )
            if declared_length is not None and byte_size != declared_length:
                raise _FetchAbort(
                    RulebookFetchFailureCode.CONTENT_LENGTH_MISMATCH,
                    "Response byte count does not match Content-Length",
                    url=final_url,
                    status_code=response.status,
                    content_type=content_type,
                    byte_size=byte_size,
                    sha256=digest.hexdigest(),
                    http_metadata=http_metadata,
                )
            if not bytes(prefix).startswith(b"%PDF-"):
                raise _FetchAbort(
                    RulebookFetchFailureCode.PDF_MAGIC_MISMATCH,
                    "Response body does not start with a PDF signature",
                    url=final_url,
                    status_code=response.status,
                    content_type=content_type,
                    byte_size=byte_size,
                    sha256=digest.hexdigest(),
                    http_metadata=http_metadata,
                )

            sha256 = digest.hexdigest()
            local_path = self._commit_temp_file(
                temp_path,
                sha256=sha256,
                byte_size=byte_size,
                url=final_url,
            )
            temp_path = None
            return RulebookFetchResult(
                candidate=candidate,
                requested_url=requested_url,
                final_url=final_url,
                redirect_chain=redirects,
                status_code=response.status,
                content_type=content_type,
                byte_size=byte_size,
                sha256=sha256,
                local_path=str(local_path),
                http_metadata=self._http_metadata(headers),
            )
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _commit_temp_file(
        self,
        temp_path: Path,
        *,
        sha256: str,
        byte_size: int,
        url: str,
    ) -> Path:
        final_path = self.manuals_dir / f"{sha256}.pdf"
        if final_path.exists():
            if self._existing_file_matches(final_path, sha256, byte_size):
                temp_path.unlink()
                return final_path
            raise _FetchAbort(
                RulebookFetchFailureCode.STORAGE_CONFLICT,
                "Existing content-addressed manual does not match its filename",
                url=url,
                status_code=200,
            )

        try:
            _atomic_noreplace_rename(temp_path, final_path)
        except FileExistsError:
            if self._existing_file_matches(final_path, sha256, byte_size):
                temp_path.unlink()
                return final_path
            raise _FetchAbort(
                RulebookFetchFailureCode.STORAGE_CONFLICT,
                "Concurrent manual file conflicts with downloaded content",
                url=url,
                status_code=200,
            )
        except OSError as exc:
            raise _FetchAbort(
                RulebookFetchFailureCode.STORAGE_ERROR,
                str(exc) or "Unable to atomically persist downloaded manual",
                url=url,
                status_code=200,
            ) from exc

        self._fsync_directory(self.manuals_dir)
        return final_path

    @staticmethod
    def _existing_file_matches(path: Path, sha256: str, byte_size: int) -> bool:
        try:
            if path.stat().st_size != byte_size:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(128 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest() == sha256
        except OSError:
            return False

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError:
            return
        try:
            try:
                os.fsync(descriptor)
            except OSError:
                pass
        finally:
            os.close(descriptor)

    @staticmethod
    def _normalized_content_type(value: str | None) -> str | None:
        if value is None:
            return None
        content_type = value.split(";", 1)[0].strip().lower()
        return content_type or None

    @staticmethod
    def _content_length(value: str | None, url: str) -> int | None:
        if value is None or not value.strip():
            return None
        text = value.strip()
        if not text.isdigit():
            raise _FetchAbort(
                RulebookFetchFailureCode.INVALID_CONTENT_LENGTH,
                "Content-Length is not a non-negative integer",
                url=url,
                status_code=200,
            )
        return int(text)

    @staticmethod
    def _http_metadata(headers: Mapping[str, str]) -> Mapping[str, str]:
        return {
            key: headers[key]
            for key in _SAFE_HTTP_METADATA
            if key in headers
        }

    @staticmethod
    def _failure_result(
        candidate: RulebookCandidate,
        requested_url: str,
        final_url: str,
        redirects: tuple[RedirectHop, ...],
        abort: _FetchAbort,
    ) -> RulebookFetchResult:
        return RulebookFetchResult(
            candidate=candidate,
            requested_url=requested_url,
            final_url=final_url,
            redirect_chain=redirects,
            status_code=abort.status_code,
            content_type=abort.content_type,
            byte_size=abort.byte_size,
            sha256=abort.sha256,
            http_metadata=abort.http_metadata,
            failure=RulebookFetchFailure(
                code=abort.code,
                message=str(abort),
                url=abort.url,
                status_code=abort.status_code,
                attempted_redirect_url=abort.attempted_redirect_url,
            ),
        )