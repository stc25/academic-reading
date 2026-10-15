"""Best-effort login reporting to the CNLP login monitor.

Each successful login POSTs {"app", "email", "method"} to MONITOR_URL ("sso" for
Microsoft sign-in, "email" for email + password) so the monitor can count logins.
It is fire-and-forget: it runs in a background thread with a
short timeout, never raises, and does nothing unless MONITOR_URL,
MONITOR_TOKEN and MONITOR_APP_NAME are all set, so it can never block or
break a login.
"""

import json
import logging
import os
import threading
import urllib.request

logger = logging.getLogger(__name__)


def _post(url: str, token: str, app: str, email: str, method: str) -> None:
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps({"app": app, "email": email, "method": method}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Monitor-Token": token},
        )
        urllib.request.urlopen(request, timeout=3).close()
    except Exception as exc:  # noqa: BLE001 - monitoring must never affect a login
        logger.debug("login report failed: %s", exc)


def report_login(email: str, method: str) -> None:
    url = os.environ.get("MONITOR_URL", "")
    token = os.environ.get("MONITOR_TOKEN", "")
    app = os.environ.get("MONITOR_APP_NAME", "")
    if not (url and token and app and email):
        return
    threading.Thread(target=_post, args=(url, token, app, email, method), daemon=True).start()
