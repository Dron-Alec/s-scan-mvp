import os
import datetime
import json
import urllib.request
import streamlit as st
import pandas as pd
from fpdf import FPDF
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(layout="wide")


def _secret(key):
    """Read from Streamlit secrets (cloud) or environment variables (local/Docker)."""
    try:
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key)


NODE_API_URL = _secret("NODE_API_URL")
FASTAPI_BASE_URL = _secret("FASTAPI_BASE_URL")  # set in Docker, absent on Streamlit Cloud
DEFAULT_ADDRESS = "0x514910771AF9Ca6566aF840dFf83E8264EcF986CA"


@st.cache_resource
def init_web3():
    if not NODE_API_URL:
        return None
    try:
        w3 = Web3(Web3.HTTPProvider(NODE_API_URL))
        return w3 if w3.is_connected() else None
    except Exception:
        return None


# ── Data functions (standalone / Streamlit Cloud mode) ────────────────────────

def get_contract_age(address: str) -> dict:
    w3 = init_web3()
    if not w3:
        return {"creation_date": None, "error": "Web3 not connected."}

    start_block, end_block, creation_block = 0, w3.eth.block_number, None
    try:
        while start_block <= end_block:
            mid = (start_block + end_block) // 2
            code = w3.eth.get_code(address, block_identifier=mid)
            if code and code != b"0x":
                creation_block = mid
                end_block = mid - 1
            else:
                start_block = mid + 1

        if creation_block:
            block = w3.eth.get_block(creation_block)
            return {"creation_date": int(block["timestamp"]), "block_number": creation_block}
        return {"creation_date": None, "error": "Contract not found on chain."}
    except Exception as e:
        return {"creation_date": None, "error": str(e)}


def run_security_analysis(address: str) -> dict:
    """GoPlus Security API — no native dependencies, works on Streamlit Cloud."""
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
            return {**empty, "error": "Contract not in GoPlus database (protocol/non-token contracts may return no data)."}

        findings = {**empty, "source": "GoPlus Security API"}

        # (flag, description, impact, inverted)
        # inverted=True means flag value "0" is the bad state (e.g. not open source)
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
                })

        for key in ("owner_address", "creator_address", "holder_count"):
            if result.get(key):
                findings[key] = result[key]

        return findings

    except Exception as e:
        return {**empty, "error": str(e)}


def get_tvl_data(address: str) -> dict:
    w3 = init_web3()
    if not w3:
        return {"tvl_source": "N/A", "tvl_usd": 0, "eth_balance": None, "tvl_score_status": "Web3 not connected."}
    try:
        eth_balance = w3.eth.get_balance(address) / 1e18
        cg_url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
        with urllib.request.urlopen(urllib.request.Request(cg_url), timeout=10) as r:
            eth_price = json.loads(r.read().decode("utf-8")).get("ethereum", {}).get("usd", 0)
        return {
            "tvl_source": "Alchemy × CoinGecko",
            "tvl_usd": eth_balance * eth_price,
            "eth_balance": eth_balance,
            "tvl_score_status": "success",
        }
    except Exception as e:
        return {"tvl_source": "Error", "tvl_usd": 0, "eth_balance": None, "tvl_score_status": str(e)}


def compute_score(age_data: dict, analysis_data: dict, tvl_data: dict) -> int:
    raw = 100
    if not analysis_data.get("error"):
        raw -= analysis_data.get("critical", 0) * 25
        raw -= analysis_data.get("high", 0) * 15
        raw -= analysis_data.get("medium", 0) * 5

    w3 = init_web3()
    if w3 and age_data.get("creation_date") is not None:
        if w3.eth.get_block("latest").timestamp - age_data["creation_date"] > 31_536_000:
            raw += 5

    if tvl_data.get("tvl_usd", 0) > 1_000_000:
        raw += 10

    return min(100, max(0, raw))


def fetch_direct(address: str) -> dict:
    """Full analysis without a backend — used on Streamlit Cloud."""
    age = get_contract_age(address)
    analysis = run_security_analysis(address)
    tvl = get_tvl_data(address)
    return {
        "contract_address": address,
        "age_data": age,
        "tvl_data": tvl,
        "analysis_data": analysis,
        "final_score": compute_score(age, analysis, tvl),
    }


def fetch_from_backend(address: str):
    """Calls FastAPI backend (Docker mode — includes Slither analysis)."""
    import requests as req_lib
    try:
        r = req_lib.get(f"{FASTAPI_BASE_URL}/{address}", timeout=240)
        r.raise_for_status()
        return r.json()
    except req_lib.exceptions.ConnectionError:
        st.error("Cannot reach FastAPI backend.")
    except req_lib.exceptions.Timeout:
        st.error("Request timed out.")
    except Exception as e:
        st.error(f"Error: {e}")
    return None


# ── PDF generation ─────────────────────────────────────────────────────────────

def sanitize(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf(data: dict) -> bytes:
    score = data["final_score"]
    analysis = data["analysis_data"]
    age_ts = data["age_data"].get("creation_date")
    age_display = pd.to_datetime(age_ts, unit="s").strftime("%Y-%m-%d") if age_ts else "N/A"
    block_num = data["age_data"].get("block_number", "N/A")
    eth_balance = data["tvl_data"].get("eth_balance")
    tvl_usd = data["tvl_data"].get("tvl_usd", 0)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Smart Contract Security Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True, align="C")
    pdf.ln(4)

    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 8, f"Contract: {data['contract_address']}", ln=True, fill=True)
    pdf.ln(4)

    r, g, b = (0, 150, 0) if score >= 85 else ((255, 140, 0) if score >= 60 else (200, 0, 0))
    pdf.set_text_color(r, g, b)
    pdf.set_font("Helvetica", "B", 42)
    pdf.cell(0, 20, f"{score} / 100", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Security Score  (100 = safest)", ln=True, align="C")
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Key Metrics", ln=True)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(2)
    for label, value in [
        ("Creation Date",    age_display),
        ("Creation Block",   f"{block_num:,}" if isinstance(block_num, int) else str(block_num)),
        ("ETH Held",         f"{eth_balance:,.4f} ETH" if eth_balance is not None else "N/A"),
        ("ETH Value (USD)",  f"${tvl_usd:,.2f}"),
    ]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 7, label + ":", ln=False)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, sanitize(str(value)), ln=True)
    pdf.ln(6)

    source_label = sanitize(analysis.get("source", "Security Analysis"))
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Vulnerability Findings ({source_label})", ln=True)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(2)

    if analysis.get("error"):
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, sanitize(f"Note: {analysis['error']}"))
    else:
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(80, 8, "Impact", border=1, fill=True)
        pdf.cell(30, 8, "Count", border=1, fill=True, ln=True)
        pdf.set_font("Helvetica", "", 10)
        for impact, key in [("Critical", "critical"), ("High", "high"), ("Medium", "medium"), ("Low", "low")]:
            pdf.cell(80, 7, impact, border=1)
            pdf.cell(30, 7, str(analysis.get(key, 0)), border=1, ln=True)
        pdf.ln(6)

        findings = analysis.get("findings_list", [])
        if findings:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, "Detailed Findings", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(2)
            for i, f in enumerate(findings, 1):
                pdf.set_font("Helvetica", "B", 10)
                pdf.multi_cell(0, 6, sanitize(f"{i}. [{f.get('impact','').upper()}] {f.get('detector','')}"))
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, sanitize(f.get("description", "")))
                pdf.ln(3)

    return bytes(pdf.output())


# ── UI ─────────────────────────────────────────────────────────────────────────

st.title("Smart Contract Security Score Analyzer")
st.caption(
    "Mode: Docker backend (Slither)" if FASTAPI_BASE_URL
    else "Mode: Streamlit Cloud (GoPlus Security API)"
)
st.markdown("---")

address = st.text_input("Enter Ethereum Contract Address:", DEFAULT_ADDRESS)

if st.button("Analyze Contract"):
    if not address:
        st.warning("Please enter a contract address.")
    else:
        with st.spinner("Analyzing — this may take a minute..."):
            data = fetch_from_backend(address) if FASTAPI_BASE_URL else fetch_direct(address)

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
            source_label = analysis.get("source", "Security Analysis")
            st.subheader(f"Vulnerability Findings ({source_label})")

            if analysis.get("error"):
                st.warning(f"Note: {analysis['error']}")
            else:
                st.table(pd.DataFrame({
                    "Impact": ["Critical", "High", "Medium", "Low"],
                    "Count": [
                        analysis.get("critical", 0), analysis.get("high", 0),
                        analysis.get("medium", 0),   analysis.get("low", 0),
                    ],
                }))
                findings_list = analysis.get("findings_list", [])
                if findings_list:
                    st.dataframe(pd.DataFrame(findings_list), use_container_width=True)
                else:
                    st.info("No vulnerabilities detected.")

            st.markdown("---")
            st.download_button(
                label="Export report as PDF",
                data=generate_pdf(data),
                file_name=f"security_report_{data['contract_address'][:10]}.pdf",
                mime="application/pdf",
            )
