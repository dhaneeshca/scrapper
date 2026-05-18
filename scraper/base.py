from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


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
