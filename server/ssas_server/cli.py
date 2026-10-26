"""Command line tools for the server (run inside the container):

    python -m ssas_server.cli create-admin
    python -m ssas_server.cli reset-totp EMAIL
    python -m ssas_server.cli set-password EMAIL
    python -m ssas_server.cli list-admins
    python -m ssas_server.cli ensure-cert
    python -m ssas_server.cli show-cert-fingerprint
"""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import ipaddress
import socket
import sys

from . import auth
from .config import load
from .db import Database


def _qr(uri: str) -> None:
    try:
        import qrcode

        q = qrcode.QRCode(border=1)
        q.add_data(uri)
        q.print_ascii(invert=True)
    except Exception:
        pass


def _ask_password() -> str:
    while True:
        p1 = getpass.getpass("Password (10+ characters): ")
        p2 = getpass.getpass("Repeat password: ")
        if p1 != p2:
            print("Passwords do not match.")
        elif len(p1) < 10:
            print("Too short.")
        else:
            return p1


def ensure_cert(cfg) -> None:
    """Create a self-signed certificate (valid 10 years) for HTTPS if there is none."""
    if cfg.cert_file.exists() and cfg.key_file.exists():
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    cfg.cert_file.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SSAS server")])
    alt = [x509.DNSName("localhost"), x509.DNSName(socket.gethostname())]
    for ip in ("127.0.0.1",):
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    cfg.key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    cfg.key_file.chmod(0o600)
    cfg.cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Created a self-signed certificate: {cfg.cert_file}")


def fingerprint(cfg) -> str:
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(cfg.cert_file.read_bytes())
    from cryptography.hazmat.primitives.serialization import Encoding

    return hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()


def main(argv: list[str]) -> int:
    cfg = load()
    db = Database(cfg.db_path)
    cmd = argv[0] if argv else ""
    if cmd == "create-admin":
        email = input("Email: ").strip()
        name = input("Name: ").strip() or email
        role = input("Role [developer / supervisor] (supervisor = view only): ").strip() or "supervisor"
        secret = auth.create_admin(db, email, name, role, _ask_password())
        uri = auth.provisioning_uri(secret, email, f"SSAS {cfg.school_name}")
        print("\nScan this QR code with Google Authenticator / Microsoft Authenticator:\n")
        _qr(uri)
        print(f"\nOr enter this key by hand: {secret}\n")
    elif cmd == "reset-totp" and len(argv) > 1:
        secret = auth.reset_totp(db, argv[1])
        _qr(auth.provisioning_uri(secret, argv[1], f"SSAS {cfg.school_name}"))
        print(f"New key: {secret}")
    elif cmd == "set-password" and len(argv) > 1:
        auth.set_password(db, argv[1], _ask_password())
        print("Password changed.")
    elif cmd == "list-admins":
        for r in db.q("SELECT email, name, role, created_at FROM admins ORDER BY id"):
            print(f"{r['email']:30} {r['role']:10} {r['name']}")
    elif cmd == "ensure-cert":
        ensure_cert(cfg)
    elif cmd == "show-cert-fingerprint":
        ensure_cert(cfg)
        print("Put this in SSAS Studio → Settings → Certificate fingerprint:")
        print(fingerprint(cfg))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
