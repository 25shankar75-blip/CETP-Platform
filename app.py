# app.py
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import json
import gc

from schemas import ProjectConfig, ThermoConfig, HydraulicConfig, FinancialConfig, CURRENCY_MULTIPLIERS
from physics_engine import expand_24_to_8760
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin Platform", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

# DEFAULT PROFILES
DEFAULT_LOAD = [60, 60, 60, 60, 60, 60, 80, 90, 100, 100, 100, 100, 100, 100, 90, 90, 80, 80, 70, 70, 60, 60, 60, 60]
DEFAULT_TARIFF = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2

# --- SESSION STATE & SAVE/LOAD LOGIC ---
ui_keys = {
    "proj_name": "Pharma Greenfield Baseline", "location": "MP, India", "industry": "Pharmaceuticals",
    "proj_type": "Greenfield Project", "peak_load_tr": 2794.18, "tank_shape": "Cylindrical (API 650)",
    "currency": "INR (₹)", "chiller_type": "Water-Cooled (With Cooling Towers)", "demand_rate": 475.0
}
for k, v in ui_keys.items():
    if k not in st.session_state: st.session_state[k] = v

with st.sidebar.expander("💾 Project Management (Save / Open)", expanded=False):
    uploaded_json = st.file_uploader("📂 Open Existing Project (.json)", type="json")
    if uploaded_json is not None:
        try:
            data = json.load(uploaded_json)
            for k in ui_keys.keys():
                if k in data: st.session_state[k] = data[k]
            if "df_24" in data: st.session_state["df_24"] = pd.DataFrame(data["df_24"])
            st.success("Project Loaded Successfully!")
            st.rerun()
        except: st.error("Invalid project file.")

    save_dict = {k: st.session_state[k] for k in ui_keys.keys()}
    if "df_24" in st.session_state: save_dict["df_24"] = st.session_state["df_24"].to_dict(orient="records")
    st.download_button("💾 Save Project Current State", json.dumps(save_dict), file_name="cetp_project.json", mime="application/json")

st.sidebar.header("🛠️ Input Master Suite")
with st.sidebar.expander("📌 Project Details", expanded=True):
    proj_name = st.text_input("Project Name", key="proj_name")
    location = st.text_input("Location", key="location")
    industry = st.selectbox("Industry Sector", ["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process", "FMCG", "Auto"], key="industry")
    proj_type = st.radio("Project Scope", ["Greenfield Project", "Brownfield / Retrofit"], key="proj_type")
    peak_load_tr = st.number_input("Peak Cooling Load (TR)", key="peak_load_tr")
    tank_shape = st.selectbox("Tank Geometry", ["Cylindrical (API 650)", "Rectangular Concrete/Steel"], key="tank_shape")
    currency = st.selectbox("Currency Unit", list(CURRENCY_MULTIPLIERS.keys()), key="currency")

with st.sidebar.expander("🌡️ Thermodynamics"): chiller_type = st.selectbox("Chiller Type", ["Water-Cooled (With Cooling Towers)", "Air-Cooled"], key="chiller_type")
with st.sidebar.expander("💧 Hydraulics"): hc = HydraulicConfig()
with st.sidebar.expander("💰 Financial Rates"): demand_rate = st.number_input("Demand Charge (per kVA)", key="demand_rate")

sym = CURRENCY_MULTIPLIERS[currency]["symbol"]
mult = CURRENCY_MULTIPLIERS[currency]["rate"]
rates = {'water_cooled_chiller': 17000*mult, 'air_cooled_chiller': 19000*mult, 'brine_chiller': 23000*mult, 'pcm_tes_cylindrical': 7533*mult, 'pcm_tes_rectangular': 8475*mult, 'strat_tes': 18000*mult, 'cooling_tower': 2200*mult, 'chw_pump': 700*mult, 'cdw_pump': 550*mult, 'brine_pump': 900*mult, 'phe': 1100*mult, 'dg_set': 11000*mult, 'transformer': 1700*mult}
tc = ThermoConfig(chiller_type=chiller_type)
fc = FinancialConfig(demand_rate=demand_rate)

# --- 7 EXACT TABS REQUIRED ---
t1, t2, t3, t4, t5, t6, t7 = st.tabs(["Load Profile", "Conv. Plant", "PCM TES Opt.", "Strat. TES Opt.", "Exec. Summary", "CAPEX Breakup", "Report Dashboard"])

with t1:
    st.subheader("Interactive 24-Hour Diurnal Load & ToU Tariff Data Editor")
    if "df_24" not in st.session_state or st.session_state.get("pk") != peak_load_tr:
        st.session_state["df_24"] = pd.DataFrame({
            "Hour": [f"Hour {i:02d}" for i in range(24)], "Load (%)": [float(p) for p in DEFAULT_LOAD],
            "Load (TR)": [(p/100)*peak_load_tr for p in DEFAULT_LOAD], f"Tariff ({sym})": [t*mult for t in DEFAULT_TARIFF]
        })
        st.session_state["pk"] = peak_load_tr

    df_edit = st.data_editor(st.session_state["df_24"], use_container_width=True, num_rows="fixed", key="edit_24")
    state = st.session_state.get("edit_24", {}).get("edited_rows", {})
    if state:
        for r, changes in state.items():
            if "Load (%)" in changes: df_edit.at[int(r), "Load (TR)"] = (float(changes["Load (%)"])/100)*peak_load_tr
            if "Load (TR)" in changes: df_edit.at[int(r), "Load (%)"] = (float(changes["Load (TR)"])/peak_load_tr)*100
        st.session_state["df_24"] = df_edit.copy()

    load_arr = df_edit["Load (TR)"].tolist()
    tar_arr = df_edit[f"Tariff ({sym})"].tolist()

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Run 8,760-Hour Simulation", type="primary"):
    with st.spinner("Executing Mathematical Optimization..."):
        prm = {"chw_supply": 7.0, "chw_return": 12.0, "brine_supply": -5.5, "brine_return": -1.7, "kw_tr_base": 0.58, "kw_tr_brine": 0.85, 'unit_rates': rates, 'chiller_type': chiller_type, 'tank_shape': tank_shape, 'head_chw': 40.0, 'head_cw': 30.0, 'pump_efficiency': 0.70, 'ct_fan_ikw_tr': 0.015, 'demand_rate': demand_rate}
        charge_hrs = {22, 23, 0, 1, 2, 3, 4, 5}
        
        res = optimize_plant(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), peak_load_tr, charge_hrs, prm, proj_type)
        
        def render_detailed_hourly_table(data_dict):
            df_detailed = pd.DataFrame({
                "Hour": [f"{i:02d}:00" for i in range(24)], "Load (TR)": load_arr[:24], "Charge (TR)": data_dict['data']['charge'][:24],
                "Discharge (TR)": data_dict['data']['discharge'][:24], "Base Chiller (kW)": data_dict['data']['kw_comp'][:24],
                "Brine Chiller (kW)": data_dict['data']['kw_brine'][:24], "CHW Pump (kW)": data_dict['data']['kw_chw'][:24],
                "CDW Pump (kW)": data_dict['data']['kw_cw'][:24], "CT Fan (kW)": data_dict['data']['kw_fan'][:24], "Total Sys (kW)": data_dict['data']['total_kw'][:24]
            })
            st.dataframe(df_detailed.style.format(precision=1), use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Conventional Chiller Plant (N+1)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Installed Base Chillers", f"{res['c']['cap_base']:,.0f} TR")
            c2.metric("Peak Electrical Demand", f"{res['c']['dem']:,.1f} kW")
            c3.metric("Required Substation & DG", f"{res['c']['dg_kva']:,.0f} kVA")
            c4.metric("Total Annual OPEX", format_currency(res['c']['opex'], currency))
            render_detailed_hourly_table(res['c'])

        with t3:
            st.subheader("PCM Thermal Energy Storage")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Downsized Base Chillers", f"{res['p']['cap_base']:,.0f} TR", f"{res['p']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
            c2.metric("Sub-Zero Brine Chillers", f"{res['p']['cap_dual']:,.0f} TR")
            c3.metric("PCM Storage Volume", f"{res['p']['cap_tes']:,.0f} TRh")
            c4.metric("Required Substation & DG", f"{res['p']['dg_kva']:,.0f} kVA", f"{res['p']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Peak Electrical Demand", f"{res['p']['dem']:,.1f} kW", f"{res['p']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
            c6.metric("Daily Peak Discharge", f"{sum(res['p']['data']['discharge'][:24]):,.0f} TRh")
            c7.metric("Total Annual OPEX", format_currency(res['p']['opex'], currency), f"- {format_currency(res['c']['opex'] - res['p']['opex'], currency)}")
            c8.metric("Simple Payback", f"{res['p']['pb']:.2f} Years" if res['p']['pb']>0 else "Instantaneous")
            render_detailed_hourly_table(res['p'])

        with t4:
            st.subheader("Stratified CHW Thermal Storage")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Downsized Base Chillers", f"{res['s']['cap_base']:,.0f} TR", f"{res['s']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
            c2.metric("Sub-Zero Brine Chillers", "0 TR")
            c3.metric("Stratified Storage Volume", f"{res['s']['cap_tes']:,.0f} TRh")
            c4.metric("Required Substation & DG", f"{res['s']['dg_kva']:,.0f} kVA", f"{res['s']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Peak Electrical Demand", f"{res['s']['dem']:,.1f} kW", f"{res['s']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
            c6.metric("Daily Peak Discharge", f"{sum(res['s']['data']['discharge'][:24]):,.0f} TRh")
            c7.metric("Total Annual OPEX", format_currency(res['s']['opex'], currency), f"- {format_currency(res['c']['opex'] - res['s']['opex'], currency)}")
            c8.metric("Simple Payback", f"{res['s']['pb']:.2f} Years" if res['s']['pb']>0 else "Instantaneous")
            render_detailed_hourly_table(res['s'])

        df_comp = pd.DataFrame({
            "Parameter": ["Base Chiller (TR)", "Brine Chiller (TR)", "Storage Vol (TRh)", "Peak Demand (kW)", "Substation (kVA)", "Total CAPEX", "Total OPEX", "Payback (Yrs)"],
            "Conventional N+1": [f"{res['c']['cap_base']:,.0f}", "-", "0", f"{res['c']['dem']:,.0f}", f"{res['c']['dg_kva']:,.0f}", format_currency(res['c']['capex'], currency), format_currency(res['c']['opex'], currency), "Baseline"],
            "PCM TES Opt.": [f"{res['p']['cap_base']:,.0f}", f"{res['p']['cap_dual']:,.0f}", f"{res['p']['cap_tes']:,.0f}", f"{res['p']['dem']:,.0f}", f"{res['p']['dg_kva']:,.0f}", format_currency(res['p']['capex'], currency), format_currency(res['p']['opex'], currency), f"{res['p']['pb']:.2f}"],
            "Strat. TES Opt.": [f"{res['s']['cap_base']:,.0f}", "-", f"{res['s']['cap_tes']:,.0f}", f"{res['s']['dem']:,.0f}", f"{res['s']['dg_kva']:,.0f}", format_currency(res['s']['capex'], currency), format_currency(res['s']['opex'], currency), f"{res['s']['pb']:.2f}"]
        })

        with t5:
            st.subheader("📊 Executive System Comparison")
            st.table(df_comp)

        with t6:
            st.subheader("💰 Master CAPEX Breakdown")
            df_bk = pd.DataFrame({
                "Category": list(res['c']['bk'].keys()),
                "Conventional N+1": [format_currency(v, currency) for v in res['c']['bk'].values()],
                "PCM TES Opt.": [format_currency(v, currency) for v in res['p']['bk'].values()],
                "Strat. TES Opt.": [format_currency(v, currency) for v in res['s']['bk'].values()]
            })
            st.table(df_bk)

        with t7:
            st.subheader("📑 Summarized Report Dashboard & Export")
            st.info("Download client-ready executive proposals. All multi-currency rates, sizing logic, and CAPEX displacement rules have been integrated.")
            
            c1, c2 = st.columns(2)
            with c1:
                pdf = generate_pdf_report(proj_name, location, industry, proj_type, currency, df_comp)
                st.download_button("📥 Export PDF Report", data=pdf, file_name=f"CETP_Report_{proj_name}.pdf", mime="application/pdf", use_container_width=True)
            with c2:
                doc = generate_word_report(proj_name, location, industry, proj_type, currency, df_comp)
                if doc: st.download_button("📝 Export Word Document (.docx)", data=doc, file_name=f"CETP_Report_{proj_name}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
                else: st.error("⚠️ `python-docx` is not installed. Please add it to requirements.txt.")
        
        gc.collect()