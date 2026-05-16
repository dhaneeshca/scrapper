"""Seed default search configs if none exist."""
import sys
import uuid
from datetime import datetime

from store.db import init_db, get_session
from store.models import SearchConfig

init_db()

with get_session() as s:
    count = s.query(SearchConfig).count()
    if count > 0:
        print(f"Skipping seed — {count} config(s) already exist.")
        sys.exit(0)

    configs = [
        dict(
            name="Skoda Rapid 2017–2022",
            make="Skoda", model="Rapid",
            variants=[], year_min=2017, year_max=2022,
            fuel_types=[], transmissions=[],
            budget_max=900000,
            regions=["Chennai", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune"],
        ),
        dict(
            name="Skoda Slavia",
            make="Skoda", model="Slavia",
            variants=[], year_min=2022, year_max=None,
            fuel_types=[], transmissions=[],
            budget_max=1400000,
            regions=["Chennai", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune"],
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
    print(f"Seeded {len(configs)} configs: Skoda Rapid, Skoda Slavia.")
