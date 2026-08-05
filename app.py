# app.py
import streamlit as st
import numpy as np
import pandas as pd
import json
import gc

from schemas import CURRENCY_MULTIPLIERS
from physics_engine import expand_24_to_8760
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin Platform", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

DEFAULT_LOAD = [1676.5, 1676.5, 1676.5, 1676.5, 1676.5, 1676.5, 2235.3, 2514.7, 2794.18, 2794.18, 2794.18, 2794.18, 2794.18, 2794.18, 2514.7, 2514.7, 2235.3, 2235.3, 1955.9, 1955.9, 1676.5, 1676.5, 1676.5, 1676.5]
DEFAULT_TARIFF = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2

# --- SESSION STATE INITIALIZATION (FIXES BLANK FIELDS BUG) ---
ui_keys = {
    "proj_name": "Example Pharma Project", "location": "Ujjain, MP, India", "industry": "Pharmaceuticals", "proj_type": "Greenfield Project", 
    "tank_shape": "Cylindrical", "tes_strategy": "Partial Storage", "currency": "INR (₹)", "chiller_type": "Water-Cooled", 
    "chw_supply": 7.0, "chw_return": 12.0, "brine_supply": -5.0, "brine_return": -1.7, "kw_tr_base": 0.58, "kw_tr_brine": 0.85, 
    "chw_pump_kw": 0.078, "cw_pump_kw": 0.030, "ct_fan_kw": 0.020, "brine_pump_kw": 0.020, "demand_rate": 475.0, "water_cost_kl": 25.0, 
    "grid_emission": 0.716, "evap_loss": 1.8, "rate_water_chiller": 19000.0, "rate_air_chiller": 21000.0, "rate_brine_chiller": 23000.0, 
    "rate_pcm_cyl": 7800.0, "rate_pcm_rect": 8500.0, "rate_strat_tes": 18000.0, "rate_ct": 3200.0, "rate_chw_pump": 900.0, 
    "rate_cw_pump": 650.0, "rate_brine_pump": 900.0, "rate_phe_int": 1500.0, "rate_dg": 11000.0, "rate_transformer": 1700.0, 
    "run_sim": False
}

for k, v in ui_keys.items():
    if k not in st.session_state: st.session_state[k] = v

def reset_sim(): st.session_state.run_sim = False

st.sidebar.header("🛠️ Input Master Suite")
nav_selection = st.sidebar.radio("Navigation Menu", ["⚙️ 1. 24-Hr Load Profile", "📌 2. Project & TES Parameters", "🌡️ 3. Chiller & Aux Parameters", "💰 4. Financial CAPEX Rates", "⚡ 5. Water & Electrical Data"], on_change=reset_sim)

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

sym = CURRENCY_MULTIPLIERS[st.session_state.currency]["symbol"]
mult = CURRENCY_MULTIPLIERS[st.session_state.currency]["rate"]

# Initialize Master Load Table
if "df_24" not in st.session_state:
    st.session_state["df_24"] = pd.DataFrame({
        "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": DEFAULT_LOAD,
        "Load (%)": [(p/2794.18)*100 for p in DEFAULT_LOAD], f"Tariff ({sym})": [t*mult for t in DEFAULT_TARIFF]
    })
calc_peak = float(st.session_state["df_24"]["Load (TR)"].max())
calc_daily = float(st.session_state["df_24"]["Load (TR)"].sum())
calc_avg = float(st.session_state["df_24"]["Load (TR)"].mean())

# --- MAIN SCREEN LOGIC ---
if not st.session_state.run_sim:
    if nav_selection == "⚙️ 1. 24-Hr Load Profile":
        st.subheader("⚙️ Hourly Load & Tariff Input")
        df_edit = st.data_editor(st.session_state["df_24"], use_container_width=True, num_rows="fixed", key="edit_24")
        
        state = st.session_state.get("edit_24", {}).get("edited_rows", {})
        if state:
            curr_peak = df_edit["Load (TR)"].max()
            for r, changes in state.items():
                if "Load (TR)" in changes: df_edit.at[int(r), "Load (%)"] = (float(changes["Load (TR)"])/curr_peak)*100 if curr_peak > 0 else 0
                if "Load (%)" in changes: df_edit.at[int(r), "Load (TR)"] = (float(changes["Load (%)"])/100)*curr_peak
            st.session_state["df_24"] = df_edit.copy()
            st.rerun() 
            
        st.markdown("---")
        st.markdown("##### Calculated Operational Displays (Locked from Table)")
        c1, c2, c3, c4 = st.columns(4)
        c1.number_input("Peak Load (TR)", value=calc_peak, disabled=True)
        c2.number_input("Avg Load (TR)", value=calc_avg, disabled=True)
        c3.number_input("Daily Load (TRh)", value=calc_daily, disabled=True)
        c4.number_input("Annual Load (TRh)", value=calc_daily*365, disabled=True)

    elif nav_selection == "📌 2. Project & TES Parameters":
        st.subheader("📌 Project Details")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.proj_name = st.text_input("Project Name", value=st.session_state.proj_name)
            st.session_state.location = st.text_input("Location", value=st.session_state.location)
            
            industries = ["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"]
            st.session_state.industry = st.selectbox("Industry Sector", industries, index=industries.index(st.session_state.industry))
            
            currencies = list(CURRENCY_MULTIPLIERS.keys())
            st.session_state.currency = st.selectbox("Currency Unit", currencies, index=currencies.index(st.session_state.currency))
        with col2:
            st.session_state.proj_type = st.radio("Project Scope", ["Greenfield Project", "Brownfield / Retrofit"], index=0 if st.session_state.proj_type == "Greenfield Project" else 1)
            st.session_state.tes_strategy = st.selectbox("TES Strategy", ["Partial Storage", "Full Storage", "Demand Limiting"], index=["Partial Storage", "Full Storage", "Demand Limiting"].index(st.session_state.tes_strategy))
            st.session_state.tank_shape = st.selectbox("Tank Geometry", ["Cylindrical", "Rectangular"], index=["Cylindrical", "Rectangular"].index(st.session_state.tank_shape))

    elif nav_selection == "🌡️ 3. Chiller & Aux Parameters":
        st.subheader("🌡️ Base Chiller & Auxiliary Parameters")
        st.session_state.chiller_type = st.selectbox("Chiller Type", ["Water-Cooled", "Air-Cooled"], index=0 if st.session_state.chiller_type == "Water-Cooled" else 1)
        c1, c2 = st.columns(2)
        
        st.session_state.chw_supply = c1.number_input("CHW Supply Temp (°C)", value=st.session_state.chw_supply)
        st.session_state.brine_supply = c1.number_input("Brine Supply Temp (°C)", value=st.session_state.brine_supply)
        st.session_state.kw_tr_base = c1.number_input("Design Full Load Base Chiller (kW/TR)", value=st.session_state.kw_tr_base)
        
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>CHW Pump Power (kW/TR) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.chw_pump_kw = c1.number_input("chw_pump", value=st.session_state.chw_pump_kw, label_visibility="collapsed")
        
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>CT Fan Power (kW/TR) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.ct_fan_kw = c1.number_input("ct_fan", value=st.session_state.ct_fan_kw, label_visibility="collapsed")
        
        st.session_state.chw_return = c2.number_input("CHW Return Temp (°C)", value=st.session_state.chw_return)
        st.session_state.brine_return = c2.number_input("Brine Return Temp (°C)", value=st.session_state.brine_return)
        st.session_state.kw_tr_brine = c2.number_input("Brine Chiller Full Load (kW/TR)", value=st.session_state.kw_tr_brine)
        
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Condenser Water Pump Power (kW/TR) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.cw_pump_kw = c2.number_input("cw_pump", value=st.session_state.cw_pump_kw, label_visibility="collapsed")
        
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Brine Pump Power (kW/TR) [Standard Base]</span>", unsafe_allow_html=True)
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
        st.subheader("⚡ Water & Electrical Parameters")
        c1, c2 = st.columns(2)
        st.session_state.water_cost_kl = c1.number_input("Water Cost (per kL)", value=st.session_state.water_cost_kl)
        c1.markdown("<span style='color:#1f77b4; font-weight:bold;'>Evaporation Loss (L/TRh) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.evap_loss = c1.number_input("evap_loss", value=st.session_state.evap_loss, label_visibility="collapsed")
        
        c2.markdown("<span style='color:#1f77b4; font-weight:bold;'>Grid Emission Factor (kg CO₂/kWh) [Standard Base]</span>", unsafe_allow_html=True)
        st.session_state.grid_emission = c2.number_input("grid_emission", value=st.session_state.grid_emission, label_visibility="collapsed")

else:
    # --- 7 TAB OUTPUT INTERFACE ---
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
        "chw_supply": st.session_state.chw_supply, "chw_return": st.session_state.chw_return, "brine_supply": st.session_state.brine_supply, 
        "brine_return": st.session_state.brine_return, "kw_tr_base": st.session_state.kw_tr_base, "kw_tr_brine": st.session_state.kw_tr_brine, 
        "chw_pump_kw": st.session_state.chw_pump_kw, "cw_pump_kw": st.session_state.cw_pump_kw, "ct_fan_kw": st.session_state.ct_fan_kw, 
        "brine_pump_kw": st.session_state.brine_pump_kw, "evap_loss": st.session_state.evap_loss, "water_cost_kl": st.session_state.water_cost_kl*mult,
        "grid_emission": st.session_state.grid_emission, 'unit_rates': rates, 'chiller_type': st.session_state.chiller_type, 
        'tank_shape': st.session_state.tank_shape, 'demand_rate': st.session_state.demand_rate*mult, "indirects_pct": 0.30
    }
    
    load_arr = st.session_state["df_24"]["Load (TR)"].tolist()
    tar_arr = st.session_state["df_24"][f"Tariff ({sym})"].tolist()
    charge_hrs = {22, 23, 0, 1, 2, 3, 4, 5}
    res = optimize_plant(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), calc_peak, charge_hrs, prm, st.session_state.proj_type)
    
    def render_detailed_hourly_table(data_dict):
        df_detailed = pd.DataFrame({
            "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": load_arr[:24], "Charge (TR)": data_dict['data']['charge'][:24],
            "Discharge (TR)": data_dict['data']['discharge'][:24], "Base Chiller (kW)": data_dict['data']['kw_comp'][:24],
            "Brine Chiller (kW)": data_dict['data']['kw_brine'][:24], "CHW Pump (kW)": data_dict['data']['kw_chw'][:24],
            "CDW Pump (kW)": data_dict['data']['kw_cw'][:24], "CT Fan (kW)": data_dict['data']['kw_fan'][:24], "Total Sys (kW)": data_dict['data']['total_kw'][:24]
        })
        st.dataframe(df_detailed.style.format(precision=1), use_container_width=True, hide_index=True)

    with t1:
        st.subheader("Hourly Load & Tariff Profile")
        st.dataframe(st.session_state["df_24"], use_container_width=True, hide_index=True)

    with t2:
        st.subheader("Conventional Chiller Plant (N+1)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Installed Base Chillers", f"{res['c']['cap_base']:,.0f} TR")
        c2.metric("Peak Electrical Demand", f"{res['c']['dem']:,.1f} kW")
        c3.metric("Required Substation & DG", f"{res['c']['dg_kva']:,.0f} kVA")
        c4.metric("Total Annual OPEX", format_currency(res['c']['opex'], st.session_state.currency))
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
        c7.metric("Total Annual OPEX", format_currency(res['p']['opex'], st.session_state.currency), f"- {format_currency(res['c']['opex'] - res['p']['opex'], st.session_state.currency)}")
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
        c7.metric("Total Annual OPEX", format_currency(res['s']['opex'], st.session_state.currency), f"- {format_currency(res['c']['opex'] - res['s']['opex'], st.session_state.currency)}")
        c8.metric("Simple Payback", f"{res['s']['pb']:.2f} Years" if res['s']['pb']>0 else "Instantaneous")
        st.markdown("##### Hourly Load Management & Equipment Power (kW)")
        render_detailed_hourly_table(res['s'])

    df_comp = pd.DataFrame({
        "Parameter": ["Base Chiller (TR)", "Brine Chiller (TR)", "Storage Vol (TRh)", "Peak Demand (kW)", "Substation (kVA)", "Carbon Emissions (tCO2/yr)", "Water Makeup (kL/yr)", "Total CAPEX", "Total OPEX", "Payback (Yrs)"],
        "Conventional N+1": [f"{res['c']['cap_base']:,.0f}", "-", "0", f"{res['c']['dem']:,.0f}", f"{res['c']['dg_kva']:,.0f}", f"{res['c']['data']['emissions']:,.0f}", f"{res['c']['data']['water_kl']:,.0f}", format_currency(res['c']['capex'], st.session_state.currency), format_currency(res['c']['opex'], st.session_state.currency), "Baseline"],
        "PCM TES Opt.": [f"{res['p']['cap_base']:,.0f}", f"{res['p']['cap_dual']:,.0f}", f"{res['p']['cap_tes']:,.0f}", f"{res['p']['dem']:,.0f}", f"{res['p']['dg_kva']:,.0f}", f"{res['p']['data']['emissions']:,.0f}", f"{res['p']['data']['water_kl']:,.0f}", format_currency(res['p']['capex'], st.session_state.currency), format_currency(res['p']['opex'], st.session_state.currency), f"{res['p']['pb']:.2f}"],
        "Strat. TES Opt.": [f"{res['s']['cap_base']:,.0f}", "-", f"{res['s']['cap_tes']:,.0f}", f"{res['s']['dem']:,.0f}", f"{res['s']['dg_kva']:,.0f}", f"{res['s']['data']['emissions']:,.0f}", f"{res['s']['data']['water_kl']:,.0f}", format_currency(res['s']['capex'], st.session_state.currency), format_currency(res['s']['opex'], st.session_state.currency), f"{res['s']['pb']:.2f}"]
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
            pdf = generate_pdf_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp)
            st.download_button("📥 Export PDF Report", data=pdf, file_name=f"CETP_Report_{st.session_state.proj_name}.pdf", mime="application/pdf", use_container_width=True)
        with c2:
            doc = generate_word_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, df_comp)
            if doc: st.download_button("📝 Export Word Document (.docx)", data=doc, file_name=f"CETP_Report_{st.session_state.proj_name}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    gc.collect()