# Problem Statement

## Context

Buying a second-hand car in India is fragmented. Listings are spread across at least four major platforms — CarDekho, CarWale, Cars24, and OLX — each with a different UI, different data quality, and no way to see across them at once. The same physical car can appear on multiple sites at different prices with no indication that it's the same vehicle.

Beyond the multi-site problem, within any single model there are multiple variants (e.g., Hyundai Verna: E, S, SX, SX(O)) that command very different prices depending on year, mileage, and region. None of the platforms give you a clean view of what a specific variant actually trades at in the market across its model years.

## Gaps This Tool Fills

1. **Unified listing view** — all listings for a target model from all sources in one table, refreshed on demand or on a schedule.

2. **Cross-site deduplication** — the same car listed on CarDekho and OLX appears as one entry with a "2 sources" badge, showing the better price.

3. **Variant × year price intelligence** — for a given make/model, show what each variant trades at per model year. Answers "what is a 2020 Verna SX actually worth in Bangalore right now?"

4. **Regional filtering** — filter by city/state to only see what's available where you'd actually buy.

5. **Shortlist + comparison** — bookmark up to 4 cars and compare them side by side: price, year, km driven, variant, city, source, link.

6. **Price history** — track when a listing's price drops. A listing that started at ₹8.5L and is now ₹7.8L is a motivated seller.

## Target Sources

| Site | Notes |
|---|---|
| CarDekho | Largest inventory, dealer-heavy, JS-rendered |
| Cars24 | Fixed-price, quality-inspected, JS-rendered |
| CarWale | Mix of dealer and individual, good data quality |
| OLX | Individual sellers, raw prices, anti-bot measures |

## Out of Scope (for now)

- Any comparison with new car pricing
- Loan / EMI calculations
- Contacting sellers from the tool
- Mobile app
