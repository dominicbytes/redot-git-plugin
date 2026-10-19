"""Offline HTTP challenges followed by same-origin or cross-port redirects."""

from __future__ import annotations

import base64
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator


@contextmanager
def redirect_fixture(cross_port: bool) -> Iterator[tuple[str, list[dict[str, object]]]]:
    events: list[dict[str, object]] = []
    expected = "Basic " + base64.b64encode(b"fixture:redirect-password").decode("ascii")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            destination = self.server is target or self.path.startswith("/destination/")
            authorization = self.headers.get("Authorization")
            events.append({"destination": destination, "authorization_present": authorization is not None,
                           "authorization_valid": authorization == expected})
            if destination and authorization is not None:
                self.send_response(404)
            elif authorization is None:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="offline-fixture"')
            else:
                self.send_response(307)
                self.send_header("WWW-Authenticate", 'Basic realm="offline-fixture"')
                port = target.server_port if cross_port else source.server_port
                self.send_header("Location", f"http://127.0.0.1:{port}/destination/info/refs?service=git-upload-pack")
            self.send_header("Content-Length", "0")
            self.end_headers()

    source = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    target = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (source, target)]
    for thread in threads:
        thread.start()
    try:
        yield f"http://127.0.0.1:{source.server_port}/repo", events
    finally:
        for server in (source, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
