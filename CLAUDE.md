# CLAUDE.md

## Project overview

Two-service MVP: a FastAPI backend (`app.py`) and a Streamlit frontend (`interface.py`). Run together via `docker-compose up --build`.

## Architecture

- `app.py` — FastAPI, single endpoint `GET /risk-score/{address}`. Calls three data sources in sequence and returns a combined JSON payload.
- `interface.py` — Streamlit UI. Calls the FastAPI backend and renders the result. Gets backend URL from `FASTAPI_BASE_URL` env var (defaults to `http://127.0.0.1:8000/risk-score` for local dev).
- `dockerfile` — API container (Python 3.11, installs slither-analyzer separately before requirements.txt to avoid dependency conflicts).
- `dockerfile.interface` — Interface container (lightweight: streamlit, pandas, requests, fpdf2).
- `docker-compose.yml` — Interface container sets `FASTAPI_BASE_URL=http://api:8000/risk-score` so it reaches the API by service name.

## Key implementation details

**Slither analysis** (`run_static_analysis`): calls the `slither` CLI via subprocess with `--json -` to get JSON on stdout. Timeout is 180s. Requires `ETHERSCAN_API_KEY` to fetch verified source from Etherscan. Contracts without verified source will fail gracefully and return an error field.

**Contract age** (`get_contract_age`): binary search from block 0 to latest, checking `w3.eth.get_code(address, block_identifier=mid)`. Finds the first block where code appeared.

**TVL** (`get_tvl_data`): gets native ETH balance via `w3.eth.get_balance(address)`, then multiplies by current ETH/USD price from CoinGecko's free API. Does not capture ERC-20 token balances.

**Scoring**: starts at 100, penalties for Slither findings, bonuses for age >1 year (+5) and ETH balance >$1M (+10). Clamped to [0, 100]. Higher = safer.

**PDF export** (`generate_pdf` in `interface.py`): built with `fpdf2`. Uses core Helvetica font (Latin-1 only) — Slither descriptions are sanitized via `.encode("latin-1", errors="replace")` before rendering.

## Environment variables

| Variable | Description |
|---|---|
| `NODE_API_URL` | Alchemy HTTPS endpoint for Ethereum mainnet |
| `ETHERSCAN_API_KEY` | Etherscan API key (needed for Slither source fetch) |

Copy `.env.example` to `.env` to get started. Never commit `.env`.

## Running locally without Docker

```bash
# Terminal 1 — API
source venv/bin/activate
uvicorn app:app --reload

# Terminal 2 — Interface
source venv/bin/activate
streamlit run interface.py
```

## Common issues

- **Slither produces no output**: contract source not verified on Etherscan, or Etherscan API key invalid.
- **Web3 not connected**: check `NODE_API_URL` is correct and the Alchemy key is valid.
- **Port 8501 already in use**: another Streamlit process is running — `lsof -i :8501` to find it.
