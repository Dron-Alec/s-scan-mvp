# s-scan-mvp

Smart contract security score analyzer. Enter an Ethereum contract address and get a scored report combining security analysis, on-chain age, and ETH balance. Final score is 0–100 (higher = safer). Export as PDF.

## How it works

| Signal | Source | Score impact |
|---|---|---|
| Vulnerability findings | GoPlus (Streamlit Cloud) or Slither (Docker) | −25 critical, −15 high, −5 medium |
| Contract age | Binary search on-chain via Alchemy | +5 if older than 1 year |
| ETH held | Alchemy balance × CoinGecko price | +10 if >$1M |

## Deploying on Streamlit Community Cloud

1. Fork or push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Select your repo, branch `main`, main module **`interface.py`**
4. Under **Settings → Secrets**, add:
   ```toml
   NODE_API_URL = "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
   ETHERSCAN_API_KEY = "YOUR_KEY"
   ```
5. Deploy

On Streamlit Cloud, security analysis uses the **GoPlus Security API** (no native dependencies required). Contract age and ETH balance still use your Alchemy node.

## Running with Docker (full Slither analysis)

**Prerequisites:** Docker, Docker Compose

1. Copy the env template and fill in your keys:
   ```bash
   cp .env.example .env
   ```

2. Build and run:
   ```bash
   docker-compose up --build
   ```

3. Open `http://localhost:8501`.

In Docker mode, security analysis uses **Slither** (deeper analysis, 1–3 min per contract). The FastAPI backend is also available directly at `http://localhost:8000/risk-score/{address}`.

## Notes

- **GoPlus** only covers ERC-20 tokens. Protocol contracts, multisigs, etc. will show no security findings (score based on age and ETH balance only).
- **Slither** requires the contract source to be verified on Etherscan.
- ETH balance reflects native ETH only — ERC-20 tokens held by the contract are not counted.
