"""
CETP Digital Twin - Master Streamlit Frontend
File: app.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import json

from schemas import CURRENCY_MULTIPLIERS, ProjectConfig, AuditConfig, FinancialConfig, ChillerTypeEnum
from physics_engine import calc_tr, calc_pump_kw
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report 

st.set_page_config(page_title="CETP Digital Twin", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

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
        {"Capacity (TR)": 1000.0, "Quantity": 2, "Chiller Type": "Water-Cooled Centrifugal", "ikW/TR": 0.62},
        {"Capacity (TR)": 800.0, "Quantity": 1, "Chiller Type": "Water-Cooled VFD Screw", "ikW/TR": 0.65}
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
        st.sidebar.error("Invalid format")

scenario_data = {"df_24h": st.session_state.df_24h.to_dict(), "chiller_fleet": st.session_state.chiller_fleet.to_dict()}
st.sidebar.download_button("💾 Save Project (.json)", json.dumps(scenario_data), "CETP_Scenario.json", "application/json", use_container_width=True)

st.sidebar.markdown("---")
# EXPLICIT RUN BUTTON
if st.sidebar.button("▶️ Run Digital Twin Optimization", type="primary", use_container_width=True):
    rates_dict = st.session_state.fin_cfg.dict()
    audit_dict = st.session_state.audit_cfg.dict()
    st.session_state.opt_results = optimize_plant(
        st.session_state.chiller_fleet, 
        st.session_state.df_24h["Cooling Load (TR)"].values, 
        st.session_state.df_24h["Tariff (₹/kWh)"].values, 
        st.session_state.proj_cfg.scope, 
        audit_dict, rates_dict,
        st.session_state.proj_cfg.running_days
    )
    st.sidebar.success("Optimization Complete! ✅ Check Output Tabs.")

# --- MASTER TABS ---
t1, t2, t3, t4, t5, t6, t7 = st.tabs(["🎛️ Setup & Audit", "📊 Load & Tariffs", "🏭 Baseline Output", "🧊 PCM TES Output", "🌊 Stratified TES Output", "💰 Financials & Exec", "📄 Export"])

with t1:
    st.subheader("Global Settings")
    c1, c2, c3 = st.columns(3)
    st.session_state.proj_cfg.project_name = c1.text_input("Project Name", st.session_state.proj_cfg.project_name)
    st.session_state.proj_cfg.scope = c2.selectbox("Project Scope", ["Greenfield", "Brownfield (Retrofit)"], index=1)
    st.session_state.proj_cfg.currency = c3.selectbox("Currency", list(CURRENCY_MULTIPLIERS.keys()))
    st.session_state.proj_cfg.running_days = c1.number_input("Annual Running Days", value=st.session_state.proj_cfg.running_days, min_value=1, max_value=365)

    if st.session_state.proj_cfg.scope == "Brownfield (Retrofit)":
        st.markdown("---")
        st.header("🔍 Retrofit Audit (Thermodynamic Restoration Engine)")
        st.info("Inputs actual running data. Engine auto-calculates inefficiencies and generates Dual-Benefit Savings (Restoration + Tariff Arbitrage).")
        
        with st.form("audit_form"):
            a1, a2, a3 = st.columns(3)
            sup = a1.number_input("Measured CHW Supply (°C)", value=st.session_state.audit_cfg.run_chw_sup_c)
            ret = a2.number_input("Measured CHW Return (°C)", value=st.session_state.audit_cfg.run_chw_ret_c)
            flow = a3.number_input("Measured CHW Flow (m³/h)", value=st.session_state.audit_cfg.run_chw_flow_m3h)
            
            c_sup = a1.number_input("Measured CW Supply (°C)", value=st.session_state.audit_cfg.run_cw_sup_c)
            c_ret = a2.number_input("Measured CW Return (°C)", value=st.session_state.audit_cfg.run_cw_ret_c)
            c_flow = a3.number_input("Measured CW Flow (m³/h)", value=st.session_state.audit_cfg.run_cw_flow_m3h)
            
            h_chw = a1.number_input("CHW Pump Head (m)", value=st.session_state.audit_cfg.run_chw_head_m)
            h_cw = a2.number_input("CW Pump Head (m)", value=st.session_state.audit_cfg.run_cw_head_m)
            ct_fan = a3.number_input("CT Fan Power (kW)", value=st.session_state.audit_cfg.run_ct_fan_kw)
            
            if st.form_submit_button("Save Audit Data", use_container_width=True):
                st.session_state.audit_cfg.run_chw_sup_c, st.session_state.audit_cfg.run_chw_ret_c, st.session_state.audit_cfg.run_chw_flow_m3h = sup, ret, flow
                st.session_state.audit_cfg.run_cw_sup_c, st.session_state.audit_cfg.run_cw_ret_c, st.session_state.audit_cfg.run_cw_flow_m3h = c_sup, c_ret, c_flow
                st.session_state.audit_cfg.run_chw_head_m, st.session_state.audit_cfg.run_cw_head_m, st.session_state.audit_cfg.run_ct_fan_kw = h_chw, h_cw, ct_fan
                st.success("Audit locked! ✅")

        dt = max(1.0, st.session_state.audit_cfg.run_chw_ret_c - st.session_state.audit_cfg.run_chw_sup_c)
        op_tr = calc_tr(st.session_state.audit_cfg.run_chw_flow_m3h, dt)
        p_kw = calc_pump_kw(st.session_state.audit_cfg.run_chw_flow_m3h, st.session_state.audit_cfg.run_chw_head_m)
        cw_kw = calc_pump_kw(st.session_state.audit_cfg.run_cw_flow_m3h, st.session_state.audit_cfg.run_cw_head_m)
        tot_kw = (op_tr * 0.72) + p_kw + cw_kw + st.session_state.audit_cfg.run_ct_fan_kw
        act_kw_tr = tot_kw / op_tr if op_tr > 0 else 0.95
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Actual Operating Load", f"{op_tr:.1f} TR", delta=f"Delta-T: {dt:.1f} °C")
        m2.metric("Audited Hydraulic Penalty", f"{p_kw + cw_kw:.1f} kW")
        m3.metric("Baseline Inefficiency", f"{act_kw_tr:.3f} kW/TR", delta="Low Delta-T Syndrome", delta_color="inverse")

    st.markdown("---")
    st.subheader("🏭 Installed / Proposed Chiller Fleet")
    st.session_state.chiller_fleet = st.data_editor(
        st.session_state.chiller_fleet, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "Chiller Type": st.column_config.SelectboxColumn("Chiller Type", options=[t.value for t in ChillerTypeEnum], required=True),
            "ikW/TR": st.column_config.NumberColumn("ikW/TR", min_value=0.1, max_value=3.0, format="%.2f", required=True)
        }
    )

with t2:
    st.header("📊 Interactive Load & Tariff Matrices")
    st.session_state.df_24h = st.data_editor(st.session_state.df_24h, num_rows="fixed", use_container_width=True, hide_index=True)

def render_output_tab(data_dict, title_prefix, curr):
    st.header(title_prefix)
    c1, c2, c3 = st.columns(3)
    c1.metric("Turnkey CAPEX", format_currency(data_dict['capex'], curr))
    c2.metric("Annual OPEX", format_currency(data_dict['opex'], curr))
    if 'sav' in data_dict: c3.metric("Annual Savings", format_currency(data_dict['sav'], curr), delta=f"Payback: {data_dict['pb']:.2f} Yrs")
    else: c3.metric("Status", "Baseline Configuration")
        
    st.markdown("#### ⚡ Granular Hourly Equipment Matrix")
    sim = data_dict['sim']
    df_out = pd.DataFrame({
        "Hour": np.arange(1, 25),
        "Cooling TR": sim["cooling_tr"],
        "Charge TR": sim["charge_tr"],
        "Discharge TR": sim["discharge_tr"],
        "Chiller kW": sim["comp_kw"],
        "CHW Pump kW": sim["chw_pump_kw"],
        "CW Pump kW": sim["cw_pump_kw"],
        "CT Fan kW": sim["ct_fan_kw"],
        "Total kW": sim["total_kw"],
        "Tariff (₹)": sim["tariff"],
        "Hourly Cost": sim["hourly_cost"]
    })
    st.dataframe(df_out.round(2), use_container_width=True)

with t3:
    if st.session_state.opt_results:
        prefix = "🏭 Existing Retrofit Baseline (Inefficient)" if st.session_state.proj_cfg.scope == "Brownfield (Retrofit)" else "🏭 Conventional N+1 Baseline"
        render_output_tab(st.session_state.opt_results['c'], prefix, st.session_state.proj_cfg.currency)
    else: st.info("Run Optimizer in the sidebar.")

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
        st.header("💰 Executive Economics & OPEX Breakdown")
        
        # OPEX Breakdown Matrix
        st.subheader("⚡ Annual OPEX Component Breakdown")
        opex_data = []
        for opt_name, k in [("Conventional Baseline", "c"), ("PCM TES Optimum", "p"), ("Stratified TES Optimum", "s")]:
            sim = res[k]["sim"]
            opex_data.append({
                "Option": opt_name,
                "Chiller OPEX": format_currency(calc_annual_cost(sim["comp_kw"], sim["tariff"], days), curr),
                "CHW Pumps OPEX": format_currency(calc_annual_cost(sim["chw_pump_kw"], sim["tariff"], days), curr),
                "CW Pumps OPEX": format_currency(calc_annual_cost(sim["cw_pump_kw"], sim["tariff"], days), curr),
                "CT Fans OPEX": format_currency(calc_annual_cost(sim["ct_fan_kw"], sim["tariff"], days), curr),
                "DG Outage Penalty": format_currency(res[k].get("dg_cost", 0.0), curr),
                "Total OPEX": format_currency(res[k]["opex"], curr)
            })
        st.table(pd.DataFrame(opex_data))

        # CAPEX Breakup
        st.subheader("🏗️ CAPEX Breakup")
        df_bk = pd.DataFrame({
            "Item": list(res['c']['bk'].keys()),
            "Baseline": [format_currency(v, curr) for v in res['c']['bk'].values()],
            "PCM TES Opt.": [format_currency(v, curr) for v in res['p']['bk'].values()],
            "Strat. TES Opt.": [format_currency(v, curr) for v in res['s']['bk'].values()]
        })
        st.table(df_bk)

with t7:
    if st.session_state.opt_results:
        c1, c2 = st.columns(2)
        curr = st.session_state.proj_cfg.currency
        res = st.session_state.opt_results
        c1.download_button("📥 Export PDF Report", data=generate_pdf_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name="CETP.pdf")
        c2.download_button("📥 Export Word Report", data=generate_word_report(st.session_state.proj_cfg.project_name, st.session_state.proj_cfg.location, st.session_state.proj_cfg.scope, curr, res), file_name="CETP.docx")