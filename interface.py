import os
import json
import streamlit as st
import requests
import pandas as pd

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000/risk-score")
DEFAULT_ADDRESS = "0x514910771AF9Ca6566aF840dFf83E8264EcF986CA"

st.set_page_config(layout="wide")
st.title("Smart Contract Security Risk Analyzer")
st.markdown("---")

address = st.text_input(
    "Enter Ethereum Contract Address:",
    DEFAULT_ADDRESS,
    key="contract_address",
)


def fetch_analysis(addr):
    url = f"{FASTAPI_BASE_URL}/{addr}"
    try:
        response = requests.get(url, timeout=240)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Connection Error: Could not reach the FastAPI backend. Is it running?")
        return None
    except requests.exceptions.Timeout:
        st.error("Request timed out — Slither analysis can take up to 3 minutes for complex contracts.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None


if st.button("Analyze Contract Risk"):
    if address:
        with st.spinner(f"Analyzing {address} — Slither analysis may take 1-3 minutes..."):
            data = fetch_analysis(address)

            if data:
                st.subheader(f"Results for: `{data['contract_address']}`")

                score = data["final_score"]
                score_color = "green" if score >= 85 else ("orange" if score >= 60 else "red")

                st.markdown(
                    f"""
                    <div style='background-color:#f0f2f6;padding:20px;border-radius:10px;text-align:center;'>
                        <h2 style='color:#262730;'>RISK SCORE</h2>
                        <h1 style='color:{score_color};font-size:80px;'>{score} / 100</h1>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown("---")

                col1, col2, col3 = st.columns(3)

                age_ts = data["age_data"].get("creation_date")
                age_display = pd.to_datetime(age_ts, unit="s").strftime("%Y-%m-%d") if age_ts else "N/A"
                block_num = data["age_data"].get("block_number", "N/A")

                with col1:
                    st.metric("Contract Creation Date", age_display)
                    st.metric("Creation Block", f"{block_num:,}" if isinstance(block_num, int) else block_num)

                tvl_usd = data["tvl_data"].get("tvl_usd", 0)
                eth_balance = data["tvl_data"].get("eth_balance")

                with col2:
                    st.metric("ETH Held by Contract", f"{eth_balance:,.4f} ETH" if eth_balance is not None else "N/A")
                    st.metric("ETH Value (USD)", f"${tvl_usd:,.2f}")

                analysis = data["analysis_data"]
                with col3:
                    st.metric("Critical findings", analysis.get("critical", 0))
                    st.metric("High findings", analysis.get("high", 0))

                st.markdown("---")
                st.subheader("Vulnerability Analysis Findings (Slither)")

                if analysis.get("error"):
                    st.warning(f"Analysis error: {analysis['error']}")
                else:
                    summary_df = pd.DataFrame({
                        "Impact": ["Critical", "High", "Medium", "Low"],
                        "Count": [
                            analysis.get("critical", 0),
                            analysis.get("high", 0),
                            analysis.get("medium", 0),
                            analysis.get("low", 0),
                        ],
                    })
                    st.table(summary_df)

                    findings_list = analysis.get("findings_list", [])
                    if findings_list:
                        st.dataframe(pd.DataFrame(findings_list), use_container_width=True)
                    else:
                        st.info("No vulnerabilities detected by Slither.")

                st.markdown("---")
                st.download_button(
                    label="Export full report as JSON",
                    data=json.dumps(data, indent=2),
                    file_name=f"risk_report_{data['contract_address'][:10]}.json",
                    mime="application/json",
                )
    else:
        st.warning("Please enter a contract address.")
