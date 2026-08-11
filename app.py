"""
Cooling Energy Transition Platform (CETP) - Master Streamlit Frontend
File: app.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import json

from schemas import CURRENCY_MULTIPLIERS, ProjectConfig, AuditConfig, FinancialConfig, ChillerTypeEnum, ScopeEnum, SectorEnum, TankShapeEnum
from physics_engine import calc_tr, calc_pump_kw, fetch_live_weather_wbt
from financial_engine import fetch_live_currency_rates, format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report 

st.set_page_config(page_title="CETP Digital Twin", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

# --- 🚀 CACHE BUSTER ---
if "fin_cfg" in st.session_state and not hasattr(st.session_state.fin_cfg, "daily_outage_hrs"):
    st.session_state.fin_cfg = FinancialConfig()
if "proj_cfg" in st.session_state and not hasattr(st.session_state.proj_cfg, "tank_shape"):
    st.session_state.proj_cfg = ProjectConfig()
if "audit_cfg" in st.session_state and not hasattr(st.session_state.audit_cfg, "run_sec_chw_flow_m3h"):
    st.session_state.audit_cfg = AuditConfig()

# --- INITIALIZE STATE ---
if "df_24h" not in st.session_state:
    hours = np.arange(1, 25)
    loads = [1047.82]*8 + [1746.36]*2 + [2095.63]*2 + [2794.18]*4 + [2444.90]*4 + [2095.63]*2 + [1047.82]*2
    tariffs = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2
    st.session_state.df_24h = pd.DataFrame({
        "Hour": hours, "Cooling Load (TR)": loads, "Tariff (₹/kWh)": tariffs, " ": [""]*24 
    })
if "chiller_fleet" not in st.session_state:
    st.session_state.chiller_fleet = pd.DataFrame([
        {"Capacity (TR)": 1000.0, "Quantity": 2, "Chiller Type": "Water-Cooled Centrifugal", "ikW/TR": 0.62, "Standby": False},
        {"Capacity (TR)": 800.0, "Quantity": 1, "Chiller Type": "Water-Cooled VFD Screw", "ikW/TR": 0.65, "Standby": True}
    ])
if "proj_cfg" not in st.session_state: st.session_state.proj_cfg = ProjectConfig()
if "audit_cfg" not in st.session_state: st.session_state.audit_cfg = AuditConfig()
if "fin_cfg" not in st.session_state: st.session_state.fin_cfg = FinancialConfig()
if "opt_results" not in st.session_state: st.session_state.opt_results = None

# --- SIDEBAR: EXECUTION & SCENARIO MGMT ---
st.sidebar.title("🎛️ Execution Controls")
st.sidebar.markdown("---")

st.sidebar.subheader("📂 Scenario Management")
uploaded_file = st.sidebar.file_uploader("Upload Project (.json)", type=["json"])
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
    rates_dict = st.session_state.fin_cfg.dict()
    audit_dict = st.session_state.audit_cfg.dict()
    
    with st.spinner("Fetching live weather and optimizing plant physics..."):
        wbt_data = fetch_live_weather_wbt(st.session_state.proj_cfg.location)
        wbt_arr = wbt_data["wbt"]

        st.session_state.opt_results = optimize_plant(
            st.session_state.chiller_fleet, 
            st.session_state.df_24h["Cooling Load (TR)"].values, 
            st.session_state.df_24h["Tariff (₹/kWh)"].values, 
            wbt_arr,
            st.session_state.proj_cfg.scope, 
            audit_dict, 
            rates_dict,
            st.session_state.proj_cfg.running_days,
            st.session_state.proj_cfg.tank_shape
        )
        if wbt_data["status"] == "LIVE":
            st.sidebar.success(f"Live Weather fetched for {st.session_state.proj_cfg.location}! Optimization Complete.")
        else:
            st.sidebar.success("Optimization Complete! (Synthetic Weather Model Used)")

# --- MASTER TABS ---
t1, t2, t3, t4, t5, t6, t7 = st.tabs(["🎛️ Setup & Audit", "📊 Load & Tariffs", "🏭 Baseline Output", "🧊 PCM TES Output", "🌊 Stratified TES Output", "💰 Executive Summary", "📄 Export"])

with t1:
    st.subheader("Global Settings")
    c1, c2, c3, c4 = st.columns(4)
    st.session_state.proj_cfg.project_name = c1.text_input("Project Name", st.session_state.proj_cfg.project_name)
    st.session_state.proj_cfg.scope = c2.selectbox("Project Scope", [ScopeEnum.GREENFIELD.value, ScopeEnum.BROWNFIELD.value], index=1 if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else 0)
    st.session_state.proj_cfg.currency = c3.selectbox("Currency", list(CURRENCY_MULTIPLIERS.keys()))
    st.session_state.proj_cfg.tank_shape = c4.selectbox("PCM Tank Geometry", [TankShapeEnum.CYLINDRICAL.value, TankShapeEnum.RECTANGULAR.value])
    
    c1, c2, c3 = st.columns(3)
    st.session_state.proj_cfg.running_days = c1.number_input("Annual Running Days", value=st.session_state.proj_cfg.running_days, min_value=1, max_value=365)
    st.session_state.audit_cfg.water_cost_per_m3 = c2.number_input("Water Cost (₹/m³)", value=st.session_state.audit_cfg.water_cost_per_m3)
    st.session_state.fin_cfg.daily_outage_hrs = float(c3.number_input("Daily Power Outage (Hrs)", value=float(st.session_state.fin_cfg.daily_outage_hrs)))

    st.markdown("---")
    st.subheader("💰 CAPEX Rate Inputs (Overrides)")
    with st.expander("Expand to modify baseline hardware & infrastructure rates"):
        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.base_chiller_rate = r1.number_input("Base Chiller Rate (₹/TR)", value=float(st.session_state.fin_cfg.base_chiller_rate))
        st.session_state.fin_cfg.ac_chiller_rate = r2.number_input("Air-Cooled Chiller Rate (₹/TR)", value=float(st.session_state.fin_cfg.ac_chiller_rate))
        st.session_state.fin_cfg.brine_chiller_rate = r3.number_input("Brine Chiller Rate (₹/TR)", value=float(st.session_state.fin_cfg.brine_chiller_rate))
        
        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.pcm_cyl_rate = r1.number_input("PCM Cylindrical Rate (₹/TRh)", value=float(st.session_state.fin_cfg.pcm_cyl_rate))
        st.session_state.fin_cfg.pcm_rect_rate = r2.number_input("PCM Rectangular Rate (₹/TRh)", value=float(st.session_state.fin_cfg.pcm_rect_rate))
        st.session_state.fin_cfg.stratified_tes_rate = r3.number_input("Stratified TES Rate (₹/TRh)", value=float(st.session_state.fin_cfg.stratified_tes_rate))

        r1, r2, r3 = st.columns(3)
        st.session_state.fin_cfg.dg_set_rate = r1.number_input("DG Set Rate (₹/TR)", value=float(st.session_state.fin_cfg.dg_set_rate))
        st.session_state.fin_cfg.transformer_rate = r2.number_input("Transformer Rate (₹/TR)", value=float(st.session_state.fin_cfg.transformer_rate))
        st.session_state.fin_cfg.water_infra_rate = r3.number_input("Water Infra Rate (₹/TR)", value=float(st.session_state.fin_cfg.water_infra_rate))

        r1, r2 = st.columns(2)
        st.session_state.fin_cfg.indirects_pct = r1.number_input("Indirects / AMC (%)", value=float(st.session_state.fin_cfg.indirects_pct), step=0.01)
        st.session_state.fin_cfg.dg_diesel_cost_kwh = r2.number_input("DG Diesel Cost (₹/kWh)", value=float(st.session_state.fin_cfg.dg_diesel_cost_kwh))

    st.markdown("---")
    st.header("🔍 Hydraulic Input Suite")
    if st.session_state.proj_cfg.scope == ScopeEnum.GREENFIELD.value:
        st.info("GREENFIELD MODE ACTIVE: Pump flows and kW will be autonomously calculated based on standard thermodynamics and the Chiller Array TR. Provide Delta-Ts and pump heads below.")
    else:
        st.warning("RETROFIT MODE ACTIVE: You must input the exact audited flows (m³/h). Leave Secondary Flow/Head at 0 if the plant operates on a Primary-Only loop.")
    
    with st.form("audit_form"):
        a1, a2, a3 = st.columns(3)
        st.markdown("#### Primary CHW Loop")
        p_head = a1.number_input("Primary Pump Head (m)", value=st.session_state.audit_cfg.run_chw_head_m)
        dt_sup = a2.number_input("CHW Supply (°C)", value=st.session_state.audit_cfg.run_chw_sup_c)
        dt_ret = a3.number_input("CHW Return (°C)", value=st.session_state.audit_cfg.run_chw_ret_c)
        if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value:
            p_flow = a1.number_input("Audited Primary CHW Flow (m³/h)", value=st.session_state.audit_cfg.run_chw_flow_m3h)
        
        st.markdown("#### Secondary CHW Loop")
        s_head = a1.number_input("Secondary Pump Head (m)", value=st.session_state.audit_cfg.run_sec_chw_head_m)
        if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value:
            s_flow = a2.number_input("Audited Secondary CHW Flow (m³/h)", value=st.session_state.audit_cfg.run_sec_chw_flow_m3h)
        
        st.markdown("#### Condenser Water Loop")
        c_head = a1.number_input("CW Pump Head (m)", value=st.session_state.audit_cfg.run_cw_head_m)
        c_sup = a2.number_input("CW Supply (°C)", value=st.session_state.audit_cfg.run_cw_sup_c)
        c_ret = a3.number_input("CW Return (°C)", value=st.session_state.audit_cfg.run_cw_ret_c)
        if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value:
            c_flow = a1.number_input("Audited CW Flow (m³/h)", value=st.session_state.audit_cfg.run_cw_flow_m3h)
            ct_fan = a2.number_input("Audited CT Fan Power (kW)", value=st.session_state.audit_cfg.run_ct_fan_kw)
        
        if st.form_submit_button("Save Plant Hydraulics", use_container_width=True):
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
    
    active_fleet = st.session_state.chiller_fleet[st.session_state.chiller_fleet["Standby"] == False] if "Standby" in st.session_state.chiller_fleet.columns else st.session_state.chiller_fleet
    tot_chiller_tr = sum(st.session_state.chiller_fleet["Capacity (TR)"] * st.session_state.chiller_fleet["Quantity"])
    tot_active_tr = sum(active_fleet["Capacity (TR)"] * active_fleet["Quantity"])

    a1, a2, a3 = st.columns(3)
    a1.metric("Total Installed Chiller Sizing (N+1)", f"{tot_chiller_tr:.0f} TR")
    a2.metric("Active Working Capacity", f"{tot_active_tr:.0f} TR")

    st.session_state.chiller_fleet = st.data_editor(
        st.session_state.chiller_fleet, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "Chiller Type": st.column_config.SelectboxColumn("Chiller Type", options=[t.value for t in ChillerTypeEnum], required=True),
            "ikW/TR": st.column_config.NumberColumn("ikW/TR", min_value=0.1, max_value=3.0, format="%.2f", required=True),
            "Standby": st.column_config.CheckboxColumn("Standby Chiller", default=False)
        }
    )

with t2:
    st.header("📊 Interactive Load & Tariff Profile")
    st.info("Edit your hourly loads and tariffs below. Click 'Save Load Profile' to commit your changes without triggering UI refresh bugs.")
    
    with st.form("load_profile_form"):
        edited_df = st.data_editor(st.session_state.df_24h, num_rows="fixed", use_container_width=True, hide_index=True)
        if st.form_submit_button("💾 Save Load & Tariff Profile", use_container_width=True):
            st.session_state.df_24h = edited_df
            st.success("Profile saved successfully! You can now run the Digital Twin Optimization in the sidebar.")

def render_output_tab(data_dict, title_prefix, curr):
    st.header(title_prefix)
    c1, c2, c3 = st.columns(3)
    c1.metric("Turnkey CAPEX", format_currency(data_dict['capex'], curr))
    c2.metric("Annual OPEX", format_currency(data_dict['opex'], curr))
    if 'sav' in data_dict: c3.metric("Annual Savings", format_currency(data_dict['sav'], curr), delta=f"Payback: {data_dict['pb']:.2f} Yrs")
    else: c3.metric("Status", "Baseline Configuration")
        
    st.markdown("#### ⚡ Granular 14-Column Hourly Output Matrix")
    sim = data_dict['sim']
    df_out = pd.DataFrame({
        "Hour": np.arange(1, 25),
        "Cooling Load (TR)": sim["cooling_tr"],
        "Charge TR": sim["charge_tr"],
        "Discharge TR": sim["discharge_tr"],
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

with t3:
    if st.session_state.opt_results:
        prefix = "🏭 Existing Retrofit Baseline" if st.session_state.proj_cfg.scope == ScopeEnum.BROWNFIELD.value else "🏭 Conventional N+1 Baseline"
        render_output_tab(st.session_state.opt_results['c'], prefix, st.session_state.proj_cfg.currency)
    else: st.info("Please click '▶️ Run Digital Twin Optimization' in the sidebar.")

with t4:
    if st.session_state.opt_results: render_output_tab(st.session_state.opt_results['p'], f"🧊 PCM TES Optimum ({st.session_state.opt_results['p']['tes_trh']:.0f} TRh) - {st.session_state.opt_results['p'].get('num_tanks',1)} Tank(s)", st.session_state.proj_cfg.currency)

with t5:
    if st.session_state.opt_results: render_output_tab(st.session_state.opt_results['s'], f"🌊 Stratified TES Optimum ({st.session_state.opt_results['s']['tes_trh']:.0f} TRh) - {st.session_state.opt_results['s'].get('num_tanks',1)} Tank(s)", st.session_state.proj_cfg.currency)

def calc_annual_cost(kw_array, tariff_array, days):
    return np.sum(np.array(kw_array) * np.array(tariff_array)) * days

with t6:
    if st.session_state.opt_results:
        res = st.session_state.opt_results
        curr = st.session_state.proj_cfg.currency
        days = st.session_state.proj_cfg.running_days
        st.header("💰 Executive Summary & Financial Comparison")
        
        st.subheader("📊 Technical & Financial Master Comparison")
        comp_summary = pd.DataFrame([
            {
                "Parameter": "Peak Load (TR)",
                "Conventional / Existing": f"{st.session_state.proj_cfg.peak_tr:.1f} TR",
                "PCM TES Option": f"{st.session_state.proj_cfg.peak_tr:.1f} TR",
                "Stratified TES Option": f"{st.session_state.proj_cfg.peak_tr:.1f} TR"
            },
            {
                "Parameter": "Base Chiller Sizing",
                "Conventional / Existing": f"{res['c'].get('base_chiller_tr', 0):.0f} TR",
                "PCM TES Option": f"{res['p'].get('base_chiller_tr', 0):.0f} TR",
                "Stratified TES Option": f"{res['s'].get('base_chiller_tr', 0):.0f} TR"
            },
            {
                "Parameter": "TES Capacity (TRh)",
                "Conventional / Existing": "0 TRh",
                "PCM TES Option": f"{res['p']['tes_trh']:.0f} TRh ({res['p']['num_tanks']} Tank)",
                "Stratified TES Option": f"{res['s']['tes_trh']:.0f} TRh ({res['s']['num_tanks']} Tank)"
            },
            {
                "Parameter": "Brine Chiller Sourcing",
                "Conventional / Existing": "N/A",
                "PCM TES Option": f"{res['p'].get('new_chiller_tr',0):.0f} TR New ({res['p'].get('chiller_tr',0):.0f} TR Total)",
                "Stratified TES Option": "N/A (Spare Fleet Charging)"
            },
            {
                "Parameter": "Annual Water Consumption (m³)",
                "Conventional / Existing": f"{res['c']['sim']['water_m3']:.0f} m³",
                "PCM TES Option": f"{res['p']['sim']['water_m3']:.0f} m³",
                "Stratified TES Option": f"{res['s']['sim']['water_m3']:.0f} m³"
            },
            {
                "Parameter": "DG Grid Offsetting Savings",
                "Conventional / Existing": "Baseline",
                "PCM TES Option": format_currency(res['p']['grid_offset'], curr),
                "Stratified TES Option": format_currency(res['s']['grid_offset'], curr)
            },
            {
                "Parameter": "Turnkey CAPEX",
                "Conventional / Existing": format_currency(res['c']['capex'], curr),
                "PCM TES Option": format_currency(res['p']['capex'], curr),
                "Stratified TES Option": format_currency(res['s']['capex'], curr)
            },
            {
                "Parameter": "Total Annual OPEX (Power + Water + Diesel)",
                "Conventional / Existing": format_currency(res['c']['opex'], curr),
                "PCM TES Option": format_currency(res['p']['opex'], curr),
                "Stratified TES Option": format_currency(res['s']['opex'], curr)
            },
            {
                "Parameter": "Annual Net OPEX Savings",
                "Conventional / Existing": "Baseline",
                "PCM TES Option": format_currency(res['p']['sav'], curr),
                "Stratified TES Option": format_currency(res['s']['sav'], curr)
            },
            {
                "Parameter": "Simple Payback Period",
                "Conventional / Existing": "N/A",
                "PCM TES Option": f"{res['p']['pb']:.2f} Years",
                "Stratified TES Option": f"{res['s']['pb']:.2f} Years"
            },
            {
                "Parameter": "CO₂ Offset (Tonnes/Yr)",
                "Conventional / Existing": "0.0 Tonnes",
                "PCM TES Option": f"{res['p']['co2']:.1f} Tonnes/Yr",
                "Stratified TES Option": f"{res['s']['co2']:.1f} Tonnes/Yr"
            }
        ])
        st.table(comp_summary)

        st.markdown("---")
        st.subheader("⚡ Annual OPEX Component Breakdown")
        opex_data = []
        for opt_name, k in [("Conventional Baseline", "c"), ("PCM TES Optimum", "p"), ("Stratified TES Optimum", "s")]:
            sim = res[k]["sim"]
            opex_data.append({
                "Option": opt_name,
                "Chiller OPEX": format_currency(calc_annual_cost(sim["comp_kw"], sim["tariff"], days), curr),
                "CHW Primary Pumps OPEX": format_currency(calc_annual_cost(sim["chw_pri_kw"], sim["tariff"], days), curr),
                "CHW Secondary Pumps OPEX": format_currency(calc_annual_cost(sim["chw_sec_kw"], sim["tariff"], days), curr),
                "CW Pumps OPEX": format_currency(calc_annual_cost(sim["cw_pump_kw"], sim["tariff"], days), curr),
                "CT Fans OPEX": format_currency(calc_annual_cost(sim["ct_fan_kw"], sim["tariff"], days), curr),
                "Water OPEX": format_currency(res[k]["water_cost"], curr),
                "DG Diesel OPEX": format_currency(res[k]["dg_cost"], curr),
                "Total OPEX": format_currency(res[k]["opex"], curr)
            })
        st.table(pd.DataFrame(opex_data))

        st.markdown("---")
        st.subheader("🏗️ CAPEX Breakup")
        
        keys = ["Chiller Equip.", "TES Tank", "PCM Media", "Pumps & PHE", "Electrical", "Water Infra", "Transformer", "DG Set", "Indirects / AMC"]
        
        b_c = [format_currency(res['c']['bk'].get(k, 0.0), curr) for k in keys]
        b_p = [format_currency(res['p']['bk'].get(k, 0.0), curr) for k in keys]
        b_s = [format_currency(res['s']['bk'].get(k, 0.0), curr) for k in keys]
        
        df_bk = pd.DataFrame({
            "Line Item": keys,
            "Conventional Baseline": b_c,
            "PCM TES Option": b_p,
            "Stratified TES Option": b_s
        })
        st.table(df_bk)

with t7:
    if st.session_state.opt_results:
        c1, c2 = st.columns(2)
        curr = st.session_state.proj_cfg.currency
        res = st.session_state.opt_results
        c1.download_button("📥 Export PDF Executive Briefing", data=generate_pdf_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name=f"CETP_Report_{st.session_state.proj_cfg.project_name}.pdf")
        c2.download_button("📥 Export Word Executive Briefing", data=generate_word_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name=f"CETP_Report_{st.session_state.proj_cfg.project_name}.docx")