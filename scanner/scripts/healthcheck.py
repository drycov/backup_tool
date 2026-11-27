"""Container liveness probe: no proxy, no redirects, no external dependency."""
import http.client
import sys

def main():
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    try:
        conn.request("GET", "/health/live", headers={"Host": "localhost"})
        response = conn.getresponse()
        if response.status != 200:
            print(f"scanner healthcheck: HTTP {response.status}", file=sys.stderr)
            return 1
        return 0
    except OSError as exc:
        print(f"scanner healthcheck: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    sys.exit(main())
