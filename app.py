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
                p_loc = st.text_input("Location (For Weather API)", value=st.session_state.location)
                industries = ["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"]
                p_ind = st.selectbox("Industry Sector", industries, index=industries.index(st.session_state.industry))
                currencies_list = list(CURRENCIES.keys())
                p_cur = st.selectbox("Currency Unit", currencies_list, index=currencies_list.index(st.session_state.currency))
                st.markdown("---")
                p_wea = st.checkbox("📡 Enable Live Open-Meteo Weather API (8760 WBT)", value=st.session_state.use_live_weather)
                p_cool = st.checkbox("⚗️ Enable CoolProp Thermodynamic Fluid Analysis", value=st.session_state.use_coolprop)
                
            with col2:
                p_scope = st.radio("Project Scope", ["Greenfield Project", "Brownfield / Retrofit"], index=0 if st.session_state.proj_type == "Greenfield Project" else 1)
                p_strat = st.selectbox("TES Strategy", ["Partial Storage", "Full Storage", "Demand Limiting"], index=["Partial Storage", "Full Storage", "Demand Limiting"].index(st.session_state.tes_strategy))
                p_shape = st.selectbox("Tank Geometry", ["Cylindrical", "Rectangular"], index=["Cylindrical", "Rectangular"].index(st.session_state.tank_shape))
            
            if st.form_submit_button("Save Project Details"):
                st.session_state.update({"proj_name": p_name, "location": p_loc, "industry": p_ind, "currency": p_cur, "use_live_weather": p_wea, "use_coolprop": p_cool, "proj_type": p_scope, "tes_strategy": p_strat, "tank_shape": p_shape})
                st.success("Project Details Locked & Saved!")

    elif nav_selection == "⚙️ 2. 24-Hr Load Profile":
        st.subheader("⚙️ Hourly Load & Tariff Input")
        st.info("Input your Load and Tariff Profile. Reactive metrics have been moved to Output tabs to guarantee stability. Press 'Save' below to lock in values.")
        
        with st.form("load_profile_form"):
            df_display = st.session_state["df_24"][["Hour", "Load (TR)", f"Tariff ({sym})"]].copy()
            edited = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Hour": st.column_config.TextColumn("Hour", disabled=True, width="small"),
                    "Load (TR)": st.column_config.NumberColumn("Load (TR)", format="%.1f", min_value=0.0, width="medium"),
                    f"Tariff ({sym})": st.column_config.NumberColumn(f"Tariff ({sym})", format="%.2f", min_value=0.0, width="medium")
                }
            )
            if st.form_submit_button("Save Load Profile Data"):
                st.session_state["df_24"]["Load (TR)"] = edited["Load (TR)"]
                st.session_state["df_24"][f"Tariff ({sym})"] = edited[f"Tariff ({sym})"]
                st.success("Load Profile Locked & Saved!")

    elif nav_selection == "🌡️ 3. Chiller Array & Audit":
        with st.form("chiller_audit_form"):
            st.markdown("### 🧊 Central Chiller Equipment Array")
            st.info("Enter the configuration of existing (Retrofit) or proposed (Greenfield) chillers.")
            
            edited_chillers = st.data_editor(
                st.session_state["df_chillers"],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Capacity (TR)": st.column_config.NumberColumn("Capacity (TR)", format="%.1f", min_value=0.0),
                    "Quantity": st.column_config.NumberColumn("Quantity", min_value=0, step=1),
                    "Type": st.column_config.SelectboxColumn("Chiller Type", options=["Water-Cooled", "Air-Cooled"])
                }
            )
            
            if "Brownfield" in st.session_state.proj_type:
                st.markdown("---")
                st.markdown("### 🔍 Current Plant Audit (Low Delta-T Syndrome Diagnostics)")
                st.error("Enter real-time operational data. The platform calculates true running TR and auxiliary kW to establish a realistic baseline OPEX.")
                
                c_a1, c_a2, c_a3 = st.columns(3)
                v_ch_kw = c_a1.number_input("Existing Chiller Operation (kW/TR)", value=st.session_state.ext_kw_tr_base)
                v_ct_fan = c_a2.number_input("Existing CT Fan Operation (kW)", value=st.session_state.ext_ct_fan_kw)
                
                st.markdown("##### 💧 Hydraulic Auditing")
                c_h1, c_h2 = st.columns(2)
                with c_h1:
                    st.markdown("**Primary CHW Circuit**")
                    v_chw_f = st.number_input("Running CHW Flow (m³/hr)", value=st.session_state.ext_chw_flow)
                    v_chw_s = st.number_input("Running CHW Supply Temp (°C)", value=st.session_state.ext_chw_sup)
                    v_chw_r = st.number_input("Running CHW Return Temp (°C)", value=st.session_state.ext_chw_ret)
                    v_chw_h = st.number_input("Running CHW Pump Head (m)", value=st.session_state.ext_chw_head)
                with c_h2:
                    st.markdown("**Condenser CW Circuit**")
                    v_cw_f = st.number_input("Running CW Flow (m³/hr)", value=st.session_state.ext_cw_flow)
                    v_cw_s = st.number_input("Running CW Entering Temp (°C)", value=st.session_state.ext_cw_sup)
                    v_cw_r = st.number_input("Running CW Leaving Temp (°C)", value=st.session_state.ext_cw_ret)
                    v_cw_h = st.number_input("Running CW Pump Head (m)", value=st.session_state.ext_cw_head)
                
                st.markdown("---")
                st.markdown("### ✨ Optimized Design State (For TES Charging & Restoration)")
            else:
                st.markdown("---")
                st.markdown("### 🌡️ Optimized Design State Parameters")
                v_ch_kw = st.session_state.ext_kw_tr_base
                v_ct_fan = st.session_state.ext_ct_fan_kw
                v_chw_f, v_chw_s, v_chw_r, v_chw_h = st.session_state.ext_chw_flow, st.session_state.ext_chw_sup, st.session_state.ext_chw_ret, st.session_state.ext_chw_head
                v_cw_f, v_cw_s, v_cw_r, v_cw_h = st.session_state.ext_cw_flow, st.session_state.ext_cw_sup, st.session_state.ext_cw_ret, st.session_state.ext_cw_head

            c1, c2 = st.columns(2)
            d_chw_s = c1.number_input("Design CHW Supply Temp (°C)", value=st.session_state.chw_supply)
            d_brine_s = c1.number_input("Design Brine Supply Temp (°C)", value=st.session_state.brine_supply)
            d_kw_base = c1.number_input("Design Full Load Base Chiller (kW/TR)", value=st.session_state.kw_tr_base)
            d_wbt = c1.number_input("Design WBT (°C) for Efficiency Baseline", value=st.session_state.design_wbt)
            
            c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design CHW Pump Power (kW/TR)</span>", unsafe_allow_html=True)
            d_chw_kw = c1.number_input("chw_pump", value=st.session_state.chw_pump_kw, label_visibility="collapsed")
            c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design CT Fan Power (kW/TR)</span>", unsafe_allow_html=True)
            d_ct_kw = c1.number_input("ct_fan", value=st.session_state.ct_fan_kw, label_visibility="collapsed")
            
            d_chw_r = c2.number_input("Design CHW Return Temp (°C)", value=st.session_state.chw_return)
            d_brine_r = c2.number_input("Design Brine Return Temp (°C)", value=st.session_state.brine_return)
            d_kw_brine = c2.number_input("Brine Chiller Full Load (kW/TR)", value=st.session_state.kw_tr_brine)
            
            c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design Condenser Water Pump Power (kW/TR)</span>", unsafe_allow_html=True)
            d_cw_kw = c2.number_input("cw_pump", value=st.session_state.cw_pump_kw, label_visibility="collapsed")
            c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Design Brine Pump Power (kW/TR)</span>", unsafe_allow_html=True)
            d_br_kw = c2.number_input("brine_pump", value=st.session_state.brine_pump_kw, label_visibility="collapsed")
            
            if st.form_submit_button("Save Chiller & Audit Parameters"):
                st.session_state["df_chillers"] = edited_chillers
                st.session_state.update({
                    "ext_kw_tr_base": v_ch_kw, "ext_ct_fan_kw": v_ct_fan, "ext_chw_flow": v_chw_f, "ext_chw_sup": v_chw_s, "ext_chw_ret": v_chw_r, "ext_chw_head": v_chw_h,
                    "ext_cw_flow": v_cw_f, "ext_cw_sup": v_cw_s, "ext_cw_ret": v_cw_r, "ext_cw_head": v_cw_h, 
                    "chw_supply": d_chw_s, "brine_supply": d_brine_s, "kw_tr_base": d_kw_base, "design_wbt": d_wbt,
                    "chw_pump_kw": d_chw_kw, "ct_fan_kw": d_ct_kw, "chw_return": d_chw_r, "brine_return": d_brine_r, "kw_tr_brine": d_kw_brine, "cw_pump_kw": d_cw_kw, "brine_pump_kw": d_br_kw
                })
                st.success("Chiller Matrix & Audit Parameters Saved!")

    elif nav_selection == "💰 4. Financial CAPEX Rates":
        st.subheader(f"💰 Financial Base Rates ({sym})")
        with st.form("financial_form"):
            f_dem = st.number_input(f"Monthly Demand Charge (per kVA)", value=st.session_state.demand_rate)
            c1, c2 = st.columns(2)
            f_wc = c1.number_input("Water-Cooled Chiller Rate (/TR)", value=st.session_state.rate_water_chiller)
            f_bc = c1.number_input("Brine Chiller Rate (/TR)", value=st.session_state.rate_brine_chiller)
            f_pcm_c = c1.number_input("PCM Tank Cylindrical Rate (/TRh)", value=st.session_state.rate_pcm_cyl)
            f_strat = c1.number_input("Stratified Tank Rate (/TRh)", value=st.session_state.rate_strat_tes)
            f_chw_p = c1.number_input("CHW Pump Rate (/TR)", value=st.session_state.rate_chw_pump)
            f_phe = c1.number_input("Plate Heat Exchanger Rate (/TR)", value=st.session_state.rate_phe_int)
            
            f_ac = c2.number_input("Air-Cooled Chiller Rate (/TR)", value=st.session_state.rate_air_chiller)
            f_ct = c2.number_input("Cooling Tower Rate (/TR)", value=st.session_state.rate_ct)
            f_pcm_r = c2.number_input("PCM Tank Rectangular Rate (/TRh)", value=st.session_state.rate_pcm_rect)
            f_dg = c2.number_input("DG Set Rate (/kVA)", value=st.session_state.rate_dg)
            f_cw_p = c2.number_input("CDW Pump Rate (/TR)", value=st.session_state.rate_cw_pump)
            f_tr = c2.number_input("Transformer Rate (/kVA)", value=st.session_state.rate_transformer)
            
            if st.form_submit_button("Save Financial Rates"):
                st.session_state.update({"demand_rate": f_dem, "rate_water_chiller": f_wc, "rate_brine_chiller": f_bc, "rate_pcm_cyl": f_pcm_c, "rate_strat_tes": f_strat, "rate_chw_pump": f_chw_p, "rate_phe_int": f_phe, "rate_air_chiller": f_ac, "rate_ct": f_ct, "rate_pcm_rect": f_pcm_r, "rate_dg": f_dg, "rate_cw_pump": f_cw_p, "rate_transformer": f_tr})
                st.success("Financial Rates Saved!")

    elif nav_selection == "⚡ 5. Water & Electrical Data":
        st.subheader("⚡ Water, Electrical & DG Blackout Parameters")
        with st.form("water_elec_form"):
            c1, c2 = st.columns(2)
            w_op = c1.number_input("Annual Operating Days", value=st.session_state.operating_days)
            w_cost = c1.number_input("Water Cost (per kL)", value=st.session_state.water_cost_kl)
            c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Evaporation Loss (L/TRh) [Standard Base]</span>", unsafe_allow_html=True)
            w_evap = c1.number_input("evap_loss", value=st.session_state.evap_loss, label_visibility="collapsed")
            
            c2.markdown("### 🔌 Diesel Generator (DG) Analysis")
            w_dg_hr = c2.number_input("Avg Daily Power Outage (Hrs/Day)", value=st.session_state.dg_outage_hrs)
            w_dg_tar = c2.number_input("DG Generation Tariff (per kWh)", value=st.session_state.dg_tariff)
            c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Grid Emission Factor (kg CO₂/kWh) [Standard Base]</span>", unsafe_allow_html=True)
            w_grid = c2.number_input("grid_emission", value=st.session_state.grid_emission, label_visibility="collapsed")
            
            if st.form_submit_button("Save Operational Parameters"):
                st.session_state.update({"operating_days": w_op, "water_cost_kl": w_cost, "evap_loss": w_evap, "dg_outage_hrs": w_dg_hr, "dg_tariff": w_dg_tar, "grid_emission": w_grid})
                st.success("Operational Parameters Saved!")

else:
    # --- OUTPUT EXECUTION ---
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
        'tank_shape': st.session_state.tank_shape, 'demand_rate': st.session_state.demand_rate*mult, "indirects_pct": 0.30, "maintenance_pct": 0.015,
        'operating_days': st.session_state.operating_days, 'dg_outage_hrs': st.session_state.dg_outage_hrs, 'dg_tariff': st.session_state.dg_tariff*mult
    }
    
    # Calculate Array Installed Capacity
    installed_chiller_tr = sum(row['Capacity (TR)'] * row['Quantity'] for _, row in st.session_state["df_chillers"].iterrows())
    
    audit_prm = prm.copy()
    if "Brownfield" in st.session_state.proj_type:
        ext_chw_tr = (st.session_state.ext_chw_flow * 1000 / 3600) * 4.18 * (st.session_state.ext_chw_ret - st.session_state.ext_chw_sup) / 3.517
        ext_chw_pump_kw = (st.session_state.ext_chw_flow / 3600) * st.session_state.ext_chw_head * 9.81 * 1000 / 0.70 / 1000
        ext_cw_pump_kw = (st.session_state.ext_cw_flow / 3600) * st.session_state.ext_cw_head * 9.81 * 1000 / 0.70 / 1000
        
        audit_prm.update({
            "kw_tr_base": st.session_state.ext_kw_tr_base,
            "chw_pump_kw": ext_chw_pump_kw / ext_chw_tr if ext_chw_tr > 0 else 0.12,
            "cw_pump_kw": ext_cw_pump_kw / ext_chw_tr if ext_chw_tr > 0 else 0.05,
            "ct_fan_kw": st.session_state.ext_ct_fan_kw / ext_chw_tr if ext_chw_tr > 0 else 0.035
        })
    
    load_arr = st.session_state["df_24"]["Load (TR)"].tolist()
    tar_arr = st.session_state["df_24"][f"Tariff ({sym})"].tolist()
    calc_peak = max(load_arr)
    
    with st.spinner("Executing Iterative Backend Permutation Optimization..."):
        res = optimize_plant(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), installed_chiller_tr, prm, audit_prm, st.session_state.proj_type)
    
    # UI Top Bar Metrics
    st.markdown(f'<div class="metric-row"><b>Profile Metrics:</b> Peak TR: {calc_peak:,.1f} &nbsp;&nbsp;|&nbsp;&nbsp; Avg TR: {np.mean(load_arr):,.1f} &nbsp;&nbsp;|&nbsp;&nbsp; Daily Load: {np.sum(load_arr):,.0f} TRh</div>', unsafe_allow_html=True)
    
    def render_detailed_hourly_table(data_dict):
        df_detailed = pd.DataFrame({
            "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": load_arr[:24], f"Tariff ({sym})": data_dict['data']['tariff'][:24],
            "Charge (TR)": data_dict['data']['charge'][:24], "Discharge (TR)": data_dict['data']['discharge'][:24], 
            "Base Chiller (kW)": data_dict['data']['kw_comp'][:24], "Brine Chiller (kW)": data_dict['data']['kw_brine'][:24], 
            "CHW Pump (kW)": data_dict['data']['kw_chw'][:24], "CDW Pump (kW)": data_dict['data']['kw_cw'][:24], 
            "CT Fan (kW)": data_dict['data']['kw_fan'][:24], "Total Sys (kW)": data_dict['data']['total_kw'][:24]
        })
        st.dataframe(df_detailed.style.format(precision=1), use_container_width=True, hide_index=True)

    t1, t2, t3, t4, t5 = st.tabs(["Conv. Plant", "PCM TES Opt.", "Strat. TES Opt.", "Exec. Summary", "Report Dashboard"])

    with t1:
        st.subheader("Conventional Chiller Plant (N+1 Baseline)")
        if "Brownfield" in st.session_state.proj_type: st.warning("⚠️ Using Existing Plant Audit Parameters for Baseline OPEX.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Installed Base Chillers", f"{res['c']['cap_base']:,.0f} TR")
        c2.metric("Peak Electrical Demand", f"{res['c']['dem']:,.1f} kW")
        c3.metric("Required Substation & DG", f"{res['c']['dg_kva']:,.0f} kVA")
        c4.metric("Total Annual OPEX", format_currency(res['c']['tot_op'], st.session_state.currency))
        st.markdown("##### Hourly Load Management & Equipment Power (kW)")
        render_detailed_hourly_table(res['c'])

    with t2:
        st.subheader("PCM Thermal Energy Storage (Iterative Optimum)")
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

    with t3:
        st.subheader("Stratified CHW Thermal Storage (Iterative Optimum)")
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
        "Parameter": ["Installed Chiller (TR)", "TES Capacity (TRh)", "Peak Demand (kW)", "Transformer (kVA)", "Electricity Cons. (kWh)", "Electricity Cost", "Water Cons. (kL)", "Water Cost", "Carbon Emissions (kgCO2)", "Annual Mech. AMC", "Annual DG OPEX", "Total Annual OPEX", "Annual DG Savings", "Total Annual Savings", "Total CAPEX", "Incremental CAPEX", "Simple Payback (Yrs)"],
        "Conventional N+1": [
            f"{res['c']['cap_base']:,.0f}", "0", f"{res['c']['dem']:,.0f}", f"{res['c']['dg_kva']:,.0f}", f"{res['c']['data']['energy_kwh']:,.0f}", 
            format_currency(res['c']['data']['energy_cost'], st.session_state.currency), f"{res['c']['data']['water_kl']:,.0f}", format_currency(res['c']['data']['water_cost'], st.session_state.currency), 
            f"{res['c']['data']['emissions']*1000:,.0f}", format_currency(res['c']['maint'], st.session_state.currency), format_currency(res['c']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['c']['tot_op'], st.session_state.currency), 
            "Baseline", "Baseline", format_currency(res['c']['capex'], st.session_state.currency), "Baseline", "Baseline"
        ],
        "PCM TES Opt.": [
            f"{res['p']['cap_base'] + res['p']['cap_dual']:,.0f}", f"{res['p']['cap_tes']:,.0f}", f"{res['p']['dem']:,.0f}", f"{res['p']['dg_kva']:,.0f}", f"{res['p']['data']['energy_kwh']:,.0f}", 
            format_currency(res['p']['data']['energy_cost'], st.session_state.currency), f"{res['p']['data']['water_kl']:,.0f}", format_currency(res['p']['data']['water_cost'], st.session_state.currency), 
            f"{res['p']['data']['emissions']*1000:,.0f}", format_currency(res['p']['maint'], st.session_state.currency), format_currency(res['p']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['p']['tot_op'], st.session_state.currency), 
            format_currency(res['p']['dg_sav'], st.session_state.currency), format_currency(res['p']['sav'], st.session_state.currency), format_currency(res['p']['capex'], st.session_state.currency), format_currency(res['p']['inc_cap'], st.session_state.currency), f"{res['p']['pb']:.2f}"
        ],
        "Strat. TES Opt.": [
            f"{res['s']['cap_base']:,.0f}", f"{res['s']['cap_tes']:,.0f}", f"{res['s']['dem']:,.0f}", f"{res['s']['dg_kva']:,.0f}", f"{res['s']['data']['energy_kwh']:,.0f}", 
            format_currency(res['s']['data']['energy_cost'], st.session_state.currency), f"{res['s']['data']['water_kl']:,.0f}", format_currency(res['s']['data']['water_cost'], st.session_state.currency), 
            f"{res['s']['data']['emissions']*1000:,.0f}", format_currency(res['s']['maint'], st.session_state.currency), format_currency(res['s']['data']['annual_dg_cost'], st.session_state.currency), format_currency(res['s']['tot_op'], st.session_state.currency), 
            format_currency(res['s']['dg_sav'], st.session_state.currency), format_currency(res['s']['sav'], st.session_state.currency), format_currency(res['s']['capex'], st.session_state.currency), format_currency(res['s']['inc_cap'], st.session_state.currency), f"{res['s']['pb']:.2f}"
        ]
    })

    with t4:
        st.subheader("📊 Executive Summary")
        st.table(df_comp)
        
        st.markdown("### 💰 Master CAPEX Breakdown")
        if "Brownfield" in st.session_state.proj_type: st.info("Sunk assets (existing chillers, pumps, towers) are evaluated at ₹ 0.00 CAPEX in the baseline.")
        df_bk = pd.DataFrame({
            "Category": list(res['c']['bk'].keys()),
            "Conventional N+1": [format_currency(v, st.session_state.currency) for v in res['c']['bk'].values()],
            "PCM TES Opt.": [format_currency(v, st.session_state.currency) for v in res['p']['bk'].values()],
            "Strat. TES Opt.": [format_currency(v, st.session_state.currency) for v in res['s']['bk'].values()]
        })
        st.table(df_bk)

    with t5:
        st.subheader("📑 Report Dashboard & Export")
        c1, c2 = st.columns(2)
        with c1:
            pdf = generate_pdf_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp, load_arr[:24], tar_arr[:24], res, sym)
            st.download_button("📥 Export High-Def PDF Report", data=pdf, file_name=f"CETP_Report_{st.session_state.proj_name}.pdf", mime="application/pdf", use_container_width=True)
        with c2:
            doc = generate_word_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp, load_arr[:24], tar_arr[:24], res, sym)
            if doc: st.download_button("📝 Export Editable Word Document (.docx)", data=doc, file_name=f"CETP_Report_{st.session_state.proj_name}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    gc.collect()