# MoneyMint

A personal analytics platform for the Indian mutual fund market — covering **every
scheme AMFI publishes**, not a curated subset.

It ingests official daily NAV data for ~14,500 schemes, computes returns, risk and
category rankings nightly, and exposes them through a search/compare explorer with
backtesting, taxation and portfolio-overlap tools.

Built as a personal project to answer questions the free tools either charge for or
answer badly — "what has this fund *actually* returned from every possible start
date?", "how much of these three funds is the same ten stocks?", "what is the
Regular plan's commission really costing me in rupees?"

> **Status:** running daily on a local machine. Personal, non-commercial use —
> AMFI/AMC data is used under their terms and is **not redistributed** (no scraped
> data is committed to this repo).

---

## What's in the box

| | |
|---|---|
| **Coverage** | 14,486 schemes; 8,747 pass data-quality screening |
| **Price history** | 21.7M daily NAV records back to **April 2006** |
| **Holdings** | 2,825 funds across 10 fund houses (what each fund actually owns) |
| **Costs** | Real expense ratios (TER) + quarterly AUM for 7,088 schemes |
| **Tests** | 104 passing |

### Features

- **Explorer** — search/filter/sort all schemes by return, Sharpe, AUM, category
- **Returns & risk** — 7 periods; volatility, Sharpe, beta, alpha, max drawdown
- **Category rankings** — percentile standing against peers, computed nightly
- **Rolling returns** — return from *every* start date, not just two convenient ones
- **Portfolio overlap** — how much of a rupee is duplicated across funds (ISIN-matched)
- **Direct vs Regular** — what the commission actually costs, in rupees
- **Backtests & calculators** — SIP/lumpsum against real NAV history; SWP, goal, and
  Indian capital-gains tax estimates
- **Holdings & sector allocation** — parsed from monthly AMC disclosures

---

## The interesting problems

The analytics are the easy part. Most of the work was in the data.

**Every fund house publishes differently.** The SEBI disclosure template is nominally
standard; in practice one house ships a modern `.xlsx` under a `.xls` filename, another
puts ISIN before the instrument name, another merges cells so the "Name" header sits in
a different column than the data, another writes weights as fractions while its neighbour
uses percentages. The parser locates columns by *label* rather than position, detects the
weight scale from the data, and recovers names from whichever cell sits beside the ISIN —
so adding a fund house is usually just a URL, not a new parser.

**Bad source data is normal.** A wound-up fund still listed as active with year-old
prices. A one-day NAV jump of +169% from a side-pocket accounting event, which would
otherwise read as a 192% annual return. A government bond's *maturity date* sitting
where the statement date should be, stamping a portfolio with the year 2065. Weights
summing to 130% of a fund. Each of these is caught by an explicit guard, and the
offending data is **excluded rather than shown** — see *Data honesty* below.

**Matching funds across sources is genuinely hard.** AMFI, the AMC spreadsheets, and
the scheme master all name the same fund differently (`&` vs `and`, plan/option suffixes,
"Portfolio of X as on <date>"). Normalisation is asymmetric — a scheme master name is
stripped of its plan/option suffix, a spreadsheet title is not — because a blanket strip
once merged *DSP Savings Fund* with *DSP Regular Savings Fund*, stacking one portfolio on
another. Where two funds genuinely can't be told apart, the matcher **refuses to guess**.

**Silent failure is the real enemy.** Scheduled jobs on macOS failed for three weeks
without a trace: `cron` could not execute a script inside `~/Desktop` (a TCC-protected
folder), its errors went to a system mail file nobody reads, and a job that never starts
writes nothing to its own log. The fix was launchd with wrappers outside the protected
folder — plus a freshness endpoint and a banner in the UI, so stale data announces itself
where it's actually looked at.

---

## Data honesty

A deliberate rule, enforced in code: **never present a placeholder as real.**

- No benchmark exists for debt categories (no free index data), so it shows `—`, not a number
- Funds with stale or discontinuous price history are flagged and excluded from rankings
- Return periods that straddle a non-economic NAV jump emit `null` rather than a figure
- Seeded demo values from early prototyping were deleted outright, along with the
  endpoints that served them

Benchmarks use real index-fund NAVs as TRI proxies (licensed index data isn't free), and
that substitution is stated in the API response rather than hidden.

---

## Architecture

```
AMFI NAVAll.txt ──┐
MFAPI.in  ────────┼──► ingestion ──► PostgreSQL ──► FastAPI ──► React explorer
AMC disclosures ──┘    (nightly)      (partitioned    (REST)      (Vite)
                                       by year)
```

- **Backend** — Python, FastAPI, SQLAlchemy, PostgreSQL 17 (`nav_history` partitioned by year)
- **Frontend** — React + Vite + Recharts
- **Scheduling** — launchd: nightly prices, monthly holdings/costs, weekly backup
- **Ingestion** — resumable backfill, per-fund-house isolation (one bad file can't sink the run)

```
backend/app/
  ingestion/       daily sync, metrics engine, holdings ETL (one module per fund house)
  routers/         explorer, calculators
  calc.py          XIRR, backtests, projections, taxation
  rolling.py  overlap.py  costleak.py
```

---

## Running it

Requires PostgreSQL 17 and Python 3.12 (3.14 breaks `pydantic-core`).

```bash
# database
createdb moneymint
cd backend && python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python setup_db.py

# load data (the historical backfill takes ~40 min, and is resumable)
./venv/bin/python -m app.ingestion.daily_sync
./venv/bin/python -m app.ingestion.backfill_nav
./venv/bin/python -m app.ingestion.holdings.runner

# serve
./venv/bin/python -m uvicorn app.main:app --port 8000
cd ../fund-analyser-frontend && npm install && npm run dev
```

`DATABASE_URL` overrides the default local connection. Tests: `./venv/bin/python -m pytest`.

---

## Known limitations

Stated plainly, because they're real:

- **Exit load is not available.** It exists only as prose inside scheme information
  documents — there is no structured source, free or otherwise. The column is empty.
- **Holdings cover 10 of ~52 fund houses.** Most of the rest publish through JavaScript
  download portals, are months out of date on third-party mirrors, or block automated
  access. This is close to the practical ceiling without a paid data vendor.
- **Benchmarks are index-fund proxies**, not true TRI indices (licensing).
- **Local-first.** Designed to run on one machine; not deployed or multi-user.
- Taxation figures are illustrative, follow current rules as dated in the code, and are
  **not financial advice**.

---

## Acknowledgements

Data from [AMFI](https://www.amfiindia.com), [MFAPI.in](https://api.mfapi.in), and AMC
monthly portfolio disclosures. Used for personal analysis only, not redistributed.
