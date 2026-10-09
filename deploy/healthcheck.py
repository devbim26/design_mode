"""Check the login page without credentials or paid API requests."""
import http.client
import os
import sys


def healthy() -> bool:
    connection = http.client.HTTPConnection(
        "127.0.0.1", int(os.environ.get("INVOKEAI_PORT", "9090")), timeout=4
    )
    try:
        connection.request("GET", "/auth/login")
        response = connection.getresponse()
        return response.status in {200, 302, 303, 307, 308}
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(0 if healthy() else 1)
