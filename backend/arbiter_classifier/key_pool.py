"""
Thread-safe API key pool with round-robin rotation and auto-failover.
Separated from batch_arbiter.py so it can be imported without heavy deps (pandas etc.).
"""

import os
import time
import threading
from pathlib import Path


def _read_env_file(filepath):
    """Parse a .env file directly from disk."""
    result = {}
    if Path(filepath).exists():
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
    return result


def _load_keys():
    """Load API keys from .env files."""
    backend_env = Path(__file__).parent.parent / ".env"
    env = _read_env_file(backend_env)

    # Fallback: settings.env
    settings_env = Path(__file__).parent / "config" / "settings.env"
    file_cfg = _read_env_file(settings_env)

    def _get(key):
        return env.get(key) or file_cfg.get(key) or os.environ.get(key, "")

    # Multi-key: TURING_API_KEYS (comma-separated)
    raw_keys = _get("TURING_API_KEYS")
    if raw_keys:
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        single = _get("TURING_API_KEY")
        keys = [single] if single and single != "YOUR_API_KEY" else []

    gw_key = _get("TURING_GW_KEY")
    auth = _get("TURING_AUTH")
    return keys, gw_key, auth


class KeyPool:
    """Thread-safe round-robin API key pool with auto-failover on budget/auth errors."""

    def __init__(self, keys: list, gw_key: str, auth: str):
        self._keys = list(keys)
        self._gw_key = gw_key
        self._auth = auth
        self._lock = threading.Lock()
        self._idx = 0
        # State per key: "active" | "budget_exceeded" | "forbidden" | "rate_limited"
        self._state = {k: "active" for k in self._keys}
        self._rate_limit_until = {}  # key -> timestamp when cooldown ends
        self._stats = {k: {"ok": 0, "fail": 0} for k in self._keys}

    @property
    def total_keys(self):
        return len(self._keys)

    @property
    def active_keys(self):
        with self._lock:
            return self._count_active()

    def _count_active(self):
        """Count active keys (must be called with lock held)."""
        now = time.time()
        return sum(
            1 for k in self._keys
            if self._state[k] == "active"
            or (self._state[k] == "rate_limited"
                and now >= self._rate_limit_until.get(k, 0))
        )

    def get_headers(self) -> dict | None:
        """Return headers using next available key (round-robin). None if all exhausted."""
        with self._lock:
            now = time.time()
            tried = 0
            while tried < len(self._keys):
                key = self._keys[self._idx % len(self._keys)]
                self._idx += 1
                tried += 1
                st = self._state[key]
                if st == "active":
                    return self._build_headers(key)
                if st == "rate_limited" and now >= self._rate_limit_until.get(key, 0):
                    self._state[key] = "active"
                    return self._build_headers(key)
                # budget_exceeded / forbidden → skip
            return None  # all keys exhausted

    def report_success(self, headers: dict):
        key = headers.get("x-api-key", "")
        with self._lock:
            if key in self._stats:
                self._stats[key]["ok"] += 1

    def report_error(self, headers: dict, status_code: int):
        key = headers.get("x-api-key", "")
        with self._lock:
            if key not in self._state:
                return
            self._stats[key]["fail"] += 1
            if status_code == 402:
                self._state[key] = "budget_exceeded"
                active = self._count_active()
                print(f"[KEY-POOL] 💳 Key ...{key[-8:]} budget exceeded. "
                      f"{active} key(s) remaining.")
            elif status_code == 403:
                self._state[key] = "forbidden"
                print(f"[KEY-POOL] 🔒 Key ...{key[-8:]} forbidden (403).")
            elif status_code == 429:
                self._state[key] = "rate_limited"
                self._rate_limit_until[key] = time.time() + 60  # cooldown 60s
                print(f"[KEY-POOL] ⏱️  Key ...{key[-8:]} rate-limited, cooling down 60s.")

    def reset(self):
        """Reset all keys to active (e.g. when starting a new run with fresh budget)."""
        with self._lock:
            for k in self._keys:
                self._state[k] = "active"
                self._stats[k] = {"ok": 0, "fail": 0}
            self._rate_limit_until.clear()
            self._idx = 0

    def summary(self) -> dict:
        with self._lock:
            return {
                "total_keys": len(self._keys),
                "active": sum(1 for k in self._keys if self._state[k] == "active"),
                "budget_exceeded": sum(1 for k in self._keys if self._state[k] == "budget_exceeded"),
                "rate_limited": sum(1 for k in self._keys if self._state[k] == "rate_limited"),
                "forbidden": sum(1 for k in self._keys if self._state[k] == "forbidden"),
                "per_key": [
                    {"key_suffix": f"...{k[-8:]}", "state": self._state[k],
                     "ok": self._stats[k]["ok"], "fail": self._stats[k]["fail"]}
                    for k in self._keys
                ],
            }

    def _build_headers(self, api_key: str) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "x-api-gw-key": self._gw_key or "",
            "Authorization": self._auth or "",
        }


# ── Module-level singleton ────────────────────────────────────────────
_keys, _gw_key, _auth = _load_keys()
key_pool = KeyPool(_keys, _gw_key, _auth)
