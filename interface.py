import streamlit as st
import requests
import pandas as pd
import json

# --- Configuration ---
FASTAPI_BASE_URL = "http://127.0.0.1:8000/risk-score"
DEFAULT_ADDRESS = "0x514910771AF9Ca6566aF840dFf83E8264EcF986CA" # LINK Token Address
# ---------------------

st.set_page_config(layout="wide")

st.title("🛡️ Smart Contract Security Risk Analyzer")
st.markdown("---")

# --- Input Section ---
address = st.text_input(
    "Enter Ethereum Contract Address:",
    DEFAULT_ADDRESS,
    key="contract_address"
)

# --- Analysis Function ---
def fetch_analysis(addr):
    """Fetches risk data from the running FastAPI backend."""
    url = f"{FASTAPI_BASE_URL}/{addr}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Connection Error: Could not connect to the FastAPI backend. Ensure your server is running on http://127.0.0.1:8000.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP Error: {e.response.status_code}. Check the address format or server logs.")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return None

# --- Display Logic ---
if st.button("Analyze Contract Risk"):
    if address:
        with st.spinner(f"Analyzing {address}..."):
            data = fetch_analysis(address)
            
            if data:
                st.subheader(f"Results for Contract: `{data['contract_address']}`")
                
                # --- A. Display Final Score ---
                score = data['final_score']
                score_color = 'green' if score >= 85 else ('orange' if score >= 60 else 'red')
                
                st.markdown(f"""
                <div style='background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center;'>
                    <h2 style='color: #262730;'>RISK SCORE:</h2>
                    <h1 style='color: {score_color}; font-size: 80px;'>{score} / 100</h1>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("---")

                # --- B. Key Data Metrics (Age & TVL) ---
                col1, col2, col3 = st.columns(3)
                
                # Column 1: Contract Age
                age_ts = data['age_data'].get('creation_date')
                age_display = 'N/A'
                if age_ts:
                    age_display = pd.to_datetime(age_ts, unit='s').strftime('%Y-%m-%d')
                
                with col1:
                    st.metric("Contract Creation Date", age_display)
                    st.metric("Creation Block", f"{data['age_data'].get('block_number', 'N/A'):,}")
                
                # Column 2: TVL Data
                tvl_usd = data['tvl_data'].get('tvl_usd', 0)
                tvl_status = data['tvl_data'].get('tvl_score_status', 'N/A')
                
                with col2:
                    st.metric("Total Value Locked (USD)", f"${tvl_usd:,.2f}")
                    st.metric("TVL Data Source", data['tvl_data'].get('tvl_source', 'N/A'))

                # --- C. Static Analysis Findings ---
                st.subheader("Vulnerability Analysis Findings (Simulated)")
                
                # Display Summary Table
                summary_data = {
                    'Impact': ['Critical', 'High', 'Medium', 'Low'],
                    'Count': [data['analysis_data']['critical'], data['analysis_data']['high'], data['analysis_data']['medium'], data['analysis_data']['low']]
                }
                st.table(pd.DataFrame(summary_data))
                
                # Display Detailed Findings List
                if data['analysis_data']['findings_list']:
                    df_findings = pd.DataFrame(data['analysis_data']['findings_list'])
                    st.dataframe(df_findings, use_container_width=True)
                else:
                    st.info("No detailed findings were returned by the analyzer.")