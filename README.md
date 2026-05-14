# s-scan-mvp

Smart contract security risk analyzer. Enter an Ethereum contract address and get a scored risk report combining static analysis, on-chain age, and ETH balance.

## How it works

| Signal | Source | Score impact |
|---|---|---|
| Vulnerability findings | Slither (via Etherscan source) | −25 critical, −15 high, −5 medium |
| Contract age | Binary search on-chain via Alchemy | +5 if older than 1 year |
| ETH held | Alchemy balance × CoinGecko price | +10 if >$1M |

Final score is 0–100 (higher = safer). Results can be exported as a PDF report.

## Setup

**Prerequisites:** Docker, Docker Compose

1. Copy the env template and fill in your keys:
   ```bash
   cp .env.example .env
   ```
   - `NODE_API_URL` — Alchemy HTTPS endpoint ([alchemy.com](https://alchemy.com))
   - `ETHERSCAN_API_KEY` — Etherscan API key ([etherscan.io](https://etherscan.io))

2. Build and run:
   ```bash
   docker-compose up --build
   ```

3. Open `http://localhost:8501` in your browser.

## Services

| Service | Port | Description |
|---|---|---|
| FastAPI backend | 8000 | Risk score API — `GET /risk-score/{address}` |
| Streamlit frontend | 8501 | Browser UI |

The API can also be queried directly:
```
http://localhost:8000/risk-score/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
```

## Notes

- Slither analysis requires the contract source to be verified on Etherscan. Unverified contracts will return a Slither error but still score on age and ETH balance.
- Analysis takes 1–3 minutes for complex contracts.
- ETH balance reflects native ETH only — ERC-20 tokens held by the contract are not included in the TVL estimate.
