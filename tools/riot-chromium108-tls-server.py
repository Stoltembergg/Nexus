#!/usr/bin/env python3
"""Local self-signed TLS server for the Chromium 108 repro: answers HTTP 200 or
a WebSocket upgrade and reports how each TLS handshake ended."""
import base64
import hashlib
import socket
import ssl
import sys
import threading

cert, key, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(cert, key)
listener = socket.create_server(("127.0.0.1", port))


def serve(raw):
    try:
        connection = context.wrap_socket(raw, server_side=True)
    except (ssl.SSLError, OSError) as error:
        print(f"SERVER handshake failed: {str(error)[:90]}", flush=True)
        return
    try:
        request = connection.recv(4096).decode("latin1")
        if "upgrade: websocket" in request.lower():
            key_line = next(l for l in request.split("\r\n") if l.lower().startswith("sec-websocket-key"))
            accept = base64.b64encode(hashlib.sha1(
                (key_line.split(":", 1)[1].strip() + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            connection.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            print("SERVER websocket upgraded", flush=True)
            connection.settimeout(5)
            try:
                connection.recv(64)
            except OSError:
                pass
        else:
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            print("SERVER https answered", flush=True)
    except (OSError, StopIteration) as error:
        print(f"SERVER request failed: {str(error)[:90]}", flush=True)
    finally:
        connection.close()


while True:
    client, _ = listener.accept()
    threading.Thread(target=serve, args=(client,), daemon=True).start()
