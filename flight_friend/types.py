# flight_friend/types.py

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, TypedDict


class PreferencesDict(TypedDict, total=False):
    out_dep_window: list[str] | None
    in_dep_window: list[str] | None
    nonstop_only: bool
    include_airlines: list[str]
    exclude_airlines: list[str]
    max_price: int | None
    max_duration_min: int | None


@dataclass
class Preferences:
    out_dep_window: tuple[str, str] | None = None
    in_dep_window: tuple[str, str] | None = None
    nonstop_only: bool = False
    include_airlines: list[str] = field(default_factory=list)
    exclude_airlines: list[str] = field(default_factory=list)
    max_price: int | None = None
    max_duration_min: int | None = None

    def to_dict(self) -> PreferencesDict:
        return {
            "out_dep_window": list(self.out_dep_window) if self.out_dep_window else None,
            "in_dep_window": list(self.in_dep_window) if self.in_dep_window else None,
            "nonstop_only": self.nonstop_only,
            "include_airlines": self.include_airlines,
            "exclude_airlines": self.exclude_airlines,
            "max_price": self.max_price,
            "max_duration_min": self.max_duration_min,
        }

    @staticmethod
    def from_dict(d: PreferencesDict) -> "Preferences":
        out_dep_window = d.get("out_dep_window")
        in_dep_window = d.get("in_dep_window")
        return Preferences(
            out_dep_window=tuple(out_dep_window) if out_dep_window else None,  # type: ignore[arg-type]
            in_dep_window=tuple(in_dep_window) if in_dep_window else None,  # type: ignore[arg-type]
            nonstop_only=d.get("nonstop_only", False),
            include_airlines=list(d.get("include_airlines", [])),
            exclude_airlines=list(d.get("exclude_airlines", [])),
            max_price=d.get("max_price"),
            max_duration_min=d.get("max_duration_min"),
        )


@dataclass
class Trip:
    id: int
    origin: str
    destination: str
    out_date: date
    ret_date: date
    adults: int
    cabin: str
    prefs: Preferences
    target_price: int | None
    tracking: bool
    created_at: datetime
    archived_at: datetime | None


@dataclass
class Run:
    id: int
    trip_id: int
    trigger: str
    status: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass
class LegQuote:
    flight_key: str
    airline_iata: str
    airline_name: str
    flight_numbers: list[str]
    dep_airport: str
    arr_airport: str
    dep_time: str
    arr_time: str
    duration_min: int | None
    stops: int | None
    price: int
    booking_url: str | None
    search_url: str | None


@dataclass
class RtQuote:
    airline_iata: str
    out_flight_key: str
    total_price: int


@dataclass
class ProviderResult:
    status: Literal["ok", "empty", "blocked", "error"]
    legs: list[LegQuote]
    rts: list[RtQuote]
    error: str | None
    seconds: float


@dataclass
class Snapshot:
    id: int
    run_id: int
    trip_id: int
    provider: str
    kind: Literal["oneway", "roundtrip"]
    direction: Literal["out", "in"] | None
    date: date
    status: str
    card_count: int
    observed_at: datetime
    error: str | None
    legs: list[LegQuote]
    rts: list[RtQuote]
