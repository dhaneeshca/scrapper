"""Seed default search configs if none exist."""
import sys
import uuid
from datetime import datetime

from store.db import init_db, get_session
from store.models import SearchConfig

init_db()

_TN_CITIES = [
    "Chennai", "Coimbatore", "Trichy", "Madurai",
    "Salem", "Tirunelveli", "Vellore", "Erode", "Thanjavur", "Tiruppur",
    "Hosur", "Dindigul", "Thoothukudi", "Nagercoil", "Kanchipuram",
]

with get_session() as s:
    count = s.query(SearchConfig).count()
    if count > 0:
        print(f"Skipping seed — {count} config(s) already exist.")
        sys.exit(0)

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
