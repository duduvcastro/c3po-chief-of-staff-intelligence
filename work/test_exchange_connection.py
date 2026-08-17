#!/usr/bin/env python3
import base64
import imaplib
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request


SERVICE = "chief-of-staff-exchange"
ACCOUNT = "eu@eduardocastro.com.br"
SERVER = "east.EXCH025.serverdata.net"


def get_password():
    generic = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVICE,
            "-w",
        ],
        text=True,
        capture_output=True,
    )
    if generic.returncode == 0:
        return generic.stdout.rstrip("\n"), None, "generic"

    internet = subprocess.run(
        [
            "security",
            "find-internet-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVER,
            "-w",
        ],
        text=True,
        capture_output=True,
    )
    if internet.returncode == 0:
        return internet.stdout.rstrip("\n"), None, "internet"

    return (
        None,
        generic.stderr.strip()
        or internet.stderr.strip()
        or "Keychain item not found",
        None,
    )


def test_tcp(host, port, timeout=10):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def test_tls(host, port, timeout=10):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        subject = cert.get("subject", [])
        return True, f"ok; certificate subject={subject[:1]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def test_imap(password):
    try:
        with imaplib.IMAP4_SSL(SERVER, 993, timeout=15) as mail:
            typ, _ = mail.login(ACCOUNT, password)
            if typ == "OK":
                mail.logout()
                return True, "IMAP login ok"
            return False, f"IMAP returned {typ}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def test_ews_basic(password):
    url = f"https://{SERVER}/EWS/Exchange.asmx"
    token = base64.b64encode(f"{ACCOUNT}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("User-Agent", "ChiefOfStaffDigitalConnectionTest/1.0")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return True, f"EWS HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            auth = exc.headers.get("WWW-Authenticate", "")
            return False, f"EWS HTTP 401; auth offered={auth[:160]}"
        return False, f"EWS HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main():
    password, error, item_type = get_password()
    print("Keychain:", f"ok ({item_type} password)" if password else f"failed - {error}")
    if not password:
        return 2

    for port in (443, 993):
        ok, msg = test_tcp(SERVER, port)
        print(f"TCP {SERVER}:{port}:", "ok" if ok else f"failed - {msg}")

    ok, msg = test_tls(SERVER, 443)
    print("TLS 443:", "ok" if ok else f"failed - {msg}")

    ok, msg = test_ews_basic(password)
    print("EWS Basic auth:", "ok" if ok else f"not confirmed - {msg}")

    ok, msg = test_imap(password)
    print("IMAP auth:", "ok" if ok else f"not confirmed - {msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
