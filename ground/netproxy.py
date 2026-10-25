"""Tiny HTTP(S) forward proxy that sends everything out of ONE network interface (e.g. the Mac's Ethernet) regardless
of the system default route, with its own DNS over that interface. Used by ground/start.sh when the laptop is on
BalloonNet (whose gateway has no internet) but has internet on another interface.

    python3 netproxy.py --iface bridge1 --dns 192.168.20.1 --port 3128
Then: HTTPS_PROXY=http://127.0.0.1:3128 NO_PROXY=10.42.0.1,127.0.0.1,localhost  <program>
macOS only (IP_BOUND_IF); on Linux use SO_BINDTODEVICE instead."""
import argparse
import http.client
import http.server
import random
import select
import socket
import socketserver
import struct
import sys
import time
import urllib.parse

IP_BOUND_IF = 25            # macOS setsockopt level IPPROTO_IP
IFACE = None
DNS = []
_cache = {}


def _bound_socket(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    if IFACE:
        s.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, socket.if_nametoindex(IFACE))
    return s


def resolve(host):
    """A-record lookup over the bound interface (minimal DNS client), with a 60 s cache."""
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    now = time.time()
    hit = _cache.get(host)
    if hit and hit[1] > now:
        return hit[0]
    for server in DNS:
        try:
            q = struct.pack(">HHHHHH", random.randint(1, 65000), 0x0100, 1, 0, 0, 0)
            q += b"".join(bytes([len(p)]) + p.encode() for p in host.strip(".").split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
            s = _bound_socket(socket.SOCK_DGRAM)
            s.settimeout(3)
            s.sendto(q, (server, 53))
            data, _ = s.recvfrom(2048)
            s.close()
            qd = struct.unpack(">H", data[4:6])[0]
            an = struct.unpack(">H", data[6:8])[0]
            i = 12
            for _ in range(qd):                       # skip question
                while data[i] != 0:
                    i += data[i] + 1
                i += 5
            for _ in range(an):
                if data[i] & 0xC0 == 0xC0:
                    i += 2
                else:
                    while data[i] != 0:
                        i += data[i] + 1
                    i += 1
                typ, _cls, ttl, rdlen = struct.unpack(">HHIH", data[i:i + 10])
                i += 10
                if typ == 1 and rdlen == 4:
                    ip = socket.inet_ntoa(data[i:i + 4])
                    _cache[host] = (ip, now + max(30, min(ttl, 300)))
                    return ip
                i += rdlen
        except Exception:
            continue
    return socket.gethostbyname(host)                 # last resort: system resolver


def connect(host, port, timeout=20):
    s = _bound_socket()
    s.settimeout(timeout)
    s.connect((resolve(host), int(port)))
    return s


class BoundHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = connect(self.host, self.port, self.timeout)


class BoundHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        raw = connect(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_CONNECT(self):
        host, _, port = self.path.partition(":")
        try:
            up = connect(host, port or 443)
        except Exception as e:
            self.send_error(502, str(e))
            return
        self.send_response(200, "Connection established")
        self.end_headers()
        c = self.connection
        try:
            while True:
                r, _, x = select.select([c, up], [], [c, up], 90)
                if x or not r:
                    break
                for s in r:
                    d = s.recv(65536)
                    if not d:
                        return
                    (up if s is c else c).sendall(d)
        except OSError:
            pass
        finally:
            up.close()

    def _forward(self):
        u = urllib.parse.urlsplit(self.path)
        if not u.netloc:
            self.send_error(400, "absolute URI required")
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        cls = BoundHTTPSConnection if u.scheme == "https" else BoundHTTPConnection
        conn = cls(u.hostname, u.port, timeout=60)
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("proxy-connection", "connection", "keep-alive")}
        try:
            conn.request(self.command, urllib.parse.urlunsplit(("", "", u.path or "/", u.query, "")), body=body or None, headers=hdrs)
            r = conn.getresponse()
            data = r.read()
        except Exception as e:
            self.send_error(502, str(e))
            return
        self.send_response(r.status, r.reason)
        for k, v in r.getheaders():
            if k.lower() not in ("transfer-encoding", "connection", "keep-alive", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        conn.close()

    do_GET = do_POST = do_PUT = do_HEAD = do_DELETE = _forward


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global IFACE, DNS
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    ap.add_argument("--dns", default="1.1.1.1,8.8.8.8", help="comma-separated DNS servers reachable via --iface")
    ap.add_argument("--port", type=int, default=3128)
    a = ap.parse_args()
    IFACE, DNS = a.iface, [d for d in a.dns.split(",") if d]
    print("netproxy: 127.0.0.1:%d -> %s (dns %s)" % (a.port, IFACE, ",".join(DNS)), flush=True)
    Server(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
