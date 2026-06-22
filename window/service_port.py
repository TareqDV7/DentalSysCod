"""Service-port handshake (window side).

The desktop window (DentaCare.exe) and the Flask service run as separate
processes. The service binds its preferred port if free, otherwise any free
port, and publishes the chosen port to ``<data dir>/service.port``. This pure
module — deliberately free of GUI dependencies so it stays import-safe in tests
— lets the window read that file and point at the exact running server instead
of assuming 5000 (which would show another local app's UI when something else
already owns 5000).
"""

from window.data_dir import resolve_data_dir

DEFAULT_SERVICE_PORT = 5000
SERVICE_PORT_FILENAME = 'service.port'


def read_service_port(default: int = DEFAULT_SERVICE_PORT) -> int:
    """Return the port the service published, or `default` when the file is
    missing/unreadable/garbage. Never raises."""
    try:
        text = (resolve_data_dir() / SERVICE_PORT_FILENAME).read_text(encoding='utf-8').strip()
        port = int(text)
        if 1 <= port <= 65535:
            return port
    except (OSError, ValueError):
        pass
    return default


def service_url(default_port: int = DEFAULT_SERVICE_PORT) -> str:
    """The http://127.0.0.1:<port> URL for the local service."""
    return f'http://127.0.0.1:{read_service_port(default_port)}'
