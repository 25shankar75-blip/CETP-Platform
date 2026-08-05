# app.py
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
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
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

DEFAULT_LOAD = [1047.816]*8 + [1746.36]*2 + [2095.632]*4 + [2794.176]*4 + [2444.904]*2 + [2095.632]*2 + [1397.088]*2
DEFAULT_TARIFF = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2

ui_keys = {
    "proj_name": "Example Pharma Project", "location": "Ujjain, MP, India", "industry": "Pharmaceuticals", "proj_type": "Greenfield Project", 
    "tank_shape": "Cylindrical", "tes_strategy": "Partial Storage", "currency": "INR (₹)", "chiller_type": "Water-Cooled", 
    "chiller_module_tr": 700.0, "design_wbt": 28.0, "use_live_weather": True, "use_coolprop": True,
    "chw_supply": 7.0, "chw_return": 12.0, "brine_supply": -5.0, "brine_return": -1.7, "kw_tr_base": 0.58, "kw_tr_brine": 0.85, 
    "chw_pump_kw": 0.078, "cw_pump_kw": 0.030, "ct_fan_kw": 0.020, "brine_pump_kw": 0.020, 
    "ext_chw_flow": 450.0, "ext_chw_sup": 9.0, "ext_chw_ret": 14.0, "ext_chw_head": 35.0,
    "ext_cw_flow": 550.0, "ext_cw_sup": 32.0, "ext_cw_ret": 37.0, "ext_cw_head": 25.0,
    "ext_ct_fan_kw": 45.0, "ext_chiller_kw_tr": 0.85,
    "operating_days": 325, "dg_outage_hrs": 2.5, "dg_tariff": 28.0, "demand_rate": 475.0, "water_cost_kl": 25.0, 
    "grid_emission": 0.716, "evap_loss": 1.8, "rate_water_chiller": 19000.0, "rate_air_chiller": 21000.0, "rate_brine_chiller": 23000.0, 
    "rate_pcm_cyl": 7800.0, "rate_pcm_rect": 8500.0, "rate_strat_tes": 18000.0, "rate_ct": 3200.0, "rate_chw_pump": 900.0, 
    "rate_cw_pump": 650.0, "rate_brine_pump": 900.0, "rate_phe_int": 1500.0, "rate_dg": 11000.0, "rate_transformer": 1700.0, 
    "run_sim": False, "retrofit_blanked": False
}

for k, v in ui_keys.items():
    if k not in st.session_state: st.session_state[k] = v

def reset_sim(): st.session_state.run_sim = False

st.sidebar.header("🛠️ Input Master Suite")
nav_selection = st.sidebar.radio("Navigation Menu", ["📌 1. Project Details & Scope", "⚙️ 2. 24-Hr Load Profile", "🌡️ 3. Chiller & Retrofit Audit", "💰 4. Financial CAPEX Rates", "⚡ 5. Water & Electrical Data"], on_change=reset_sim)

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Run Digital Twin Optimization", type="primary"): st.session_state.run_sim = True
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
        st.sidebar.success("Project Loaded!")
    except: st.sidebar.error("Invalid file.")

save_dict = {k: st.session_state[k] for k in ui_keys.keys()}
if "df_24" in st.session_state: save_dict["df_24"] = st.session_state["df_24"].to_dict(orient="records")
st.sidebar.download_button("💾 Save Project State", json.dumps(save_dict), file_name="cetp_project.json", mime="application/json")

sym = CURRENCIES[st.session_state.currency]["symbol"]
mult = CURRENCIES[st.session_state.currency]["rate"]

if "df_24" not in st.session_state:
    st.session_state["df_24"] = pd.DataFrame({
        "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": DEFAULT_LOAD,
        f"Tariff ({sym})": [t*mult for t in DEFAULT_TARIFF]
    })

# Retrofit Conditional Blanking
if st.session_state.proj_type == "Brownfield / Retrofit" and not st.session_state.retrofit_blanked:
    st.session_state["df_24"]["Load (TR)"] = 0.0
    st.session_state["df_24"][f"Tariff ({sym})"] = 0.0
    st.session_state.retrofit_blanked = True
elif st.session_state.proj_type == "Greenfield Project":
    st.session_state.retrofit_blanked = False

# --- MAIN SCREEN LOGIC ---
if not st.session_state.run_sim:
    if nav_selection == "📌 1. Project Details & Scope":
        st.subheader("📌 Project Details & API Integrations")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.proj_name = st.text_input("Project Name", value=st.session_state.proj_name)
            st.session_state.location = st.text_input("Location (For Weather API)", value=st.session_state.location)
            industries = ["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"]
            st.session_state.industry = st.selectbox("Industry Sector", industries, index=industries.index(st.session_state.industry))
            currencies_list = list(CURRENCIES.keys())
            st.session_state.currency = st.selectbox("Currency Unit", currencies_list, index=currencies_list.index(st.session_state.currency))
            st.markdown("---")
            st.session_state.use_live_weather = st.checkbox("📡 Enable Live Open-Meteo Weather API (8760 WBT)", value=st.session_state.use_live_weather)
            st.session_state.use_coolprop = st.checkbox("⚗️ Enable CoolProp Thermodynamic Fluid Analysis", value=st.session_state.use_coolprop)
            
        with col2:
            st.session_state.proj_type = st.radio("Project Scope", ["Greenfield Project", "Brownfield / Retrofit"], index=0 if st.session_state.proj_type == "Greenfield Project" else 1)
            st.session_state.tes_strategy = st.selectbox("TES Strategy", ["Partial Storage", "Full Storage", "Demand Limiting"], index=["Partial Storage", "Full Storage", "Demand Limiting"].index(st.session_state.tes_strategy))
            st.session_state.tank_shape = st.selectbox("Tank Geometry", ["Cylindrical", "Rectangular"], index=["Cylindrical", "Rectangular"].index(st.session_state.tank_shape))

    elif nav_selection == "⚙️ 2. 24-Hr Load Profile":
        st.subheader("⚙️ Hourly Load & Tariff Input")
        st.info("Edit Load and Tariff cells once. The % column is reactive and prevents scroll overlap.")
        
        # State-isolated Data Editor (Fixes Infinite Loop & Double Entry)
        df_display = st.session_state["df_24"].copy()
        curr_peak = df_display["Load (TR)"].max()
        df_display["Load (%)"] = (df_display["Load (TR)"] / curr_peak * 100) if curr_peak > 0 else 0.0
        
        edited = st.data_editor(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Hour": st.column_config.TextColumn("Hour", disabled=True, width="small"),
                "Load (TR)": st.column_config.NumberColumn("Load (TR)", format="%.1f", min_value=0.0, width="medium"),
                "Load (%)": st.column_config.NumberColumn("Load (%)", format="%.1f %%", disabled=True, width="small"),
                f"Tariff ({sym})": st.column_config.NumberColumn(f"Tariff ({sym})", format="%.2f", min_value=0.0, width="medium")
            }
        )
        st.session_state["df_24"]["Load (TR)"] = edited["Load (TR)"]
        st.session_state["df_24"][f"Tariff ({sym})"] = edited[f"Tariff ({sym})"]
            
        st.markdown("---")
        st.markdown("##### Calculated Operational Displays")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Peak Load (TR)", f"{st.session_state['df_24']['Load (TR)'].max():.1f}")
        c2.metric("Avg Load (TR)", f"{st.session_state['df_24']['Load (TR)'].mean():.1f}")
        c3.metric("Daily Load (TRh)", f"{st.session_state['df_24']['Load (TR)'].sum():.1f}")
        c4.metric("Annual Load (TRh)", f"{st.session_state['df_24']['Load (TR)'].sum()*st.session_state.operating_days:.1f}")

    elif nav_selection == "🌡️ 3. Chiller & Retrofit Audit":
        if "Brownfield" in st.session_state.proj_type:
            st.markdown("### 🔍 Current Plant Audit (Low Delta-T Syndrome Diagnostics)")
            st.error("Enter the real-time operational data of your existing inefficient plant. The platform will dynamically calculate your true running TR and auxiliary kW to establish a realistic baseline OPEX.")
            
            c_a1, c_a2, c_a3 = st.columns(3)
            st.session_state.ext_chiller_kw_tr = c_a1.number_input("Existing Chiller Operation (kW/TR)", value=st.session_state.ext_chiller_kw_tr)
            st.session_state.ext_ct_fan_kw = c_a2.number_input("Existing CT Fan Operation (kW)", value=st.session_state.ext_ct_fan_kw)
            
            st.markdown("##### 💧 Hydraulic Auditing")
            c_h1, c_h2 = st.columns(2)
            with c_h1:
                st.markdown("**Primary CHW Circuit**")
                st.session_state.ext_chw_flow = st.number_input("Running CHW Flow (m³/hr)", value=st.session_state.ext_chw_flow)
                st.session_state.ext_chw_sup = st.number_input("Running CHW Supply Temp (°C)", value=st.session_state.ext_chw_sup)
                st.session_state.ext_chw_ret = st.number_input("Running CHW Return Temp (°C)", value=st.session_state.ext_chw_ret)
                st.session_state.ext_chw_head = st.number_input("Running CHW Pump Head (m)", value=st.session_state.ext_chw_head)
            with c_h2:
                st.markdown("**Condenser CW Circuit**")
                st.session_state.ext_cw_flow = st.number_input("Running CW Flow (m³/hr)", value=st.session_state.ext_cw_flow)
                st.session_state.ext_cw_sup = st.number_input("Running CW Entering Temp (°C)", value=st.session_state.ext_cw_sup)
                st.session_state.ext_cw_ret = st.number_input("Running CW Leaving Temp (°C)", value=st.session_state.ext_cw_ret)
                st.session_state.ext_cw_head = st.number_input("Running CW Pump Head (m)", value=st.session_state.ext_cw_head)
                
            # Dynamic Diagnostic Math
            ext_chw_tr = (st.session_state.ext_chw_flow * 1000 / 3600) * 4.18 * (st.session_state.ext_chw_ret - st.session_state.ext_chw_sup) / 3.517
            ext_chw_pump_kw = (st.session_state.ext_chw_flow / 3600) * st.session_state.ext_chw_head * 9.81 * 1000 / 0.70 / 1000
            ext_cw_pump_kw = (st.session_state.ext_cw_flow / 3600) * st.session_state.ext_cw_head * 9.81 * 1000 / 0.70 / 1000
            
            st.session_state.ext_chw_pump_kw_tr = ext_chw_pump_kw / ext_chw_tr if ext_chw_tr > 0 else 0.12
            st.session_state.ext_cw_pump_kw_tr = ext_cw_pump_kw / ext_chw_tr if ext_chw_tr > 0 else 0.05
            st.session_state.ext_ct_fan_kw_tr = st.session_state.ext_ct_fan_kw / ext_chw_tr if ext_chw_tr > 0 else 0.035

            st.markdown("##### 📊 Real-Time Diagnostic Results")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Actual Cooling Delivered", f"{ext_chw_tr:.0f} TR")
            r2.metric("Actual CHW Pump Index", f"{st.session_state.ext_chw_pump_kw_tr:.3f} kW/TR")
            r3.metric("Actual CW Pump Index", f"{st.session_state.ext_cw_pump_kw_tr:.3f} kW/TR")
            r4.metric("Actual CT Fan Index", f"{st.session_state.ext_ct_fan_kw_tr:.3f} kW/TR")
            
            st.markdown("---")
            st.markdown("### ✨ Optimized Design State (For TES Charging & Restoration)")
        else:
            st.markdown("### 🌡️ Base Chiller & Auxiliary Parameters")
            
        c1, c2 = st.columns(2)
        st.session_state.chiller_type = c1.selectbox("Chiller Type", ["Water-Cooled", "Air-Cooled"], index=0 if st.session_state.chiller_type == "Water-Cooled" else 1)
        st.session_state.chiller_module_tr = c2.number_input("Standard Chiller Module Size (TR)", value=st.session_state.chiller_module_tr)
        
        st.session_state.chw_supply = c1.number_input("Design CHW Supply Temp (°C)", value=st.session_state.chw_supply)
        st.session_state.brine_supply = c1.number_input("Design Brine Supply Temp (°C)", value=st.session_state.brine_supply)
        st.session_state.kw_tr_base = c1.number_input("Design Full Load Base Chiller (kW/TR)", value=st.session_state.kw_tr_base)
        st.session_state.design_wbt = c1.number_input("Design WBT (°C) for Efficiency Baseline", value=st.session_state.design_wbt)
        
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design CHW Pump Power (kW/TR)</span>", unsafe_allow_html=True)
        st.session_state.chw_pump_kw = c1.number_input("chw_pump", value=st.session_state.chw_pump_kw, label_visibility="collapsed")
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design CT Fan Power (kW/TR)</span>", unsafe_allow_html=True)
        st.session_state.ct_fan_kw = c1.number_input("ct_fan", value=st.session_state.ct_fan_kw, label_visibility="collapsed")
        
        st.session_state.chw_return = c2.number_input("Design CHW Return Temp (°C)", value=st.session_state.chw_return)
        st.session_state.brine_return = c2.number_input("Design Brine Return Temp (°C)", value=st.session_state.brine_return)
        st.session_state.kw_tr_brine = c2.number_input("Brine Chiller Full Load (kW/TR)", value=st.session_state.kw_tr_brine)
        
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design Condenser Water Pump Power (kW/TR)</span>", unsafe_allow_html=True)
        st.session_state.cw_pump_kw = c2.number_input("cw_pump", value=st.session_state.cw_pump_kw, label_visibility="collapsed")
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design Brine Pump Power (kW/TR)</span>", unsafe_allow_html=True)
        st.session_state.brine_pump_kw = c2.number_input("brine_pump", value=st.session_state.brine_pump_kw, label_visibility="collapsed")

    elif nav_selection == "💰 4. Financial CAPEX Rates":
        st.subheader(f"💰 Financial Base Rates ({sym})")
        st.session_state.demand_rate = st.number_input(f"Monthly Demand Charge (per kVA)", value=st.session_state.demand_rate)
        c1, c2 = st.columns(2)
        st.session_state.rate_water_chiller = c1.number_input("Water-Cooled Chiller Rate (/TR)", value=st.session_state.rate_water_chiller)
        st.session_state.rate_brine_chiller = c1.number_input("Brine Chiller Rate (/TR)", value=st.session_state.rate_brine_chiller)
        st.session_state.rate_pcm_cyl = c1.number_input("PCM Tank Cylindrical Rate (/TRh)", value=st.session_state.rate_pcm_cyl)
        st.session_state.rate_strat_tes = c1.number_input("Stratified Tank Rate (/TRh)", value=st.session_state.rate_strat_tes)
        st.session_state.rate_chw_pump = c1.number_input("CHW Pump Rate (/TR)", value=st.session_state.rate_chw_pump)
        st.session_state.rate_phe_int = c1.number_input("Plate Heat Exchanger Rate (/TR)", value=st.session_state.rate_phe_int)
        
        st.session_state.rate_air_chiller = c2.number_input("Air-Cooled Chiller Rate (/TR)", value=st.session_state.rate_air_chiller)
        st.session_state.rate_ct = c2.number_input("Cooling Tower Rate (/TR)", value=st.session_state.rate_ct)
        st.session_state.rate_pcm_rect = c2.number_input("PCM Tank Rectangular Rate (/TRh)", value=st.session_state.rate_pcm_rect)
        st.session_state.rate_dg = c2.number_input("DG Set Rate (/kVA)", value=st.session_state.rate_dg)
        st.session_state.rate_cw_pump = c2.number_input("CDW Pump Rate (/TR)", value=st.session_state.rate_cw_pump)
        st.session_state.rate_transformer = c2.number_input("Transformer Rate (/kVA)", value=st.session_state.rate_transformer)

    elif nav_selection == "⚡ 5. Water & Electrical Data":
        st.subheader("⚡ Water, Electrical & DG Blackout Parameters")
        c1, c2 = st.columns(2)
        st.session_state.operating_days = c1.number_input("Annual Operating Days", value=st.session_state.operating_days)
        st.session_state.water_cost_kl = c1.number_input("Water Cost (per kL)", value=st.session_state.water_cost_kl)
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Evaporation Loss (L/TRh) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.evap_loss = c1.number_input("evap_loss", value=st.session_state.evap_loss, label_visibility="collapsed")
        
        c2.markdown("### 🔌 Diesel Generator (DG) Analysis")
        st.session_state.dg_outage_hrs = c2.number_input("Avg Daily Power Outage (Hrs/Day)", value=st.session_state.dg_outage_hrs)
        st.session_state.dg_tariff = c2.number_input("DG Generation Tariff (per kWh)", value=st.session_state.dg_tariff)
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Grid Emission Factor (kg CO₂/kWh) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.grid_emission = c2.number_input("grid_emission", value=st.session_state.grid_emission, label_visibility="collapsed")

else:
    t1, t2, t3, t4, t5, t6, t7 = st.tabs(["Load Profile", "Conv. Plant", "PCM TES Opt.", "Strat. TES Opt.", "Exec. Summary", "CAPEX Breakup", "Report Dashboard"])
    
    rates = {
        'water_cooled_chiller': st.session_state.rate_water_chiller*mult, 'air_cooled_chiller': st.session_state.rate_air_chiller*mult, 
        'brine_chiller': st.session_state.rate_brine_chiller*mult, 'pcm_cylindrical': st.session_state.rate_pcm_cyl*mult, 
        'pcm_rectangular': st.session_state.rate_pcm_rect*mult, 'strat_tes': st.session_state.rate_strat_tes*mult, 
        'cooling_tower': st.session_state.rate_ct*mult, 'chw_pump': st.session_state.rate_chw_pump*mult, 
        'cdw_pump': st.session_state.rate_cw_pump*mult, 'brine_pump': st.session_state.rate_brine_pump*mult, 
        'phe': st.session_state.rate_phe_int*mult, 'dg_set': st.session_state.rate_dg*mult, 'transformer': st.session_state.rate_transformer*mult
    }
    
    prm = {
        "location": st.session_state.location, "design_wbt": st.session_state.design_wbt, "use_live_weather": st.session_state.use_live_weather, "use_coolprop": st.session_state.use_coolprop,
        "chw_supply": st.session_state.chw_supply, "chw_return": st.session_state.chw_return, "brine_supply": st.session_state.brine_supply, 
        "brine_return": st.session_state.brine_return, "kw_tr_base": st.session_state.kw_tr_base, "kw_tr_brine": st.session_state.kw_tr_brine, 
        "chw_pump_kw": st.session_state.chw_pump_kw, "cw_pump_kw": st.session_state.cw_pump_kw, "ct_fan_kw": st.session_state.ct_fan_kw, 
        "brine_pump_kw": st.session_state.brine_pump_kw, "evap_loss": st.session_state.evap_loss, "water_cost_kl": st.session_state.water_cost_kl*mult,
        "grid_emission": st.session_state.grid_emission, 'unit_rates': rates, 'chiller_type': st.session_state.chiller_type, 'chiller_module_tr': st.session_state.chiller_module_tr,
        'tank_shape': st.session_state.tank_shape, 'demand_rate': st.session_state.demand_rate*mult, "indirects_pct": 0.30, "maintenance_pct": 0.02,
        'operating_days': st.session_state.operating_days, 'dg_outage_hrs': st.session_state.dg_outage_hrs, 'dg_tariff': st.session_state.dg_tariff*mult
    }
    
    audit_prm = prm.copy()
    if "Brownfield" in st.session_state.proj_type:
        audit_prm.update({
            "kw_tr_base": st.session_state.get('ext_chiller_kw_tr', 0.85),
            "chw_pump_kw": st.session_state.get('ext_chw_pump_kw_tr', 0.12),
            "cw_pump_kw": st.session_state.get('ext_cw_pump_kw_tr', 0.05),
            "ct_fan_kw": st.session_state.get('ext_ct_fan_kw_tr', 0.035)
        })
    
    load_arr = st.session_state["df_24"]["Load (TR)"].tolist()
    tar_arr = st.session_state["df_24"][f"Tariff ({sym})"].tolist()
    charge_hrs = {22, 23, 0, 1, 2, 3, 4, 5}
    calc_peak = max(load_arr)
    
    with st.spinner("Fetching Weather Data & Executing Mathematical Optimization..."):
        res = optimize_plant(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), calc_peak, charge_hrs, prm, audit_prm, st.session_state.proj_type)
    
    def render_detailed_hourly_table(data_dict):
        df_detailed = pd.DataFrame({
            "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": load_arr[:24], f"Tariff ({sym})": data_dict['data']['tariff'][:24],
            "Charge (TR)": data_dict['data']['charge'][:24], "Discharge (TR)": data_dict['data']['discharge'][:24], 
            "Base Chiller (kW)": data_dict['data']['kw_comp'][:24], "Brine Chiller (kW)": data_dict['data']['kw_brine'][:24], 
            "CHW Pump (kW)": data_dict['data']['kw_chw'][:24], "CDW Pump (kW)": data_dict['data']['kw_cw'][:24], 
            "CT Fan (kW)": data_dict['data']['kw_fan'][:24], "Total Sys (kW)": data_dict['data']['total_kw'][:24]
        })
        st.dataframe(df_detailed.style.format(precision=1), use_container_width=True, hide_index=True)

    with t1:
        st.subheader("Hourly Load & Tariff Profile")
        st.dataframe(st.session_state["df_24"], use_container_width=True, hide_index=True)

    with t2:
        st.subheader("Conventional Chiller Plant (N+1 Baseline)")
        if "Brownfield" in st.session_state.proj_type: st.warning("⚠️ Using Existing Plant Audit Parameters for Baseline OPEX.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Installed Base Chillers", f"{res['c']['cap_base']:,.0f} TR")
        c2.metric("Peak Electrical Demand", f"{res['c']['dem']:,.1f} kW")
        c3.metric("Required Substation & DG", f"{res['c']['dg_kva']:,.0f} kVA")
        c4.metric("Total Annual OPEX", format_currency(res['c']['tot_op'], st.session_state.currency))
        st.markdown("##### Hourly Load Management & Equipment Power (kW)")
        render_detailed_hourly_table(res['c'])

    with t3:
        st.subheader("PCM Thermal Energy Storage (Optimum)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Downsized Base Chillers", f"{res['p']['cap_base']:,.0f} TR", f"{res['p']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
        c2.metric("Sub-Zero Brine Chillers", f"{res['p']['cap_dual']:,.0f} TR")
        c3.metric("PCM Storage Volume", f"{res['p']['cap_tes']:,.0f} TRh")
        c4.metric("Required Substation & DG", f"{res['p']['dg_kva']:,.0f} kVA", f"{res['p']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Peak Electrical Demand", f"{res['p']['dem']:,.1f} kW", f"{res['p']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
        c6.metric("Daily Peak Discharge", f"{sum(res['p']['data']['discharge'][:24]):,.0f} TRh")
        c7.metric("Total Annual OPEX", format_currency(res['p']['tot_op'], st.session_state.currency), f"- {format_currency(res['c']['tot_op'] - res['p']['tot_op'], st.session_state.currency)}")
        c8.metric("Simple Payback", f"{res['p']['pb']:.2f} Years" if res['p']['pb']>0 else "Instantaneous")
        st.markdown("##### Hourly Load Management & Equipment Power (kW)")
        render_detailed_hourly_table(res['p'])

    with t4:
        st.subheader("Stratified CHW Thermal Storage (Optimum)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Downsized Base Chillers", f"{res['s']['cap_base']:,.0f} TR", f"{res['s']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
        c2.metric("Sub-Zero Brine Chillers", "0 TR")
        c3.metric("Stratified Storage Volume", f"{res['s']['cap_tes']:,.0f} TRh")
        c4.metric("Required Substation & DG", f"{res['s']['dg_kva']:,.0f} kVA", f"{res['s']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Peak Electrical Demand", f"{res['s']['dem']:,.1f} kW", f"{res['s']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
        c6.metric("Daily Peak Discharge", f"{sum(res['s']['data']['discharge'][:24]):,.0f} TRh")
        c7.metric("Total Annual OPEX", format_currency(res['s']['tot_op'], st.session_state.currency), f"- {format_currency(res['c']['tot_op'] - res['s']['tot_op'], st.session_state.currency)}")
        c8.metric("Simple Payback", f"{res['s']['pb']:.2f} Years" if res['s']['pb']>0 else "Instantaneous")
        st.markdown("##### Hourly Load Management & Equipment Power (kW)")
        render_detailed_hourly_table(res['s'])

    df_comp = pd.DataFrame({
        "Parameter": ["Installed Chiller (TR)", "TES Capacity (TRh)", "Peak Demand (kW)", "Transformer (kVA)", "Electricity Cons. (kWh)", "Electricity Cost", "Water Cons. (kL)", "Water Cost", "Carbon Emissions (kgCO2)", "Annual Maint. Cost", "Annual DG OPEX", "Total Annual OPEX", "Annual DG Savings", "Total Annual Savings", "Incremental CAPEX", "Simple Payback (Yrs)"],
        "Conventional N+1": [
            f"{res['c']['cap_base']:,.0f}", "0", f"{res['c']['dem']:,.0f}", f"{res['c']['dg_kva']:,.0f}", f"{res['c']['data']['energy_kwh']:,.0f}", 
            format_currency(res['c']['data']['energy_cost'], st.session_state.currency), f"{res['c']['data']['water_kl']:,.0f}", format_currency(res['c']['data']['water_cost'], st.session_state.currency), 
            f"{res['c']['data']['emissions']*1000:,.0f}", format_currency(res['c']['maint'], st.session_state.currency), format_currency(res['c']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['c']['tot_op'], st.session_state.currency), 
            "Baseline", "Baseline", format_currency(res['c']['capex'], st.session_state.currency), "Baseline"
        ],
        "PCM TES Opt.": [
            f"{res['p']['cap_base'] + res['p']['cap_dual']:,.0f}", f"{res['p']['cap_tes']:,.0f}", f"{res['p']['dem']:,.0f}", f"{res['p']['dg_kva']:,.0f}", f"{res['p']['data']['energy_kwh']:,.0f}", 
            format_currency(res['p']['data']['energy_cost'], st.session_state.currency), f"{res['p']['data']['water_kl']:,.0f}", format_currency(res['p']['data']['water_cost'], st.session_state.currency), 
            f"{res['p']['data']['emissions']*1000:,.0f}", format_currency(res['p']['maint'], st.session_state.currency), format_currency(res['p']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['p']['tot_op'], st.session_state.currency), 
            format_currency(res['p']['dg_sav'], st.session_state.currency), format_currency(res['p']['sav'], st.session_state.currency), format_currency(res['p']['inc_cap'], st.session_state.currency), f"{res['p']['pb']:.2f}"
        ],
        "Strat. TES Opt.": [
            f"{res['s']['cap_base']:,.0f}", f"{res['s']['cap_tes']:,.0f}", f"{res['s']['dem']:,.0f}", f"{res['s']['dg_kva']:,.0f}", f"{res['s']['data']['energy_kwh']:,.0f}", 
            format_currency(res['s']['data']['energy_cost'], st.session_state.currency), f"{res['s']['data']['water_kl']:,.0f}", format_currency(res['s']['data']['water_cost'], st.session_state.currency), 
            f"{res['s']['data']['emissions']*1000:,.0f}", format_currency(res['s']['maint'], st.session_state.currency), format_currency(res['s']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['s']['tot_op'], st.session_state.currency), 
            format_currency(res['s']['dg_sav'], st.session_state.currency), format_currency(res['s']['sav'], st.session_state.currency), format_currency(res['s']['inc_cap'], st.session_state.currency), f"{res['s']['pb']:.2f}"
        ]
    })

    with t5:
        st.subheader("📊 Executive Summary")
        st.table(df_comp)

    with t6:
        st.subheader("💰 Master CAPEX Breakdown")
        df_bk = pd.DataFrame({
            "Category": list(res['c']['bk'].keys()),
            "Conventional N+1": [format_currency(v, st.session_state.currency) for v in res['c']['bk'].values()],
            "PCM TES Opt.": [format_currency(v, st.session_state.currency) for v in res['p']['bk'].values()],
            "Strat. TES Opt.": [format_currency(v, st.session_state.currency) for v in res['s']['bk'].values()]
        })
        st.table(df_bk)

    with t7:
        st.subheader("📑 Report Dashboard & Export")
        c1, c2 = st.columns(2)
        with c1:
            pdf = generate_pdf_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp, load_arr[:24], tar_arr[:24], res, sym)
            st.download_button("📥 Export High-Def PDF Report", data=pdf, file_name=f"CETP_Report_{st.session_state.proj_name}.pdf", mime="application/pdf", use_container_width=True)
        with c2:
            doc = generate_word_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp, load_arr[:24], tar_arr[:24], res, sym)
            if doc: st.download_button("📝 Export Editable Word Document (.docx)", data=doc, file_name=f"CETP_Report_{st.session_state.proj_name}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    gc.collect()