"""Seed default search configs and source city configs if none exist."""
import sys
import uuid
from datetime import datetime

from store.db import init_db, get_session
from store.models import SearchConfig, SourceCityConfig

init_db()

_TN_CITIES = [
    "Chennai", "Coimbatore", "Trichy", "Madurai",
    "Salem", "Tirunelveli", "Vellore", "Erode", "Thanjavur", "Tiruppur",
    "Hosur", "Dindigul", "Thoothukudi", "Nagercoil", "Kanchipuram", "Namakkal",
]

with get_session() as s:
    count = s.query(SearchConfig).count()
    if count > 0:
        print(f"Skipping SearchConfig seed — {count} config(s) already exist.")
    else:
        configs = [
            dict(
                name="Skoda Slavia",
                make="Skoda", model="Slavia",
                variants=[], year_min=2022, year_max=None,
                fuel_types=[], transmissions=[],
                budget_max=1_400_000,
                regions=_TN_CITIES,
            ),
            dict(
                name="Skoda Rapid 2017–2022",
                make="Skoda", model="Rapid",
                variants=[], year_min=2017, year_max=2022,
                fuel_types=[], transmissions=[],
                budget_max=900_000,
                regions=_TN_CITIES,
            ),
            dict(
                name="Volkswagen Virtus",
                make="Volkswagen", model="Virtus",
                variants=[], year_min=2022, year_max=2025,
                fuel_types=[], transmissions=[],
                budget_max=1_200_000,
                regions=_TN_CITIES,
            ),
            dict(
                name="Hyundai Verna",
                make="Hyundai", model="Verna",
                variants=[], year_min=2018, year_max=2025,
                fuel_types=[], transmissions=[],
                budget_max=1_200_000,
                regions=_TN_CITIES,
            ),
            dict(
                name="VW Vento — TN",
                make="Volkswagen", model="Vento",
                variants=[], year_min=2018, year_max=2022,
                fuel_types=[], transmissions=[],
                budget_max=800_000,
                regions=_TN_CITIES,
            ),
        ]

        for c in configs:
            s.add(SearchConfig(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                is_active=True,
                **c,
            ))
        s.commit()
        names = ", ".join(c["name"] for c in configs)
        print(f"Seeded {len(configs)} configs: {names}.")


# ── Source city config seed ───────────────────────────────────────────────────

ALL_SOURCES = ["olx", "cartrade", "cars24", "spinny", "carwale", "cardekho"]

# OLX location IDs per state (slug, location_id)
_OLX_STATES = {
    "tamil-nadu":    {"slug": "tamil-nadu",    "location_id": "2001173"},
    "delhi":         {"slug": "delhi",         "location_id": "2001160"},
    "maharashtra":   {"slug": "maharashtra",   "location_id": "2001168"},
    "karnataka":     {"slug": "karnataka",     "location_id": "2001165"},
    "telangana":     {"slug": "telangana",     "location_id": "2001154"},
    "kerala":        {"slug": "kerala",        "location_id": "2001166"},
    "gujarat":       {"slug": "gujarat",       "location_id": "2001164"},
    "west-bengal":   {"slug": "west-bengal",   "location_id": "2001176"},
    "rajasthan":     {"slug": "rajasthan",     "location_id": "2001171"},
    "uttar-pradesh": {"slug": "uttar-pradesh", "location_id": "2001174"},
    "punjab":        {"slug": "punjab",        "location_id": "2001170"},
}

# (state_name, state_key, city_name, city_key,
#  cartrade_cfg or None,
#  cars24_supported, cars24_slug_override,
#  spinny_supported)
_SEED_CITIES = [
    # ── Tamil Nadu ─────────────────────────────────────────────────────────
    ("Tamil Nadu", "tamil-nadu", "Chennai",     "chennai",
     {"slug": "chennai",         "city_id": 176},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Coimbatore",  "coimbatore",
     {"slug": "coimbatore",      "city_id": 177},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Trichy",      "trichy",
     {"slug": "tiruchirappalli", "city_id": 194},  True,  "tiruchirappalli", True),
    ("Tamil Nadu", "tamil-nadu", "Madurai",     "madurai",
     {"slug": "madurai",         "city_id": 184},  True,  None,              False),
    ("Tamil Nadu", "tamil-nadu", "Salem",       "salem",
     {"slug": "salem",           "city_id": 191},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Tirunelveli", "tirunelveli",
     {"slug": "tirunelveli",     "city_id": 195},  True,  None,              False),
    ("Tamil Nadu", "tamil-nadu", "Vellore",     "vellore",
     {"slug": "vellore",         "city_id": 304},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Erode",       "erode",
     {"slug": "erode",           "city_id": 340},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Thanjavur",   "thanjavur",
     {"slug": "thanjavur",       "city_id": 193},  False, None,              False),
    ("Tamil Nadu", "tamil-nadu", "Tiruppur",    "tiruppur",
     {"slug": "tiruppur",        "city_id": 347},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Hosur",       "hosur",
     {"slug": "hosur",           "city_id": 534},  True,  None,              True),
    ("Tamil Nadu", "tamil-nadu", "Dindigul",    "dindigul",
     {"slug": "dindigul",        "city_id": 181},  True,  None,              False),
    ("Tamil Nadu", "tamil-nadu", "Thoothukudi", "thoothukudi",
     {"slug": "thoothukudi",     "city_id": 1535}, False, None,              False),
    ("Tamil Nadu", "tamil-nadu", "Nagercoil",   "nagercoil",
     {"slug": "nagercoil",       "city_id": 342},  False, None,              False),
    ("Tamil Nadu", "tamil-nadu", "Kanchipuram", "kanchipuram",
     {"slug": "kancheepuram",    "city_id": 474},  False, None,              False),
    ("Tamil Nadu", "tamil-nadu", "Namakkal",    "namakkal",
     {"slug": "namakkal",        "city_id": 343},  True,  None,              False),
    # ── Delhi / NCR ────────────────────────────────────────────────────────
    ("Delhi",      "delhi",      "Delhi",       "delhi",
     {"slug": "delhi",           "city_id": 10},   False, None,              False),
    ("Delhi",      "delhi",      "Noida",       "noida",
     None,                                         False, None,              False),
    ("Delhi",      "delhi",      "Ghaziabad",   "ghaziabad",
     None,                                         False, None,              False),
    # ── Maharashtra ────────────────────────────────────────────────────────
    ("Maharashtra", "maharashtra", "Mumbai",    "mumbai",
     {"slug": "mumbai",          "city_id": 1},    False, None,              False),
    ("Maharashtra", "maharashtra", "Pune",      "pune",
     {"slug": "pune",            "city_id": 12},   False, None,              False),
    ("Maharashtra", "maharashtra", "Nagpur",    "nagpur",
     None,                                         False, None,              False),
    ("Maharashtra", "maharashtra", "Thane",     "thane",
     None,                                         False, None,              False),
    # ── Karnataka ──────────────────────────────────────────────────────────
    ("Karnataka",  "karnataka",  "Bangalore",   "bangalore",
     {"slug": "bangalore",       "city_id": 2},    False, None,              False),
    ("Karnataka",  "karnataka",  "Mysore",      "mysore",
     None,                                         False, None,              False),
    # ── Telangana ──────────────────────────────────────────────────────────
    ("Telangana",  "telangana",  "Hyderabad",   "hyderabad",
     {"slug": "hyderabad",       "city_id": 105},  False, None,              False),
    # ── Kerala ─────────────────────────────────────────────────────────────
    ("Kerala",     "kerala",     "Kochi",       "kochi",
     None,                                         False, None,              False),
    ("Kerala",     "kerala",     "Thiruvananthapuram", "thiruvananthapuram",
     None,                                         False, None,              False),
    # ── Gujarat ────────────────────────────────────────────────────────────
    ("Gujarat",    "gujarat",    "Ahmedabad",   "ahmedabad",
     {"slug": "ahmedabad",       "city_id": 128},  False, None,              False),
    ("Gujarat",    "gujarat",    "Surat",       "surat",
     None,                                         False, None,              False),
    # ── West Bengal ────────────────────────────────────────────────────────
    ("West Bengal", "west-bengal", "Kolkata",   "kolkata",
     {"slug": "kolkata",         "city_id": 198},  False, None,              False),
    # ── Rajasthan ──────────────────────────────────────────────────────────
    ("Rajasthan",  "rajasthan",  "Jaipur",      "jaipur",
     None,                                         False, None,              False),
    # ── Punjab ─────────────────────────────────────────────────────────────
    ("Punjab",     "punjab",     "Chandigarh",  "chandigarh",
     None,                                         False, None,              False),
    ("Punjab",     "punjab",     "Ludhiana",    "ludhiana",
     None,                                         False, None,              False),
]


def _seed_source_city_configs(session):
    count = session.query(SourceCityConfig).count()
    if count > 0:
        print(f"Skipping SourceCityConfig seed — {count} row(s) already exist.")
        return

    rows = []
    for (state_name, state_key, city_name, city_key,
         cartrade_cfg, cars24_supported, cars24_slug, spinny_supported) in _SEED_CITIES:

        olx_cfg = _OLX_STATES.get(state_key)

        source_data = {
            "olx": (
                bool(olx_cfg),
                {**olx_cfg, "state_key": state_key} if olx_cfg else {},
            ),
            "cartrade": (
                bool(cartrade_cfg),
                cartrade_cfg or {},
            ),
            "cars24": (
                cars24_supported,
                {"slug": cars24_slug} if cars24_slug else {},
            ),
            "spinny": (
                spinny_supported,
                {},
            ),
            "carwale": (True, {}),
            "cardekho": (True, {}),
        }

        for source in ALL_SOURCES:
            is_supported, cfg = source_data[source]
            rows.append(SourceCityConfig(
                id=str(uuid.uuid4()),
                state_name=state_name,
                state_key=state_key,
                city_name=city_name,
                city_key=city_key,
                source=source,
                is_supported=is_supported,
                source_config=cfg,
            ))

    for row in rows:
        session.add(row)
    session.commit()
    print(f"Seeded {len(rows)} SourceCityConfig rows ({len(_SEED_CITIES)} cities × {len(ALL_SOURCES)} sources).")


with get_session() as s:
    _seed_source_city_configs(s)
