# flight_friend/config.py

from datetime import timedelta

ORIGIN: str = "ICN"
MANUAL_COOLDOWN: timedelta = timedelta(minutes=5)
STUCK_RUN_AFTER: timedelta = timedelta(minutes=10)
RUN_TIMEOUT: timedelta = timedelta(minutes=3)
NEAR_MISS_MIN_PCT: float = 0.10
NEAR_MISS_MIN_KRW: int = 30_000
ALERT_DROP_PCT: float = 0.03
ALERT_DROP_KRW: int = 10_000
MIN_TRACKING_DAYS: int = 3
NAVER_ONEWAY_TIMEOUT: float = 45.0
NAVER_ROUNDTRIP_TIMEOUT: float = 60.0
