import logging
import os
import subprocess
import json
import urllib.request
from fastapi import FastAPI, HTTPException
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NODE_API_URL = os.getenv("NODE_API_URL")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip() or None

w3 = None
try:
    w3 = Web3(Web3.HTTPProvider(NODE_API_URL))
    if not w3.is_connected():
        raise ConnectionError("Web3 client could not connect to node provider.")
    logger.info("Web3 connected successfully.")
except Exception as e:
    logger.error(f"Error initializing Web3: {e}")

app = FastAPI()


@app.get("/risk-score/{address}")
def get_risk_data(address: str):
    try:
        checksum_address = Web3.to_checksum_address(address)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Ethereum address format.")

    age_data = get_contract_age(checksum_address)
    analysis_data = get_combined_analysis(checksum_address)
    tvl_data = get_tvl_data(checksum_address)

    raw_score = 100
    if not analysis_data.get("error"):
        raw_score -= int(analysis_data.get("critical", 0) * 25)
        raw_score -= int(analysis_data.get("high", 0) * 15)
        raw_score -= int(analysis_data.get("medium", 0) * 5)

    return {
        "contract_address": checksum_address,
        "age_data": age_data,
        "tvl_data": tvl_data,
        "analysis_data": analysis_data,
        "final_score": max(0, raw_score),
    }


def get_contract_age(address: str) -> dict:
    if not w3 or not w3.is_connected():
        return {"creation_date": None, "error": "Web3 client is not connected."}

    start_block = 0
    end_block = w3.eth.block_number
    creation_block = None

    try:
        while start_block <= end_block:
            mid_block = (start_block + end_block) // 2
            code = w3.eth.get_code(address, block_identifier=mid_block)
            if code and code != b"0x":
                creation_block = mid_block
                end_block = mid_block - 1
            else:
                start_block = mid_block + 1

        if creation_block:
            block = w3.eth.get_block(creation_block)
            return {
                "creation_date": int(block["timestamp"]),
                "block_number": creation_block,
            }
        return {"creation_date": None, "error": "Contract code not found on chain."}

    except Exception as e:
        return {"creation_date": None, "error": f"Web3 lookup failed: {str(e)}"}


def run_slither(address: str) -> dict:
    empty = {"critical": 0, "high": 0, "medium": 0, "low": 0, "findings_list": []}

    if not ETHERSCAN_API_KEY:
        return {**empty, "error": "Etherscan API key not configured."}

    try:
        result = subprocess.run(
            ["slither", address, "--etherscan-apikey", ETHERSCAN_API_KEY, "--json", "-"],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "ETHERSCAN_API_KEY": ETHERSCAN_API_KEY},
        )

        if not result.stdout.strip():
            return {**empty, "error": f"Slither produced no output: {result.stderr.strip()[:500]}"}

        output = json.loads(result.stdout)

        if not output.get("success"):
            return {**empty, "error": output.get("error") or "Slither reported failure."}

        findings = {**empty}
        for d in output.get("results", {}).get("detectors", []):
            impact = d.get("impact", "Informational").lower()
            if impact == "critical":
                findings["critical"] += 1
            elif impact == "high":
                findings["high"] += 1
            elif impact == "medium":
                findings["medium"] += 1
            else:
                findings["low"] += 1
            findings["findings_list"].append({
                "description": d.get("description", "").strip(),
                "impact": impact,
                "detector": d.get("check", "unknown"),
                "source": "Slither",
            })

        return findings

    except subprocess.TimeoutExpired:
        return {**empty, "error": "Analysis timed out after 180s."}
    except json.JSONDecodeError as e:
        return {**empty, "error": f"Failed to parse Slither output: {e}"}
    except FileNotFoundError:
        return {**empty, "error": "slither not installed or not in PATH."}
    except Exception as e:
        return {**empty, "error": f"Analysis error: {str(e)}"}


def run_goplus(address: str) -> dict:
    empty = {"critical": 0, "high": 0, "medium": 0, "low": 0, "findings_list": []}
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/1?contract_addresses={address.lower()}"
        req = urllib.request.Request(url, headers={"User-Agent": "s-scan/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))

        if data.get("code") != 1:
            return {**empty, "error": f"GoPlus error: {data.get('message')}"}

        result = data.get("result", {}).get(address.lower())
        if not result:
            return {**empty, "error": "Contract not in GoPlus database."}

        findings = {**empty}
        checks = [
            ("is_honeypot",             "Honeypot: funds cannot be withdrawn",       "critical", False),
            ("selfdestruct",            "Contract has a self-destruct function",      "critical", False),
            ("can_take_back_ownership", "Owner can reclaim contract ownership",       "high",     False),
            ("hidden_owner",            "Contract has a hidden owner",               "high",     False),
            ("is_open_source",          "Source code is not verified/open source",   "high",     True),
            ("transfer_pausable",       "Owner can pause all transfers",             "medium",   False),
            ("is_mintable",             "Owner can mint unlimited tokens",           "medium",   False),
            ("is_proxy",                "Proxy contract (upgradeable)",              "medium",   False),
            ("is_blacklisted",          "Contract uses a blacklist",                 "low",      False),
            ("is_whitelisted",          "Contract uses a whitelist",                 "low",      False),
        ]

        for flag, description, impact, inverted in checks:
            val = result.get(flag, "0")
            is_bad = (val == "0") if inverted else (val == "1")
            if is_bad:
                findings[impact] += 1
                findings["findings_list"].append({
                    "description": description,
                    "impact": impact,
                    "detector": flag,
                    "source": "GoPlus",
                })

        return findings

    except Exception as e:
        return {**empty, "error": str(e)}


def get_combined_analysis(address: str) -> dict:
    slither = run_slither(address)
    goplus = run_goplus(address)

    combined = {
        "critical": slither.get("critical", 0) + goplus.get("critical", 0),
        "high":     slither.get("high", 0)     + goplus.get("high", 0),
        "medium":   slither.get("medium", 0)   + goplus.get("medium", 0),
        "low":      slither.get("low", 0)      + goplus.get("low", 0),
        "findings_list": slither.get("findings_list", []) + goplus.get("findings_list", []),
        "source": "Slither + GoPlus",
    }

    if slither.get("error"):
        combined["slither_error"] = slither["error"]
    if goplus.get("error"):
        combined["goplus_error"] = goplus["error"]

    return combined


def get_tvl_data(address: str) -> dict:
    if not w3 or not w3.is_connected():
        return {
            "tvl_source": "N/A",
            "tvl_usd": 0,
            "eth_balance": None,
            "tvl_score_status": "Web3 not connected.",
        }

    try:
        eth_balance = w3.eth.get_balance(address) / 1e18

        cg_url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
        with urllib.request.urlopen(urllib.request.Request(cg_url), timeout=10) as r:
            price_data = json.loads(r.read().decode("utf-8"))

        eth_price = price_data.get("ethereum", {}).get("usd", 0)

        return {
            "tvl_source": "Alchemy (balance) × CoinGecko (price)",
            "tvl_usd": eth_balance * eth_price,
            "eth_balance": eth_balance,
            "tvl_score_status": "success",
        }

    except Exception as e:
        logger.error(f"TVL lookup failed: {e}")
        return {
            "tvl_source": "API Error",
            "tvl_usd": 0,
            "eth_balance": None,
            "tvl_score_status": f"Error: {str(e)}",
        }
