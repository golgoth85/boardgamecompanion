from __future__ import annotations

import ipaddress

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Project-owned public-address policy. These ranges intentionally mirror the
# conservative security semantics used by current CPython/IANA data rather than
# delegating the SSRF boundary to the runtime version of ipaddress.
_IPV4_DISALLOWED = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_IPV4_EXCEPTIONS = frozenset(
    (
        ipaddress.ip_address("192.0.0.9"),
        ipaddress.ip_address("192.0.0.10"),
    )
)

_IPV6_DISALLOWED = tuple(
    ipaddress.ip_network(value)
    for value in (
        "::/8",
        "100::/8",
        "200::/7",
        "400::/6",
        "800::/5",
        "1000::/4",
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "3fff::/20",
        "4000::/3",
        "6000::/3",
        "8000::/3",
        "a000::/3",
        "c000::/3",
        "e000::/4",
        "f000::/5",
        "f800::/6",
        "fc00::/7",
        "fe00::/9",
        "fec0::/10",
        "ff00::/8",
    )
)
_IPV6_EXCEPTIONS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "2001:1::1/128",
        "2001:1::2/128",
        "2001:3::/32",
        "2001:4:112::/48",
        "2001:20::/28",
        "2001:30::/28",
    )
)


def is_disallowed_public_ip(address: IPAddress) -> bool:
    """Return True unless *address* is permitted by BGC's stable public policy."""
    if isinstance(address, ipaddress.IPv4Address):
        if address in _IPV4_EXCEPTIONS:
            return False
        return any(address in network for network in _IPV4_DISALLOWED)

    if address.ipv4_mapped is not None:
        return True
    if any(address in network for network in _IPV6_EXCEPTIONS):
        return False
    return any(address in network for network in _IPV6_DISALLOWED)