"""Loopback-only TLS SMTP capture for isolated browser tests; never an app endpoint."""

import argparse
import json
import os
import signal
import socketserver
import ssl
import subprocess
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def main() -> None:
    if not urlsplit(os.environ.get("RAPO_DATABASE_URL", "")).path.endswith("_test"):
        raise SystemExit("SMTP capture requires a dedicated test database")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--smtp-port", type=int, default=8026)
    parser.add_argument("--http-port", type=int, default=8025)
    args = parser.parse_args()
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            args.key,
            "-out",
            args.cert,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    messages: list[dict[str, str]] = []
    lock = threading.Lock()

    class SMTP(socketserver.StreamRequestHandler):
        def reply(self, value: bytes) -> None:
            self.wfile.write(value + b"\r\n")
            self.wfile.flush()

        def handle(self) -> None:
            self.connection.settimeout(15)
            secure = False
            self.reply(b"220 localhost test SMTP")
            while line := self.rfile.readline(8192):
                command = line.split(b" ", 1)[0].strip().upper()
                if command in {b"EHLO", b"HELO"}:
                    self.reply(b"250-localhost")
                    self.reply(b"250-AUTH PLAIN" if secure else b"250-STARTTLS")
                    self.reply(b"250 SIZE 100000")
                elif command == b"STARTTLS" and not secure:
                    self.reply(b"220 Begin TLS")
                    self.rfile.close()
                    self.wfile.close()
                    self.connection = context.wrap_socket(self.connection, server_side=True)
                    self.rfile = self.connection.makefile("rb")
                    self.wfile = self.connection.makefile("wb")
                    secure = True
                elif command == b"AUTH" and secure:
                    self.reply(b"235 Authenticated")
                elif command in {b"MAIL", b"RCPT", b"RSET", b"NOOP"} and secure:
                    self.reply(b"250 OK")
                elif command == b"DATA" and secure:
                    self.reply(b"354 End with a dot")
                    content = []
                    while (chunk := self.rfile.readline(65536)) not in {b".\r\n", b""}:
                        content.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                    message = BytesParser(policy=policy.default).parsebytes(b"".join(content))
                    with lock:
                        messages.append(
                            {
                                "to": str(message["To"]),
                                "subject": str(message["Subject"]),
                                "body": str(message.get_content()),
                            }
                        )
                    self.reply(b"250 Captured")
                elif command == b"QUIT":
                    self.reply(b"221 Bye")
                    return
                else:
                    self.reply(b"530 TLS required")

    class CaptureServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

        def handle_error(self, request: object, client_address: object) -> None:
            pass  # Do not echo test credentials or message contents on protocol errors.

    class Mailbox(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/health", "/messages"}:
                self.send_error(404)
                return
            with lock:
                body = json.dumps(messages if self.path == "/messages" else {"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    smtp = CaptureServer(("127.0.0.1", args.smtp_port), SMTP)
    http = ThreadingHTTPServer(("127.0.0.1", args.http_port), Mailbox)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    for server in (smtp, http):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        stop.wait()
    finally:
        for server in (smtp, http):
            server.shutdown()
            server.server_close()
        Path(args.cert).unlink(missing_ok=True)
        Path(args.key).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
