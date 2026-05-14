import os
import datetime
import streamlit as st
import requests
import pandas as pd
from fpdf import FPDF

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000/risk-score")
DEFAULT_ADDRESS = "0x514910771AF9Ca6566aF840dFf83E8264EcF986CA"

st.set_page_config(layout="wide")
st.title("Smart Contract Security Score Analyzer")
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


def sanitize(text: str) -> str:
    """Strip characters outside Latin-1 so fpdf core fonts don't error."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf(data: dict) -> bytes:
    score = data["final_score"]
    address = data["contract_address"]
    analysis = data["analysis_data"]

    age_ts = data["age_data"].get("creation_date")
    age_display = pd.to_datetime(age_ts, unit="s").strftime("%Y-%m-%d") if age_ts else "N/A"
    block_num = data["age_data"].get("block_number", "N/A")
    eth_balance = data["tvl_data"].get("eth_balance")
    tvl_usd = data["tvl_data"].get("tvl_usd", 0)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Smart Contract Security Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True, align="C")
    pdf.ln(4)

    # Contract address
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 8, f"Contract: {address}", ln=True, fill=True)
    pdf.ln(4)

    # Score
    r, g, b = (0, 150, 0) if score >= 85 else ((255, 140, 0) if score >= 60 else (200, 0, 0))
    pdf.set_text_color(r, g, b)
    pdf.set_font("Helvetica", "B", 42)
    pdf.cell(0, 20, f"{score} / 100", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Security Score  (100 = safest)", ln=True, align="C")
    pdf.ln(8)

    # Key metrics
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Key Metrics", ln=True)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(2)

    metrics = [
        ("Creation Date", age_display),
        ("Creation Block", f"{block_num:,}" if isinstance(block_num, int) else str(block_num)),
        ("ETH Held", f"{eth_balance:,.4f} ETH" if eth_balance is not None else "N/A"),
        ("ETH Value (USD)", f"${tvl_usd:,.2f}"),
        ("TVL Source", data["tvl_data"].get("tvl_source", "N/A")),
    ]
    for label, value in metrics:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 7, label + ":", ln=False)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, sanitize(str(value)), ln=True)
    pdf.ln(6)

    # Slither summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Vulnerability Findings (Slither)", ln=True)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(2)

    if analysis.get("error"):
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, sanitize(f"Analysis error: {analysis['error']}"))
    else:
        # Summary table
        col_w = [80, 30]
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(col_w[0], 8, "Impact", border=1, fill=True)
        pdf.cell(col_w[1], 8, "Count", border=1, fill=True, ln=True)

        pdf.set_font("Helvetica", "", 10)
        for impact, key in [("Critical", "critical"), ("High", "high"), ("Medium", "medium"), ("Low / Informational", "low")]:
            pdf.cell(col_w[0], 7, impact, border=1)
            pdf.cell(col_w[1], 7, str(analysis.get(key, 0)), border=1, ln=True)

        pdf.ln(6)

        findings = analysis.get("findings_list", [])
        if findings:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "Detailed Findings", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(2)

            for i, f in enumerate(findings, 1):
                impact_label = f.get("impact", "").upper()
                detector = f.get("detector", "unknown")
                pdf.set_font("Helvetica", "B", 10)
                pdf.multi_cell(0, 6, sanitize(f"{i}. [{impact_label}] {detector}"))
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, sanitize(f.get("description", "")))
                pdf.ln(3)

    return bytes(pdf.output())


if st.button("Analyze Contract"):
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
                        <h2 style='color:#262730;'>SECURITY SCORE</h2>
                        <h1 style='color:{score_color};font-size:80px;'>{score} / 100</h1>
                        <p style='color:#555;'>Higher is safer</p>
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

                eth_balance = data["tvl_data"].get("eth_balance")
                tvl_usd = data["tvl_data"].get("tvl_usd", 0)

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
                pdf_bytes = generate_pdf(data)
                st.download_button(
                    label="Export report as PDF",
                    data=pdf_bytes,
                    file_name=f"security_report_{data['contract_address'][:10]}.pdf",
                    mime="application/pdf",
                )
    else:
        st.warning("Please enter a contract address.")
