# CLAUDE.md

## Project overview

Two deployment modes from one codebase:

| Mode | How to run | Analysis engine |
|---|---|---|
| **Streamlit Cloud** | Deploy `interface.py` as main module | GoPlus Security API (no native deps) |
| **Docker** | `docker-compose up --build` | Slither (via FastAPI backend) |

## Architecture

- `app.py` — FastAPI backend, single endpoint `GET /risk-score/{address}`. Used in Docker mode only.
- `interface.py` — Streamlit UI. Standalone in Streamlit Cloud mode; calls `app.py` in Docker mode.
- `dockerfile` — API container (Python 3.11, installs slither-analyzer separately before requirements.txt).
- `dockerfile.interface` — Interface container (streamlit, pandas, requests, fpdf2).
- `docker-compose.yml` — Sets `FASTAPI_BASE_URL=http://api:8000/risk-score` on the interface container, which switches it into Docker/Slither mode.

## Dual-mode detection in interface.py

`interface.py` checks for `FASTAPI_BASE_URL` at startup:
- **Set** → calls the FastAPI backend (`fetch_from_backend`), gets Slither results
- **Not set** → runs all data fetches inline (`fetch_direct`), uses GoPlus for security analysis

Secrets are read via `_secret(key)` which tries `st.secrets` first (Streamlit Cloud), then `os.getenv` (local/.env).

## Key implementation details

**GoPlus analysis** (`run_security_analysis` in `interface.py`): calls `api.gopluslabs.io/api/v1/token_security/1`. Returns binary flags (honeypot, selfdestruct, hidden owner, etc.). Only works for ERC-20 tokens — protocol/non-token contracts return no data.

**Slither analysis** (`run_static_analysis` in `app.py`): calls the `slither` CLI via subprocess with `--json -`. Timeout 180s. Requires `ETHERSCAN_API_KEY`. Docker only.

**Contract age** (`get_contract_age`): binary search from block 0 to latest via `w3.eth.get_code(address, block_identifier=mid)`.

**TVL** (`get_tvl_data`): native ETH balance via `w3.eth.get_balance(address)` × ETH/USD price from CoinGecko free API.

**Scoring**: starts at 100, −25/−15/−5 per critical/high/medium finding, +5 if age >1 year, +10 if ETH balance >$1M. Clamped to [0, 100]. Higher = safer.

**PDF export** (`generate_pdf` in `interface.py`): fpdf2 with Helvetica. Text sanitized to Latin-1 before rendering.

## Environment variables

| Variable | Description | Required |
|---|---|---|
| `NODE_API_URL` | Alchemy HTTPS endpoint for Ethereum mainnet | Both modes |
| `ETHERSCAN_API_KEY` | Etherscan API key for Slither source fetch | Docker only |
| `FASTAPI_BASE_URL` | Set automatically by docker-compose | Docker only |

On Streamlit Cloud, set `NODE_API_URL` (and optionally `ETHERSCAN_API_KEY`) in the app's **Secrets** dashboard under Settings.

## Streamlit Cloud deployment

1. Push to GitHub
2. Go to share.streamlit.io → New app → select repo, branch `main`, main module `interface.py`
3. Under Settings → Secrets, add:
   ```toml
   NODE_API_URL = "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
   ETHERSCAN_API_KEY = "YOUR_KEY"
   ```
4. Deploy

## Running locally without Docker

```bash
source venv/bin/activate
streamlit run interface.py   # standalone mode (GoPlus)
```

## Common issues

- **GoPlus returns no data**: contract is not an ERC-20 token — protocol contracts, multisigs, etc. are not in the GoPlus database.
- **Slither produces no output**: contract source not verified on Etherscan, or Etherscan API key invalid.
- **Web3 not connected**: check `NODE_API_URL` is correct and Alchemy key is valid.
- **Port 8501 already in use**: `lsof -i :8501` to find and kill the conflicting process.
