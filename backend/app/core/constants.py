"""Protocol constants (techspec.md 5.1/5.5, appflow.md 6.3).

These are fixed by the API contract, not operator-tunable, so they live here
rather than in the environment-loaded settings.
"""
API_V1_PREFIX: str = "/api/v1"
WS_EVENTS_PATH: str = "/api/v1/ws/events"

# Pagination (techspec.md 5.1).
DEFAULT_PAGE_LIMIT: int = 50
MAX_PAGE_LIMIT: int = 200

# Clock-skew warning threshold (appflow.md 6.3): a worker whose frame clock
# diverges from the server clock by more than this produces false
# TEMPORAL_TOO_FAST rejections that look exactly like a matching bug.
CLOCK_SKEW_WARN_SECONDS: float = 5.0
