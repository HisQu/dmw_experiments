"""Expose LM Studio while rewriting DMW's pinned generation-model alias."""

import argparse
import http.client
import json
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ALIASES = {"qwen3.6-27b", "qwen/qwen3.6-27b"}
LMSTUDIO_MODEL_ID = "qwen/qwen3.6-27b"


class ProxyHandler(BaseHTTPRequestHandler):
    """Relay model discovery and generation to the Windows LM Studio server."""

    upstream_host: str
    upstream_port: int

    def do_GET(self) -> None:  # noqa: N802
        """Relay model-catalog requests without modifying their payload."""
        self._relay(method="GET", body=None)

    def do_POST(self) -> None:  # noqa: N802
        """Rewrite the experiment alias, then relay one generation request."""
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        if body.get("model") in MODEL_ALIASES:
            # > DMW uses a pinned provider alias while the currently loaded
            # > Q6_K model exposes its canonical LM Studio catalog identifier.
            body["model"] = LMSTUDIO_MODEL_ID
        self._relay(method="POST", body=json.dumps(body).encode())

    def _relay(self, *, method: str, body: bytes | None) -> None:
        """Forward one request and copy the complete response body.

        :param method: HTTP method sent to LM Studio.
        :param body: Optional encoded JSON request payload.
        :return: None.
        """
        upstream = http.client.HTTPConnection(
            self.upstream_host,
            self.upstream_port,
            timeout=3600,
        )
        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        authorization = self.headers.get("Authorization")
        if authorization:
            headers["Authorization"] = authorization
        upstream.request(method, self.path, body, headers)
        response = upstream.getresponse()
        payload = response.read()
        self.send_response(response.status)
        self.send_header(
            "Content-Type",
            response.getheader("Content-Type", "application/json"),
        )
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        upstream.close()

    def log_message(self, *_args):
        return


def _parser() -> argparse.ArgumentParser:
    """Build the WSL-local relay interface.

    :return: Parser for the Windows relay and local listener addresses.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--upstream-host",
        required=True,
        help="Current Windows host address as visible from WSL.",
    )
    parser.add_argument("--upstream-port", type=int, default=1235)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=1236)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the WSL-local alias proxy until the process is interrupted.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Process exit status after the server stops.
    """
    args = _parser().parse_args(argv)
    ProxyHandler.upstream_host = args.upstream_host
    ProxyHandler.upstream_port = args.upstream_port
    ThreadingHTTPServer(
        (args.listen_host, args.listen_port),
        ProxyHandler,
    ).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
