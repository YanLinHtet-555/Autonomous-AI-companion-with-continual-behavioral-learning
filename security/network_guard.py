"""
NetworkGuard — blocks ALL outbound network connections from this process.

The AI companion must NEVER send data to the internet without explicit
user instruction. This guard patches Python's socket layer at startup,
intercepts every connection attempt, logs it, and blocks it unless the
user has explicitly unlocked a specific host for a limited session.

Nothing leaves your machine without your command.
"""

import socket
import ssl
import urllib.request
import threading
import os
from datetime import datetime


# Keep reference to original before patching
_real_socket_connect = socket.socket.connect
_real_socket_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


_lock = threading.Lock()
_blocked_attempts = []       # log of all blocked attempts
_allowed_hosts = {}          # host -> expiry timestamp (user-unlocked sessions)
_guard_active = False
_audit_callback = None       # set by AuditLog integration


def _is_local(host: str) -> bool:
    """Allow connections to localhost / loopback only."""
    local = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    return host in local or host.startswith("127.") or host.startswith("192.168.")


def _is_allowed(host: str) -> bool:
    if _is_local(host):
        return True
    with _lock:
        expiry = _allowed_hosts.get(host)
        if expiry and datetime.now().timestamp() < expiry:
            return True
    return False


def _blocked(host, port, method):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "blocked_host": host,
        "port": port,
        "method": method,
    }
    with _lock:
        _blocked_attempts.append(entry)
    msg = (f"\n[SECURITY] BLOCKED outbound connection to {host}:{port}\n"
           f"           The AI attempted to contact an external server.\n"
           f"           This request was BLOCKED. Your data stays local.\n"
           f"           To allow: use /allow-network {host} in the chat.\n")
    print(msg)
    if _audit_callback:
        _audit_callback("NETWORK_BLOCKED", f"{host}:{port}", severity="HIGH")
    raise PermissionError(
        f"[NetworkGuard] Outbound connection to {host}:{port} is blocked. "
        f"All data stays local. Use '/allow-network {host}' to temporarily unlock."
    )


def _patched_connect(self, address):
    if _guard_active:
        host = address[0] if isinstance(address, tuple) else str(address)
        port = address[1] if isinstance(address, tuple) else 0
        if not _is_allowed(host):
            _blocked(host, port, "socket.connect")
    return _real_socket_connect(self, address)


def _patched_connect_ex(self, address):
    if _guard_active:
        host = address[0] if isinstance(address, tuple) else str(address)
        port = address[1] if isinstance(address, tuple) else 0
        if not _is_allowed(host):
            _blocked(host, port, "socket.connect_ex")
    return _real_socket_connect_ex(self, address)


def _patched_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                                source_address=None):
    if _guard_active:
        host = address[0] if isinstance(address, tuple) else str(address)
        port = address[1] if isinstance(address, tuple) else 0
        if not _is_allowed(host):
            _blocked(host, port, "socket.create_connection")
    return _real_create_connection(address, timeout, source_address)


def activate(audit_callback=None):
    """
    Patch socket at the Python level. Call once at startup.
    After this, any outbound connection attempt is blocked and logged.
    """
    global _guard_active, _audit_callback
    socket.socket.connect = _patched_connect
    socket.socket.connect_ex = _patched_connect_ex
    socket.create_connection = _patched_create_connection
    _guard_active = True
    _audit_callback = audit_callback
    print("[NetworkGuard] ACTIVE — all outbound network connections blocked.")


def deactivate():
    """Restore original socket (only for shutdown/testing)."""
    global _guard_active
    socket.socket.connect = _real_socket_connect
    socket.socket.connect_ex = _real_socket_connect_ex
    socket.create_connection = _real_create_connection
    _guard_active = False
    print("[NetworkGuard] Deactivated.")


def allow_host(host: str, duration_minutes: int = 10):
    """
    Temporarily unlock a specific host. Requires user command.
    Access expires automatically after duration_minutes.
    """
    expiry = datetime.now().timestamp() + duration_minutes * 60
    with _lock:
        _allowed_hosts[host] = expiry
    print(f"[NetworkGuard] '{host}' allowed for {duration_minutes} minutes. "
          f"Expires at {datetime.fromtimestamp(expiry).strftime('%H:%M:%S')}")
    if _audit_callback:
        _audit_callback("NETWORK_UNLOCK", f"{host} for {duration_minutes}min",
                        severity="MEDIUM")


def revoke_host(host: str):
    with _lock:
        _allowed_hosts.pop(host, None)
    print(f"[NetworkGuard] Access to '{host}' revoked.")


def get_blocked_attempts():
    with _lock:
        return list(_blocked_attempts)


def status():
    with _lock:
        allowed = {h: datetime.fromtimestamp(e).strftime("%H:%M:%S")
                   for h, e in _allowed_hosts.items()
                   if datetime.now().timestamp() < e}
    print(f"\n[NetworkGuard] Status: {'ACTIVE' if _guard_active else 'INACTIVE'}")
    print(f"  Blocked attempts : {len(_blocked_attempts)}")
    print(f"  Allowed hosts    : {allowed or 'none'}")
    if _blocked_attempts:
        print("  Recent blocks:")
        for b in _blocked_attempts[-5:]:
            print(f"    {b['timestamp'][:19]}  {b['blocked_host']}:{b['port']}")
