# Problem Statement

## Context

Buying a second-hand car in India is fragmented. Listings are spread across six major platforms — CarDekho, CarWale, Cars24, OLX, CarTrade, and Spinny — each with a different UI, different data quality, and no way to see across them at once. The same physical car can appear on multiple sites at different prices with no indication that it's the same vehicle.

Beyond the multi-site problem, within any single model there are multiple variants (e.g. Skoda Slavia: Active, Ambition, Style, Sportline) that command very different prices depending on year, mileage, and region. None of the platforms give you a clean view of what a specific variant actually trades at in the market.

## Gaps This Tool Fills

1. **Unified listing view** — all listings for a target model from all six sources in one table, refreshed on demand.

2. **Cross-site deduplication** — the same car listed on CarDekho and OLX appears as one entry with a "2 sources" badge showing the lower price.

3. **Variant × year price intelligence** — for a given make/model, show what each variant trades at per model year. Answers "what is a 2023 Slavia Style 1.5 DSG actually worth in Tamil Nadu right now?"

4. **Deal score** — each listing is scored against the fair value band for that variant/year, so underpriced cars are surfaced immediately.

5. **Regional filtering** — scraping is state-scoped. The States tab manages which cities and sources are active; search configs reference states, the engine expands to all cities automatically.

6. **Shortlist + comparison** — bookmark up to 4 cars and compare them side by side: price, year, km, variant, city, source, link.

7. **Price history** — track when a listing's price drops. A listing that dropped from ₹8.5 L to ₹7.8 L is a motivated seller.

8. **Not interested** — dismiss listings so they don't clutter the view on the next scrape.

## Target Sources

| Site | Notes |
|---|---|
| CarDekho | Largest inventory, dealer-heavy, JS-rendered |
| Cars24 | Fixed-price, quality-inspected, city-based hubs |
| CarWale | Mix of dealer and individual, good data quality |
| OLX | Individual sellers, raw prices, anti-bot measures |
| CarTrade | Dealer-heavy, city + make/model ID based search |
| Spinny | Fixed-price, quality-inspected, pure JSON API |

## Out of Scope (for now)

- Comparison with new car pricing
- Loan / EMI calculations
- Contacting sellers from the tool
- Mobile app
- Automatic scheduling (manual trigger only for now)
