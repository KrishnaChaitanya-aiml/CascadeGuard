import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}


def get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    expires_at, value = item
    if time.time() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def set_value(key: str, value: Any, ttl: int):
    _CACHE[key] = (time.time() + ttl, value)
    return value
