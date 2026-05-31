import logging
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional, TypeVar

_log = logging.getLogger(__name__)

_OWNER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}

T = TypeVar("T")


def fetch_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (),
    label: str = "",
) -> T:
    """Call fn(), retrying transient network failures with exponential backoff + jitter.

    Always retries OSError-family errors (DNS, connection reset, socket timeout). Callers
    pass library-specific transients via retry_on (e.g. requests.RequestException,
    playwright TimeoutError) since those do not subclass OSError. Re-raises the last
    exception once attempts are exhausted.
    """
    retryable = (OSError,) + retry_on
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retryable as exc:
            last_exc = exc
            if i == attempts - 1:
                break
            delay = base_delay * (2 ** i) + random.uniform(0, base_delay)
            _log.warning(
                "retry %s (%d/%d) in %.1fs after: %s", label or fn.__name__, i + 1, attempts, delay, exc
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _parse_owner_count(text: str) -> Optional[int]:
    # matches "1st Owner", "2nd Owner", "1 Owner", "1 owner" etc.
    m = re.search(r"(\d+)(?:st|nd|rd|th)?\s*owner", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(first|second|third|fourth)\s*owner", text, re.IGNORECASE)
    if m:
        return _OWNER_WORDS.get(m.group(1).lower())
    return None


@dataclass
class RawListing:
    source: str
    source_id: str
    url: str
    make: str
    model: str
    variant: str
    year: int
    km_driven: int
    fuel_type: str
    transmission: str
    price: int
    location_city: str
    location_state: str = ""
    seller_type: str = ""
    images: list[str] = field(default_factory=list)
    description: str = ""
    listed_at: Optional[date] = None
    owner_count: Optional[int] = None


class Scraper(ABC):
    name: str

    @abstractmethod
    def search(
        self,
        make: str,
        model: str,
        variants: list[str],
        regions: list[str],
        year_min: int,
        year_max: int,
        budget_max: int,
        city_configs: dict[str, dict] | None = None,
    ) -> list[RawListing]: ...
