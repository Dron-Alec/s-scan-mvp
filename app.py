import os
from fastapi import FastAPI, HTTPException
from web3 import Web3
from dotenv import load_dotenv
import requests

NODE_API_URL = os.getenv("NODE_API_URL ")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

try:
    w3 = Web3(Web3.HTTPProvider(NODE_API_URL))
    if not w3.is_connected():
         raise ConnectionError("Web3 client could not connect to node provider.")
except Exception as e:
     print(f"Error initializing Web3: {e}")
     # If connection fails, API should not run properly
     w3 = None
# Initialize the FastAPI application
app = FastAPI()

# Define the root endpoint
@app.get("/risk-score/{address}")
def get_risk_data(address: str):
    # Ensure address is checksummed for consistency
    try:
        checksum_address = Web3.to_checksum_address(address)
    except:
        raise HTTPException(status_code=400, detail="Invalid Ethereum address format.")

    # 1. Get Contract Age
    age_data = get_contract_age(checksum_address)

    # 2. Get TVL (Placeholder)
    # This will be replaced with real logic later
    tvl_data = {"tvl_score": "Placeholder"}

    return {
        "contract_address": checksum_address,
        "age_data": age_data,
        "tvl_data": tvl_data,
        "raw_score": 100 # Initial score placeholder
    }

#Define function to get the contract age
def get_contract_age(address: str) -> dict:
    """Fetches contract creation time using Etherscan API."""
    if not ETHERSCAN_API_KEY:
        return {"creation_date": None, "block_number": None, "error": "Etherscan API key missing"}

    # Etherscan API URL for a specific contract's internal transactions
    etherscan_url = (
        f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999"
        f"&sort=asc&apikey={ETHERSCAN_API_KEY}"
    )

    response = requests.get(etherscan_url).json()

    if response['status'] == '1' and response['result']:
            # The first transaction in the list is the creation transaction (or earliest TX)
            first_tx = response['result'][0]

            # Creation timestamp (Unix time)
            timestamp = int(first_tx['timeStamp'])

            return {
                "creation_date": timestamp,
                "block_number": int(first_tx['blockNumber'])
            }
    else:
            return {"creation_date": None, "error": response.get('message', 'No transactions found or Etherscan error.')}
