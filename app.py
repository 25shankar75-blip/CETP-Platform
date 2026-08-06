import streamlit as st
import numpy as np
import pandas as pd
import json
import gc
import requests

from schemas import CURRENCY_MULTIPLIERS
from physics_engine import expand_24_to_8760
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin Platform", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; } .metric-row { background-color: #f1f3f5; padding: 10px; border-radius: 8px; margin-bottom: 20px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_live_currency(base_dict):
    try:
        url = "https://open.er-api.com/v6/latest/INR"
        resp = requests.get(url, timeout=3).json()
        if resp.get("result") == "success":
            rates = resp["rates"]
            base_dict["USD ($)"]["rate"] = rates.get("USD", base_dict["USD ($)"]["rate"])
            base_dict["EUR (€)"]["rate"] = rates.get("EUR", base_dict["EUR (€)"]["rate"])
            base_dict["AED (د.إ)"]["rate"] = rates.get("AED", base_dict["AED (د.إ)"]["rate"])
            base_dict["MYR (RM)"]["rate"] = rates.get("MYR", base_dict["MYR (RM)"]["rate"])
    except: pass
    return base_dict

CURRENCIES = fetch_live_currency(CURRENCY_MULTIPLIERS)

# Mondelez Default Profile Initialization
MONDELEZ_LOAD = [431.0]*6 + [976.0]*3 + [431.0]*2 + [976.0]*10 + [431.0]*3
MONDELEZ_TARIFF = [5.62]*6 + [11.26]*3 + [9.02]*2 + [11.26]*10 + [5.62]*3

ui_keys = {
    "proj_name": "Mondelez Industrial Retrofit", "location": "Pune, Maharashtra, India", "industry": "FMCG", "proj_type": "Brownfield / Retrofit", 
    "tank_shape": "Cylindrical", "tes_strategy": "Partial Storage", "currency": "INR (₹)", "chiller_type": "Water-Cooled", 
    "chiller_module_tr": 1000.0, "design_wbt": 28.0, "use_live_weather": True, "use_coolprop": True,
    "chw_supply": 7.0, "chw_return": 12.0, "brine_supply": -5.5, "brine_return": -2.1, "kw_tr_base": 0.60, "kw_tr_brine": 0.85, 
    "chw_pump_kw": 0.078, "cw_pump_kw": 0.030, "ct_fan_kw": 0.020, "brine_pump_kw": 0.020, 
    "ext_chw_flow": 477.0, "ext_chw_sup": 5.2, "ext_chw_ret": 7.6, "ext_chw_head": 40.0,
    "ext_cw_flow": 739.0, "ext_cw_sup": 32.0, "ext_cw_ret": 35.0, "ext_cw_head": 35.0,
    "ext_ct_fan_kw": 21.0, "ext_kw_tr_base": 0.85,
    "operating_days": 325, "dg_outage_hrs": 2.5, "dg_tariff": 28.0, "demand_rate": 475.0, "water_cost_kl": 25.0, 
    "grid_emission": 0.727, "evap_loss": 1.8, "rate_water_chiller": 19000.0, "rate_air_chiller": 21000.0, "rate_brine_chiller": 23000.0, 
    "rate_pcm_cyl": 7800.0, "rate_pcm_rect": 8500.0, "rate_strat_tes": 18000.0, "rate_ct": 3200.0, "rate_chw_pump": 900.0, 
    "rate_cw_pump": 650.0, "rate_brine_pump": 900.0, "rate_phe_int": 1500.0, "rate_dg": 11000.0, "rate_transformer": 1700.0, 
    "run_sim": False
}

for k, v in ui_keys.items():
    if k not in st.session_state: st.session_state[k] = v

def reset_sim(): st.session_state.run_sim = False

st.sidebar.header("🛠️ Input Master Suite")
nav_selection = st.sidebar.radio("Navigation Menu", ["📌 1. Project Details & Scope", "⚙️ 2. 24-Hr Load Profile", "🌡️ 3. Chiller Array & Audit", "💰 4. Financial CAPEX Rates", "⚡ 5. Water & Electrical Data"], on_change=reset_sim)

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Run Iterative Optimization", type="primary"): st.session_state.run_sim = True
if st.session_state.run_sim:
    if st.sidebar.button("🔙 Return to Inputs"): reset_sim()

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Project Management")
uploaded_json = st.sidebar.file_uploader("📂 Open Existing Project (.json)", type="json")
if uploaded_json is not None:
    try:
        data = json.load(uploaded_json)
        for k in ui_keys.keys():
            if k in data: st.session_state[k] = data[k]
        if "df_24" in data: st.session_state["df_24"] = pd.DataFrame(data["df_24"])
        if "df_chillers" in data: st.session_state["df_chillers"] = pd.DataFrame(data["df_chillers"])
        st.sidebar.success("Project Loaded!")
    except: st.sidebar.error("Invalid file.")

save_dict = {k: st.session_state[k] for k in ui_keys.keys()}
if "df_24" in st.session_state: save_dict["df_24"] = st.session_state["df_24"].to_dict(orient="records")
if "df_chillers" in st.session_state: save_dict["df_chillers"] = st.session_state["df_chillers"].to_dict(orient="records")
st.sidebar.download_button("💾 Save Project State", json.dumps(save_dict), file_name="cetp_project.json", mime="application/json")

sym = CURRENCIES[st.session_state.currency]["symbol"]
mult = CURRENCIES[st.session_state.currency]["rate"]

if "df_24" not in st.session_state:
    st.session_state["df_24"] = pd.DataFrame({
        "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": MONDELEZ_LOAD,
        f"Tariff ({sym})": [t*mult for t in MONDELEZ_TARIFF]
    })

if "df_chillers" not in st.session_state:
    default_chillers = [{"Capacity (TR)": 1000.0, "Quantity": 1, "Type": "Water-Cooled"}]
    for _ in range(9): default_chillers.append({"Capacity (TR)": 0.0, "Quantity": 0, "Type": "Water-Cooled"})
    st.session_state["df_chillers"] = pd.DataFrame(default_chillers)

# --- MAIN SCREEN LOGIC ---
if not st.session_state.run_sim:
    if nav_selection == "📌 1. Project Details & Scope":
        st.subheader("📌 Project Details & Scope Configuration")
        with st.form("project_form"):
            col1, col2 = st.columns(2)
            with col1:
                p_name = st.text_input("Project Name", value=st.session_state.proj_name)
                p_loc = st.text_input("Location (For Weather API)", value=st.session_state.location