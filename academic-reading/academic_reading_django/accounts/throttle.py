from django.core.cache import cache

_WINDOW = 15 * 60
_PER_IP = 30
_PER_EMAIL = 10


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def throttled(request, scope: str, email: str) -> bool:
    """Count this attempt; True once the IP or email is over its limit.

    Per-process cache, so the effective limit scales with gunicorn workers —
    enough to stop mass guessing.
    """
    for key, limit in (
        (f"throttle:{scope}:ip:{_client_ip(request)}", _PER_IP),
        (f"throttle:{scope}:email:{email.strip().lower()}", _PER_EMAIL),
    ):
        cache.add(key, 0, _WINDOW)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, _WINDOW)
            count = 1
        if count > limit:
            return True
    return False
