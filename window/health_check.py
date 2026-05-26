"""Health polling for the DentaCare service from the window-app launcher.

The window app launches before the service is necessarily ready (especially
right after Windows boot when NSSM is still starting our process), so we
poll /healthz with a bounded retry-with-backoff loop and only open the
pywebview window once the service is reachable.
"""

import time
import urllib.error
import urllib.request


def wait_for_service(url: str, timeout: float = 10.0) -> bool:
    """Poll `url` until it returns HTTP 200 or `timeout` seconds elapse.

    Returns True if the service became healthy within the budget, False
    otherwise. Never raises — all transport errors are treated as 'not yet'.
    Uses exponential backoff capped at 1s between attempts."""
    deadline = time.monotonic() + timeout
    delay = 0.1
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError, TimeoutError):
            pass
        # Sleep, but not past the deadline.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        delay = min(delay * 1.5, 1.0)
    return False
