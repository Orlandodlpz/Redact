"""The hosted demo's front door: a passcode, a per IP limit and a daily cap. Owner: Victor.

This exists for one reason. The hosted demo runs on a real key with a real balance, and
the link goes in a public submission. Without a gate, one person with a script spends
the credits the demo needs on judging day.

Three layers, cheapest first:

1. **Passcode.** A shared secret in `DEMO_PASSCODE`, sent in the `X-Redact-Passcode`
   header. A header, not a query string and not a URL, because query strings end up in
   access logs at every hop. Unset means the gate is off, which is what local
   development wants; the deploy sets it.
2. **Per IP limit.** A fixed window of `RATE_LIMIT_PER_IP_PER_HOUR` analyze calls per
   hour. Stops one visitor burning the budget without stopping a judge trying the demo
   a few times.
3. **Daily cap.** `DAILY_ANALYZE_CAP` analyze calls across everyone, per day. The per IP
   limit does nothing against a handful of addresses, and this is the number that bounds
   the bill. At the Phase 1 estimate of about $0.06 per image, the default of 200 bounds
   a day at roughly $12.

`/health` is never gated, because the hosting platform calls it to decide whether the
service is alive.

Known limits, both fine for a demo and both worth saying out loud. The counters live in
this process, so two instances mean two sets of limits; the demo runs one instance.
And the client address is only as trustworthy as the hop in front of it, which is what
`TRUST_PROXY_HEADER` is about: behind a proxy the socket address is the proxy's, so the
forwarded header is the only real address, but anywhere else that header is whatever the
caller typed. It defaults to off and the deploy turns it on.
"""

import time
from dataclasses import dataclass, field

from app.config import Settings

PASSCODE_HEADER = "x-redact-passcode"
GATED_PATHS = ("/analyze", "/export")
# Only /analyze spends money, so only /analyze counts against the limits.
COUNTED_PATHS = ("/analyze",)

HOUR_S = 3600
DAY_S = 86400


@dataclass
class Decision:
    allowed: bool
    status: int = 200
    detail: str = ""
    retry_after_s: int | None = None


@dataclass
class _Window:
    started_at: float
    count: int = 0


@dataclass
class DemoGate:
    """Fixed window counters. Call `check` before the work, `record` after it starts."""

    settings: Settings
    _per_ip: dict[str, _Window] = field(default_factory=dict)
    _day: _Window | None = None

    def client_ip(self, forwarded_for: str | None, socket_host: str | None) -> str:
        """The address to count against.

        Behind a proxy the socket address is the proxy's, so every visitor would share
        one bucket; the forwarded header is the real address. Anywhere else that header
        is attacker controlled, so it is ignored unless the deploy says to trust it.
        """
        if self.settings.trust_proxy_header and forwarded_for:
            # The first entry is the original client; the rest are proxies.
            return forwarded_for.split(",")[0].strip() or "unknown"
        return socket_host or "unknown"

    def check(self, path: str, passcode: str | None, ip: str, now: float | None = None) -> Decision:
        if not any(path.startswith(p) for p in GATED_PATHS):
            return Decision(allowed=True)
        now = time.monotonic() if now is None else now

        expected = self.settings.demo_passcode
        if expected is not None:
            if passcode != expected.get_secret_value():
                # Same message either way: a different one for "missing" against "wrong"
                # tells a guesser which half they got right.
                return Decision(False, 401, "This demo needs a passcode.")

        if not any(path.startswith(p) for p in COUNTED_PATHS):
            return Decision(allowed=True)

        day = self._day
        if day is None or now - day.started_at >= DAY_S:
            day = self._day = _Window(started_at=now)
        if day.count >= self.settings.daily_analyze_cap:
            return Decision(
                False, 503,
                "The demo has reached its limit for today. Try again tomorrow.",
                retry_after_s=int(DAY_S - (now - day.started_at)),
            )

        window = self._per_ip.get(ip)
        if window is None or now - window.started_at >= HOUR_S:
            window = self._per_ip[ip] = _Window(started_at=now)
        if window.count >= self.settings.rate_limit_per_ip_per_hour:
            return Decision(
                False, 429,
                "That is a lot of images in one hour. Try again later.",
                retry_after_s=int(HOUR_S - (now - window.started_at)),
            )

        self._sweep(now)
        return Decision(allowed=True)

    def record(self, path: str, ip: str, now: float | None = None) -> None:
        """Counts one accepted analyze. Called after `check` allows it."""
        if not any(path.startswith(p) for p in COUNTED_PATHS):
            return
        now = time.monotonic() if now is None else now
        if self._day is None or now - self._day.started_at >= DAY_S:
            self._day = _Window(started_at=now)
        self._day.count += 1
        window = self._per_ip.get(ip)
        if window is None or now - window.started_at >= HOUR_S:
            window = self._per_ip[ip] = _Window(started_at=now)
        window.count += 1

    def _sweep(self, now: float) -> None:
        """Drop windows that have expired, so the dict cannot grow without bound."""
        if len(self._per_ip) < 1000:
            return
        stale = [ip for ip, w in self._per_ip.items() if now - w.started_at >= HOUR_S]
        for ip in stale:
            del self._per_ip[ip]
