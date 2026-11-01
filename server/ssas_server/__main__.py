"""Start the server: python -m ssas_server

Normal (local network): HTTPS on port 8443 with the server's own certificate (made on first start).
Behind a proxy that does HTTPS (deploy/vps): SSAS_TLS=off and SSAS_BEHIND_PROXY=true, plain HTTP on port 8000,
reachable only by the proxy.
"""

import os

import uvicorn

from .cli import ensure_cert
from .config import load
from .main import create_app


def run() -> None:
    cfg = load()
    host = os.environ.get("SSAS_HOST", "0.0.0.0")
    options: dict = {"workers": 1, "server_header": False, "proxy_headers": cfg.behind_proxy}
    if cfg.behind_proxy:
        # Trust the visitor address only when it comes from the proxy itself (deploy/vps sets Caddy's network).
        options["forwarded_allow_ips"] = os.environ.get("SSAS_TRUSTED_PROXIES", "127.0.0.1")
    if cfg.tls:
        ensure_cert(cfg)
        options.update(
            port=int(os.environ.get("SSAS_PORT", "8443")),
            ssl_certfile=str(cfg.cert_file),
            ssl_keyfile=str(cfg.key_file),
        )
    else:
        if not cfg.behind_proxy:
            print("WARNING: plain HTTP (SSAS_TLS=off). Use this only behind a proxy that does HTTPS.", flush=True)
        options.update(port=int(os.environ.get("SSAS_PORT", "8000")))
    uvicorn.run(create_app(cfg), host=host, **options)


if __name__ == "__main__":
    run()
