from __future__ import annotations

import ssl


def create_ssl_context(
    ca_cert: str | None = None,
    client_cert: str | None = None,
    client_key: str | None = None,
    insecure: bool = False,
) -> ssl.SSLContext:
    """
    Create SSL context for TLS/mTLS connections.

    Args:
        ca_cert: Path to CA certificate file for server verification.
        client_cert: Path to client certificate file for mTLS.
        client_key: Path to client private key file for mTLS.
        insecure: If True, disable certificate verification (dev only).

    Returns:
        Configured SSL context.
    """
    context = ssl.create_default_context()

    if insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif ca_cert:
        context.load_verify_locations(ca_cert)

    if client_cert and client_key:
        context.load_cert_chain(client_cert, client_key)

    return context
