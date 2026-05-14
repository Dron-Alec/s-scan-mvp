# s-scan-mvp

Smart contract security score analyzer. Enter an Ethereum contract address and get a scored report combining security analysis, on-chain age, ETH balance, and transaction activity. Final score is 0–100 (higher = safer, 100 = no detectable red flags).

<img width="1472" height="670" alt="Screenshot 2026-05-14 at 10 57 09 AM" src="https://github.com/user-attachments/assets/01cc9531-9d49-4c8f-8b65-38f5c1edbecf" />
<img width="1398" height="494" alt="Screenshot 2026-05-14 at 10 59 40 AM" src="https://github.com/user-attachments/assets/a3fd33f4-637c-4bde-82a2-96ddfcdb4545" />


## How it works

| Signal | Source | Score impact |
|---|---|---|
| Vulnerability findings | GoPlus (Streamlit Cloud) or Slither (Docker) | −25 critical, −15 high, −5 medium |
| Contract age | Binary search on-chain via Alchemy | display only |
| ETH held | Alchemy balance × CoinGecko price | display only |
| Transaction activity | Etherscan (last 30 days) | display only |

## Test addresses

| Address | Contract | What to expect |
|---|---|---|
| `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` | WETH | High ETH balance (~3M ETH), old (2017), few flags — good baseline |
| `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | USDC | Proxy flag (upgradeable by Circle) |
| `0x514910771AF9Ca6566aF840dFf83E8264EcF986CA` | LINK | Clean token, default address |
| `0xdAC17F958D2ee523a2206206994597C13D831ec7` | USDT | Demonstrates ETH balance limitation — token contracts hold $0 ETH |
| Any new/small ERC-20 | Unknown token | Most likely to surface real GoPlus flags (honeypot, mintable, hidden owner) |

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

On Streamlit Cloud, security analysis uses the **GoPlus Security API** (no native dependencies required).

## Running with Docker (full Slither analysis)

**Prerequisites:** Docker, Docker Compose

```bash
cp .env.example .env   # fill in your keys
docker-compose up --build
```

Open `http://localhost:8501`. The Docker setup runs both GoPlus and Slither and merges their findings. The FastAPI backend is also queryable directly at `http://localhost:8000/risk-score/{address}`.

## Known limitations

- **Score means absence of detected flags, not safety.** A score of 100 means no red flags were found — not that the contract is safe. Economic exploits, oracle manipulation, and logic bugs are outside the scope of this tool.
- **GoPlus only covers ERC-20 tokens.** Protocol contracts, multisigs, and non-token contracts return no GoPlus data.
- **ETH balance ≠ TVL for token contracts.** USDT, USDC, and most ERC-20s hold near-zero ETH — their value is tracked internally, not as ETH.
- **Slither requires verified source code.** Contracts without Etherscan-verified source will fail Slither analysis but still score on GoPlus flags.
