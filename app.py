"""
Cooling Energy Transition Platform (CETP) - Master Streamlit Frontend
File: app.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import json

from schemas import CURRENCY_MULTIPLIERS, ProjectConfig, AuditConfig, FinancialConfig, ChillerTypeEnum, ScopeEnum, SectorEnum, TankShapeEnum
from physics_engine import fetch_live_weather_wbt
from financial_engine import fetch_live_currency_rates, format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report 

st.set_page_config(page_title="CETP Digital Twin", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

# --- INITIALIZE STATE ---
if "fin_cfg" not in st.session_state: st.session_state.fin_cfg = FinancialConfig()
if "proj_cfg" not in st.session_state: st.session_state.proj_cfg = ProjectConfig()
if "audit_cfg" not in st.session_state: st.session_state.audit_cfg = AuditConfig()
if "df_24h" not in st.session_state:
    st.session_state.df_24h = pd.DataFrame({
        "Hour": np.arange(1, 25), 
        "Cooling Load (TR)": [0.0]*24, 
        "Tariff (₹/kWh)": [0.0]*24 
    })
if "chiller_fleet" not in st.session_state:
    st.session_state.chiller_fleet = pd.DataFrame([
        {"Capacity (TR)": 0.0, "Quantity": 1, "Chiller Type": "Water-Cooled Centrifugal", "ikW/TR": 0.62, "Standby": False}
    ])
if "opt_results" not in st.session_state: st.session_state.opt_results = None

# --- SIDEBAR: EXECUTION ---
st.sidebar.title("🎛️ Execution Controls")
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader("📂 Upload Project (.json)", type=["json"])
if uploaded_file:
    try:
        data = json.load(uploaded_file)
        st.session_state.df_24h = pd.DataFrame(data["df_24h"])
        st.session_state.chiller_fleet = pd.DataFrame(data["chiller_fleet"])
        st.sidebar.success("Scenario Restored! ✅")
    except Exception:
        st.sidebar.error("Invalid format. Please upload a valid CETP JSON.")

scenario_data = {"df_24h": st.session_state.df_24h.to_dict(), "chiller_fleet": st.session_state.chiller_fleet.to_dict()}
st.sidebar.download_button("💾 Save Project (.json)", json.dumps(scenario_data), "CETP_Scenario.json", "application/json", use_container_width=True)
st.sidebar.markdown("---")

if st.sidebar.button("▶️ Run Digital Twin Optimization", type="primary", use_container_width=True):
    if not st.session_state.proj_cfg.location:
        st.sidebar.error("❌ Action Required: Please enter a Location in the 'Setup' tab to fetch live weather APIs.")
    elif max(st.session_state.df_24h["Cooling Load (TR)"]) == 0:
        st.sidebar.error("❌ Action Required: Please input non-zero Cooling Loads in the 'Load & Tariffs' tab.")
    else:
        rates_dict = st.session_state.fin_cfg.dict()
        audit_dict = st.session_state.audit_cfg.dict()
        with st.spinner("Fetching Live APIs and Computing Predictive BMS Variables..."):
            wbt_data = fetch_live_weather_wbt(st.session_state.proj_cfg.location)
            st.session_state.opt_results = optimize_plant(
                st.session_state.chiller_fleet, 
                st.session_state.df_24h["Cooling Load (TR)"].values, 
                st.session_state.df_24h["Tariff (₹/kWh)"].values, 
                wbt_data["wbt"],
                st.session_state.proj_cfg.scope, 
                audit_dict, rates_dict,
                st.session_state.proj_cfg.running_days or 365, 
                st.session_state.proj_cfg.tank_shape
            )
            if wbt_data["status"] == "LIVE": 
                st.sidebar.success(f"Live Weather fetched for {st.session_state.proj_cfg.location}! Optimization Complete.")
            else: 
                st.sidebar.warning("Optimization Complete! (Fallback Weather Model Used)")

# --- MASTER TABS ---
t1, t2, t3, t4, t5, t6, t7 = st.tabs(["🎛️ Global Setup & Financials", "⚙️ Hydraulics & Chiller Fleet", "📊 Load & Tariffs", "🏭 Baseline Output", "🧊 PCM TES Output", "🌊 Stratified TES Output", "💰 Executive Summary"])

with t1:
    st.subheader("Project Configuration")
    c1, c2, c3, c4 = st.columns(4)
    st.session_state.proj_cfg.project_name = c1.text_input("Project Name", value=st.session_state.proj_cfg.project_name, placeholder="e.g. Mondelez Phase 1")
    st.session_state.proj_cfg.location = c2.text_input("Location (Required for WBT API)", value=st.session_state.proj_cfg.location, placeholder="e.g. Gurugram, IN")
    st.session_state.proj_cfg.scope = c3.selectbox("Project Scope", [ScopeEnum.GREENFIELD.value, ScopeEnum.BROWNFIELD.value], index=0)
    st.session_state.proj_cfg.currency = c4.selectbox("Currency", list(CURRENCY_MULTIPLIERS.keys()))

    st.markdown("---")
    st.subheader("Rev 19 Engineering & Financial Baselines")
    with st.expander("Expand to Input Baseline Equipment & Financial Rates", expanded=True):
        st.info("Input explicit values based on project specifics. Leaving fields blank will trigger standard ASHRAE/Industry defaults during simulation.")
        r1, r2, r3, r4 = st.columns(4)
        st.session_state.proj_cfg.tank_shape = r1.selectbox("PCM Tank Geometry", [TankShapeEnum.CYLINDRICAL.value, TankShapeEnum.RECTANGULAR.value])
        st.session_state.proj_cfg.chiller_module_tr = r2.number_input("Standard Chiller Module (TR)", value=st.session_state.proj_cfg.chiller_module_tr)
        st.session_state.proj_cfg.running_days = r3.number_input("Annual Running Days", value=st.session_state.proj_cfg.running_days, min_value=1, max_value=365)
        st.session_state.proj_cfg.project_life_years = r4.number_input("Project Life (Years)", value=st.session_state.proj_cfg.project_life_years)

        r1, r2, r3 = st.columns(3)
        st.session_state.audit_cfg.kw_tr_base = r1.number_input("Base Chiller Efficiency (kW/TR)", value=st.session_state.audit_cfg.kw_tr_base)
        st.session_state.audit_cfg.kw_tr_brine = r2.number_input("Brine Chiller Efficiency (kW/TR)", value=st.session_state.audit_cfg.kw_tr_brine)
        st.session_state.audit_cfg.kw_tr_ac = r3.number_input("Air-Cooled Efficiency (kW/TR)", value=st.session_state.audit_cfg.kw_tr_ac)

        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.base_chiller_rate = r1.number_input("Base Chiller Rate (₹/TR)", value=st.session_state.fin_cfg.base_chiller_rate)
        st.session_state.fin_cfg.ac_chiller_rate = r2.number_input("Air-Cooled Chiller Rate (₹/TR)", value=st.session_state.fin_cfg.ac_chiller_rate)
        st.session_state.fin_cfg.brine_chiller_rate = r3.number_input("Brine Chiller Rate (₹/TR)", value=st.session_state.fin_cfg.brine_chiller_rate)
        
        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.pcm_cyl_rate = r1.number_input("PCM Cylindrical Rate (₹/TRh)", value=st.session_state.fin_cfg.pcm_cyl_rate)
        st.session_state.fin_cfg.pcm_rect_rate = r2.number_input("PCM Rectangular Rate (₹/TRh)", value=st.session_state.fin_cfg.pcm_rect_rate)
        st.session_state.fin_cfg.stratified_tes_rate = r3.number_input("Stratified TES Rate (₹/TRh)", value=st.session_state.fin_cfg.stratified_tes_rate)

        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.dg_set_rate = r1.number_input("DG Set Rate (₹/TR)", value=st.session_state.fin_cfg.dg_set_rate)
        st.session_state.fin_cfg.transformer_rate = r2.number_input("Transformer Rate (₹/TR)", value=st.session_state.fin_cfg.transformer_rate)
        st.session_state.fin_cfg.water_infra_rate = r3.number_input("Water Infra Rate (₹/TR)", value=st.session_state.fin_cfg.water_infra_rate)

        r1, r2, r3, r4 = st.columns(4)
        st.session_state.fin_cfg.discount_rate_pct = r1.number_input("Discount Rate (%)", value=st.session_state.fin_cfg.discount_rate_pct)
        st.session_state.fin_cfg.elec_escalation_pct = r2.number_input("Electricity Escalation (%)", value=st.session_state.fin_cfg.elec_escalation_pct)
        st.session_state.fin_cfg.water_escalation_pct = r3.number_input("Water Escalation (%)", value=st.session_state.fin_cfg.water_escalation_pct)
        st.session_state.fin_cfg.indirects_pct = r4.number_input("Indirects / AMC (%)", value=st.session_state.fin_cfg.indirects_pct)

        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.dg_diesel_cost_kwh = r1.number_input("DG Diesel Cost (₹/kWh)", value=st.session_state.fin_cfg.dg_diesel_cost_kwh)
        st.session_state.fin_cfg.daily_outage_hrs = r2.number_input("Daily Power Outage (Hrs)", value=st.session_state.fin_cfg.daily_outage_hrs)
        st.session_state.audit_cfg.water_cost_per_m3 = r3.number_input("Water Cost (₹/m³)", value=st.session_state.audit_cfg.water_cost_per_m3)

with t2:
    st.header("🔍 Hydraulic Input Suite")
    if st.session_state.proj_cfg.scope == ScopeEnum.GREENFIELD.value:
        st.info("GREENFIELD MODE ACTIVE: Pump flows and kW will be autonomously calculated based on standard thermodynamics and the Chiller Array TR. Provide Delta-Ts and pump heads below.")
    else:
        st.warning("RETROFIT MODE ACTIVE: You must input the exact audited flows (m³/h). Leave Secondary Flow/Head at blank if the plant operates on a Primary-Only loop.")
    
    with st.form("audit_form"):
        a1, a2, a3 = st.columns(3)
        st.markdown("#### Primary CHW Loop")
        p_head = a1.number_input("Primary Pump Head (m)", value=st.session_state.audit_cfg.run_chw_head_m)
        dt_sup = a2.number_input("CHW Supply (°C)", value=st.session_state.audit_cfg.run_chw_sup_c)
        dt_ret = a3.number_input("CHW Return (°C)", value=st.session_state.audit_cfg.run_chw_ret_c)
        p_flow = a1.number_input("Audited Primary CHW Flow (m³/h)", value=st.session_state.audit_cfg.run_chw_flow_m3h) if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else None
        
        st.markdown("#### Secondary CHW Loop")
        s_head = a1.number_input("Secondary Pump Head (m)", value=st.session_state.audit_cfg.run_sec_chw_head_m)
        s_flow = a2.number_input("Audited Secondary CHW Flow (m³/h)", value=st.session_state.audit_cfg.run_sec_chw_flow_m3h) if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else None
        
        st.markdown("#### Condenser Water Loop")
        c_head = a1.number_input("CW Pump Head (m)", value=st.session_state.audit_cfg.run_cw_head_m)
        c_sup = a2.number_input("CW Supply (°C)", value=st.session_state.audit_cfg.run_cw_sup_c)
        c_ret = a3.number_input("CW Return (°C)", value=st.session_state.audit_cfg.run_cw_ret_c)
        c_flow = a1.number_input("Audited CW Flow (m³/h)", value=st.session_state.audit_cfg.run_cw_flow_m3h) if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else None
        ct_fan = a2.number_input("Audited CT Fan Power (kW)", value=st.session_state.audit_cfg.run_ct_fan_kw) if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else None
        
        if st.form_submit_button("💾 Save Plant Hydraulics", use_container_width=True):
            st.session_state.audit_cfg.run_chw_head_m = p_head
            st.session_state.audit_cfg.run_sec_chw_head_m = s_head
            st.session_state.audit_cfg.run_cw_head_m = c_head
            st.session_state.audit_cfg.run_chw_sup_c, st.session_state.audit_cfg.run_chw_ret_c = dt_sup, dt_ret
            st.session_state.audit_cfg.run_cw_sup_c, st.session_state.audit_cfg.run_cw_ret_c = c_sup, c_ret
            if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value:
                st.session_state.audit_cfg.run_chw_flow_m3h = p_flow
                st.session_state.audit_cfg.run_sec_chw_flow_m3h = s_flow
                st.session_state.audit_cfg.run_cw_flow_m3h = c_flow
                st.session_state.audit_cfg.run_ct_fan_kw = ct_fan
            st.success("Hydraulic Data Locked! ✅")

    st.markdown("---")
    st.subheader("🏭 Installed / Proposed Chiller Fleet Array")
    st.session_state.chiller_fleet = st.data_editor(
        st.session_state.chiller_fleet, num_rows="dynamic", use_container_width=True,
        column_config={"Chiller Type": st.column_config.SelectboxColumn("Chiller Type", options=[t.value for t in ChillerTypeEnum], required=True)}
    )

with t3:
    st.header("📊 Interactive Load & Tariff Profile")
    with st.form("load_profile_form"):
        edited_df = st.data_editor(st.session_state.df_24h, num_rows="fixed", use_container_width=True, hide_index=True)
        if st.form_submit_button("💾 Save Load & Tariff Profile", use_container_width=True):
            st.session_state.df_24h = edited_df
            st.success("Profile saved successfully!")

def render_output_tab(data_dict, title_prefix, curr):
    st.header(title_prefix)
    if data_dict.get('status') == "NOT RECOMMENDED":
        st.error(f"❌ This configuration was evaluated but rejected. (ROI > 4.0 Years or Engineering Constraints Failed).")
    elif data_dict.get('status') == "RECOMMENDED":
        st.success(f"✅ Recommended Configuration Passed All Constraints.")
        
    c1, c2, c3 = st.columns(3)
    c1.metric("Turnkey CAPEX", format_currency(data_dict.get('capex'), curr))
    c2.metric("Annual OPEX", format_currency(data_dict.get('opex'), curr))
    if 'sav' in data_dict: c3.metric("Annual Savings", format_currency(data_dict['sav'], curr), delta=f"Payback: {data_dict.get('pb', 0):.2f} Yrs")
    else: c3.metric("Status", data_dict.get('status', 'BASELINE'))
        
    st.markdown("#### ⚡ Granular Hourly Output Matrix")
    sim = data_dict['sim']
    df_out = pd.DataFrame({
        "Hour": np.arange(1, 25),
        "Cooling Load (TR)": sim["cooling_tr"],
        "Charge TR": sim.get("charge_tr", [0]*24),
        "Discharge TR": sim.get("discharge_tr", [0]*24),
        "Base Chiller TR": sim["op_chiller_tr"],
        "Loading Factor (%)": sim["loading_factor"],
        "Compressors (kW)": sim["comp_kw"],
        "CHW Pri Pumps (kW)": sim["chw_pri_kw"],
        "CHW Sec Pumps (kW)": sim["chw_sec_kw"],
        "CW Pumps (kW)": sim["cw_pump_kw"],
        "CT Fans (kW)": sim["ct_fan_kw"],
        "Total Demand (kW)": sim["total_kw"],
        "ToU Tariff (₹)": sim["tariff"],
        "Hourly OPEX (₹)": sim["hourly_cost"]
    })
    st.dataframe(df_out.round(2), use_container_width=True)

with t4:
    if st.session_state.opt_results: render_output_tab(st.session_state.opt_results['c'], "🏭 Conventional Baseline", st.session_state.proj_cfg.currency)

with t5:
    if st.session_state.opt_results: render_output_tab(st.session_state.opt_results['p'], f"🧊 PCM TES Optimum ({st.session_state.opt_results['p'].get('tes_trh', 0):.0f} TRh)", st.session_state.proj_cfg.currency)

with t6:
    if st.session_state.opt_results: render_output_tab(st.session_state.opt_results['s'], f"🌊 Stratified TES Optimum ({st.session_state.opt_results['s'].get('tes_trh', 0):.0f} TRh)", st.session_state.proj_cfg.currency)

with t7:
    if st.session_state.opt_results:
        res = st.session_state.opt_results
        curr = st.session_state.proj_cfg.currency
        st.header("💰 Executive Summary & Financial Comparison")
        comp_summary = pd.DataFrame([
            {"Parameter": "Status", "Conventional / Existing": res['c'].get('status',''), "PCM TES Option": res['p'].get('status',''), "Stratified TES Option": res['s'].get('status','')},
            {"Parameter": "Base Chiller Sizing", "Conventional / Existing": f"{res['c'].get('base_chiller_tr', 0):.0f} TR", "PCM TES Option": f"{res['p'].get('base_chiller_tr', 0):.0f} TR", "Stratified TES Option": f"{res['s'].get('base_chiller_tr', 0):.0f} TR"},
            {"Parameter": "TES Capacity (TRh)", "Conventional / Existing": "0 TRh", "PCM TES Option": f"{res['p'].get('tes_trh', 0):.0f} TRh", "Stratified TES Option": f"{res['s'].get('tes_trh', 0):.0f} TRh"},
            {"Parameter": "Turnkey CAPEX", "Conventional / Existing": format_currency(res['c'].get('capex',0), curr), "PCM TES Option": format_currency(res['p'].get('cap',{}).get('Total CAPEX',0), curr), "Stratified TES Option": format_currency(res['s'].get('cap',{}).get('Total CAPEX',0), curr)},
            {"Parameter": "Annual OPEX", "Conventional / Existing": format_currency(res['c'].get('opex',0), curr), "PCM TES Option": format_currency(res['p'].get('opex',0), curr), "Stratified TES Option": format_currency(res['s'].get('opex',0), curr)},
            {"Parameter": "Annual Savings", "Conventional / Existing": "-", "PCM TES Option": format_currency(res['p'].get('sav',0), curr), "Stratified TES Option": format_currency(res['s'].get('sav',0), curr)},
            {"Parameter": "Simple Payback Period", "Conventional / Existing": "N/A", "PCM TES Option": f"{res['p'].get('payback', 0):.2f} Years", "Stratified TES Option": f"{res['s'].get('payback', 0):.2f} Years"}
        ])
        st.table(comp_summary)
        
        st.markdown("---")
        st.subheader("🏗️ Strict 8-Key CAPEX Breakup")
        keys = ["Chiller Equip.", "TES System", "Pumps & PHE", "Electrical", "Water Infra", "Transformer", "DG Set", "Indirects / AMC"]
        df_bk = pd.DataFrame({
            "Line Item": keys,
            "Conventional Baseline": [format_currency(res['c'].get('bk', {}).get(k), curr) for k in keys],
            "PCM TES Option": [format_currency(res['p'].get('cap', {}).get('Breakdown', {}).get(k), curr) for k in keys],
            "Stratified TES Option": [format_currency(res['s'].get('cap', {}).get('Breakdown', {}).get(k), curr) for k in keys]
        })
        st.table(df_bk)
        
        st.markdown("---")
        c1, c2 = st.columns(2)
        c1.download_button("📥 Export PDF Executive Briefing", data=generate_pdf_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name=f"CETP_Report_{st.session_state.proj_cfg.project_name}.pdf")
        c2.download_button("📥 Export Word Executive Briefing", data=generate_word_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name=f"CETP_Report_{st.session_state.proj_cfg.project_name}.docx")