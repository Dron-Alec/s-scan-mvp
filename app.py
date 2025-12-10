import os
import subprocess
from fastapi import FastAPI, HTTPException
from web3 import Web3
from dotenv import load_dotenv
import requests
import json 
from slither.slither import Slither
from slither.exceptions import SlitherException

load_dotenv()

NODE_API_URL = os.getenv("NODE_API_URL")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

print(f"DEBUG: NODE_API_URL loaded: {NODE_API_URL}")
print(f"DEBUG: ETHERSCAN_API_KEY loaded: {ETHERSCAN_API_KEY}")

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

    # 1. Get Contract Age (Uses the Web3/Binary Search Logic)
    age_data = get_contract_age(checksum_address)

    # 2. Run Static Analysis (NEW CORE STEP)
    analysis_data = run_static_analysis(checksum_address)

    # 3. Get TVL (Placeholder)
    tvl_data = {"tvl_score": "Placeholder"}
    
    # 4. Score Calculation (MVP Rule-Based Logic)
    raw_score = 100
    
    # Simple risk penalties based on Slither findings:
    if not analysis_data.get("error"):
        raw_score -= int(analysis_data.get("critical", 0) * 25)
        raw_score -= int(analysis_data.get("high", 0) * 15)
        raw_score -= int(analysis_data.get("medium", 0) * 5)
    
    # Placeholder age bonus (to demonstrate scoring flexibility)
    # Age Bonus Calculation: Check if the contract is older than 1 year (31,536,000 seconds)
    if age_data.get("creation_date") and age_data["creation_date"] != None:
       current_timestamp = w3.eth.get_block("latest").timestamp
       age_in_seconds = current_timestamp - age_data["creation_date"]
       if age_in_seconds > 31536000: # Over 1 year old
        raw_score += 5 # Bonus for maturity

    # Ensure score doesn't go below zero
    final_score = max(0, raw_score)

    return {
        "contract_address": checksum_address,
        "age_data": age_data,
        "tvl_data": tvl_data,
        "analysis_data": analysis_data, # <-- NEW DATA FIELD
        "final_score": final_score
    }

#Define function to get the contract age
def get_contract_age(address: str) -> dict:
    """
    Finds contract creation block and timestamp using binary search 
    on the Alchemy/Web3 connection. Bypasses Etherscan entirely.
    """
    # Check if Web3 client is initialized and connected globally
    if not w3 or not w3.is_connected():
        return {"creation_date": None, "error": "Web3 client is not connected to node provider."}

    # Binary Search Parameters
    start_block = 0
    end_block = w3.eth.block_number
    creation_block = None

    try:
        # 1. Use binary search to find the block where the contract code first appeared
        while start_block <= end_block:
            mid_block = (start_block + end_block) // 2
            
            # Get contract code at the middle block number
            code = w3.eth.get_code(address, block_identifier=mid_block)
            
            if code and code != b'0x': # Contract code exists at this block
                creation_block = mid_block
                end_block = mid_block - 1 # Try to find an earlier block
            else:
                start_block = mid_block + 1 # Code does not exist yet, look later

        if creation_block:
            # 2. Once the creation block is found, get the timestamp
            block = w3.eth.get_block(creation_block)
            timestamp = int(block['timestamp'])

            return {
                "creation_date": timestamp,
                "block_number": creation_block
            }
        else:
            return {"creation_date": None, "error": "Contract code not found via binary search."}

    except Exception as e:
        return {"creation_date": None, "error": f"Web3 lookup failed: {str(e)}"}
    

def run_static_analysis(address: str) -> dict:
    """Runs the Slither static analysis tool on the contract address."""
    # Ensure the Etherscan API key is set for Slither to retrieve source code
    if not ETHERSCAN_API_KEY:
        return {"error": "Etherscan API Key is required for remote analysis.", "findings_list": []}

    # Temporarily set the Etherscan environment variable for Slither
    os.environ['ETHERSCAN_API_KEY'] = ETHERSCAN_API_KEY
    
    try:
        # Initialize Slither:
        # 1. Pass the address.
        # 2. Set the network to 'mainnet' (or 'ethereum').
        # 3. Pass the web3 object to allow Slither to use the node connection.
        # 4. Remove 'compiler' argument, as it's for local compilation.
        slither = Slither(
            address, 
            network = 'mainnet',
            etherscan_api_key='forge',
            web3 = w3 # Pass the initialized Web3 object
        ) 

        # Generate the analysis result object
        analysis_output = slither.generate_result()
        
        # Prepare the output structure
        findings = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings_list": []
        }

        # Iterate through Slither's detectors to summarize the findings
        for d in analysis_output.detectors:
            if d.result:
                # Loop through specific findings and count by impact
                for impact in ['high', 'medium', 'low', 'critical']:
                    if impact in d.result:
                        for vuln in d.result[impact]:
                            findings['findings_list'].append({
                                "description": vuln.description,
                                "impact": impact,
                                "detector": d.NAME
                            })
                            if impact in findings:
                                findings[impact] += 1
                            
        return findings

    except SlitherException as e:
        # This catches errors like 'Source code not verified' (common for old contracts)
        return {"error": f"Slither Analysis Failed: {str(e)}", "findings_list": []}
    except Exception as e:
        # Catch unexpected errors
        return {"error": f"Internal Slither Error: {str(e)}", "findings_list": []}
    finally:
        # IMPORTANT: Clean up the environment variable after use
        if 'ETHERSCAN_API_KEY' in os.environ:
             del os.environ['ETHERSCAN_API_KEY']