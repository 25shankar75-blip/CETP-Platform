# app.py
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import gc

from schemas import ProjectConfig, ThermoConfig, HydraulicConfig, FinancialConfig, CURRENCY_MULTIPLIERS
from physics_engine import expand_24_to_8760
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report

st.set_page_config(page_title="CETP Digital Twin Platform", page_icon="❄️", layout="wide")

st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

# DEFAULT PROFILES
DEFAULT_LOAD = [60, 60, 60, 60, 60, 60, 80, 90, 100, 100, 100, 100, 100, 100, 90, 90, 80, 80, 70, 70, 60, 60, 60, 60]
DEFAULT_TARIFF = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2

st.sidebar.header("🛠️ Input Master Suite")
with st.sidebar.expander("📌 Project Details", expanded=True):
    pc = ProjectConfig(
        proj_name=st.text_input("Project Name", "Ujjain Pharma Baseline"),
        location=st.text_input("Location", "MP, India"),
        industry=st.selectbox("Industry Sector", ["Pharmaceuticals", "Data Centre", "Commercial HVAC", "Chemical Process"]),
        proj_type=st.radio("Project Scope", ["Greenfield Project", "Brownfield / Retrofit"]),
        peak_load_tr=st.number_input("Peak Cooling Load (TR)", value=2794.18),
        tank_shape=st.selectbox("Tank Geometry", ["Cylindrical (API 650)", "Rectangular Concrete/Steel"]),
        currency=st.selectbox("Currency Unit", list(CURRENCY_MULTIPLIERS.keys()))
    )
with st.sidebar.expander("🌡️ Thermodynamics"): tc = ThermoConfig(chiller_type=st.selectbox("Chiller Type", ["Water-Cooled (With Cooling Towers)", "Air-Cooled"]))
with st.sidebar.expander("💧 Hydraulics"): hc = HydraulicConfig()
with st.sidebar.expander("💰 Financial Rates"): fc = FinancialConfig(demand_rate=st.number_input("Demand Charge (per kVA)", value=475.0))

sym = CURRENCY_MULTIPLIERS[pc.currency]["symbol"]
mult = CURRENCY_MULTIPLIERS[pc.currency]["rate"]

# FULL 6-TAB RESTORATION
t1, t2, t3, t4, t5, t6 = st.tabs(["⚙️ Input Profiles", "🏢 Conventional N+1", "🧊 PCM TES System", "🌊 Stratified CHW TES", "📊 Executive Summary", "💰 CAPEX Matrix"])

with t1:
    st.subheader("Interactive 24-Hour Diurnal Load & ToU Tariff Data Editor")
    if "df_24" not in st.session_state or st.session_state.get("pk") != pc.peak_load_tr:
        st.session_state["df_24"] = pd.DataFrame({
            "Hour": [f"Hour {i}" for i in range(24)],
            "Load (%)": [float(p) for p in DEFAULT_LOAD],
            "Load (TR)": [(p/100)*pc.peak_load_tr for p in DEFAULT_LOAD],
            f"Tariff ({sym})": [t*mult for t in DEFAULT_TARIFF]
        })
        st.session_state["pk"] = pc.peak_load_tr

    df_edit = st.data_editor(st.session_state["df_24"], use_container_width=True, num_rows="fixed", key="edit_24")
    state = st.session_state.get("edit_24", {}).get("edited_rows", {})
    if state:
        for r, changes in state.items():
            if "Load (%)" in changes: df_edit.at[int(r), "Load (TR)"] = (float(changes["Load (%)"])/100)*pc.peak_load_tr
            if "Load (TR)" in changes: df_edit.at[int(r), "Load (%)"] = (float(changes["Load (TR)"])/pc.peak_load_tr)*100
        st.session_state["df_24"] = df_edit.copy()

    load_arr = df_edit["Load (TR)"].tolist()
    tar_arr = df_edit[f"Tariff ({sym})"].tolist()

st.sidebar.markdown("---")
if st.sidebar.button("🚀 Run 8,760-Hour Simulation", type="primary"):
    with st.spinner("Executing Mathematical Optimization..."):
        prm = {**pc.model_dump(), **tc.model_dump(), **hc.model_dump(), **fc.model_dump(), **fc.unit_rates}
        charge_hrs = {22, 23, 0, 1, 2, 3, 4, 5} # Off-peak window
        
        res = optimize_plant(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), pc.peak_load_tr, charge_hrs, prm, pc.proj_type)
        
        def render_dispatch_chart(data, sys_name, color):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(range(24)), y=data['kw'][:24], name='Plant Power (kW)', fill='tozeroy', marker_color=color))
            fig.update_layout(title=f"24-Hour Electric Power Dispatch: {sys_name}", xaxis_title="Hour of Day", yaxis_title="kW", height=300, margin=dict(l=0, r=0, t=35, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with t2:
            st.subheader("Conventional Chiller Plant (N+1)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Installed Base Chillers", f"{res['c']['cap_base']:,.0f} TR")
            c2.metric("Peak Electrical Demand", f"{res['c']['dem']:,.1f} kW")
            c3.metric("Required Substation & DG", f"{res['c']['dg_kva']:,.0f} kVA")
            c4.metric("Total Annual OPEX", format_currency(res['c']['opex'], pc.currency))
            render_dispatch_chart(res['c'], "Conventional N+1", "#EF4444")

        with t3:
            st.subheader("PCM Thermal Energy Storage")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Downsized Base Chillers", f"{res['p']['cap_base']:,.0f} TR", f"{res['p']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
            c2.metric("Sub-Zero Brine Chillers", f"{res['p']['cap_dual']:,.0f} TR")
            c3.metric("PCM Storage Volume", f"{res['p']['cap_tes']:,.0f} TRh")
            c4.metric("Required Substation & DG", f"{res['p']['dg_kva']:,.0f} kVA", f"{res['p']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Peak Electrical Demand", f"{res['p']['dem']:,.1f} kW", f"{res['p']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
            c6.metric("Daily Peak Discharge", f"{res['p']['disch']:,.0f} TRh")
            c7.metric("Total Annual OPEX", format_currency(res['p']['opex'], pc.currency), f"- {format_currency(res['c']['opex'] - res['p']['opex'], pc.currency)}")
            c8.metric("Simple Payback", f"{res['p']['pb']:.2f} Years" if res['p']['pb']>0 else "Instantaneous")
            render_dispatch_chart(res['p'], "PCM TES", "#10B981")

        with t4:
            st.subheader("Stratified CHW Thermal Storage")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Downsized Base Chillers", f"{res['s']['cap_base']:,.0f} TR", f"{res['s']['cap_base'] - res['c']['cap_base']:,.0f} TR (Savings)")
            c2.metric("Sub-Zero Brine Chillers", "0 TR")
            c3.metric("Stratified Storage Volume", f"{res['s']['cap_tes']:,.0f} TRh")
            c4.metric("Required Substation & DG", f"{res['s']['dg_kva']:,.0f} kVA", f"{res['s']['dg_kva'] - res['c']['dg_kva']:,.0f} kVA (Savings)")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Peak Electrical Demand", f"{res['s']['dem']:,.1f} kW", f"{res['s']['dem'] - res['c']['dem']:,.1f} kW (Savings)")
            c6.metric("Daily Peak Discharge", f"{res['s']['disch']:,.0f} TRh")
            c7.metric("Total Annual OPEX", format_currency(res['s']['opex'], pc.currency), f"- {format_currency(res['c']['opex'] - res['s']['opex'], pc.currency)}")
            c8.metric("Simple Payback", f"{res['s']['pb']:.2f} Years" if res['s']['pb']>0 else "Instantaneous")
            render_dispatch_chart(res['s'], "Stratified CHW TES", "#3B82F6")

        with t5:
            st.subheader("📊 Executive System Comparison")
            df_comp = pd.DataFrame({
                "Parameter": ["Base Chiller (TR)", "Brine Chiller (TR)", "Storage Vol (TRh)", "Peak Demand (kW)", "Substation (kVA)", "Total CAPEX", "Total OPEX", "Payback (Yrs)"],
                "Conventional N+1": [f"{res['c']['cap_base']:,.0f}", "-", "0", f"{res['c']['dem']:,.0f}", f"{res['c']['dg_kva']:,.0f}", format_currency(res['c']['capex'], pc.currency), format_currency(res['c']['opex'], pc.currency), "Baseline"],
                "PCM TES": [f"{res['p']['cap_base']:,.0f}", f"{res['p']['cap_dual']:,.0f}", f"{res['p']['cap_tes']:,.0f}", f"{res['p']['dem']:,.0f}", f"{res['p']['dg_kva']:,.0f}", format_currency(res['p']['capex'], pc.currency), format_currency(res['p']['opex'], pc.currency), f"{res['p']['pb']:.2f}"],
                "Stratified TES": [f"{res['s']['cap_base']:,.0f}", "-", f"{res['s']['cap_tes']:,.0f}", f"{res['s']['dem']:,.0f}", f"{res['s']['dg_kva']:,.0f}", format_currency(res['s']['capex'], pc.currency), format_currency(res['s']['opex'], pc.currency), f"{res['s']['pb']:.2f}"]
            })
            st.table(df_comp)
            
            pdf = generate_pdf_report(pc.proj_name, pc.location, pc.industry, pc.proj_type, pc.currency, df_comp)
            st.download_button("📄 Download Executive Proposal", data=pdf, file_name="CETP_Report.pdf", mime="application/pdf", type="primary")

        with t6:
            st.subheader("💰 Master CAPEX Breakdown")
            df_bk = pd.DataFrame({
                "Category": list(res['c']['bk'].keys()),
                "Conventional N+1": [format_currency(v, pc.currency) for v in res['c']['bk'].values()],
                "PCM TES": [format_currency(v, pc.currency) for v in res['p']['bk'].values()],
                "Stratified TES": [format_currency(v, pc.currency) for v in res['s']['bk'].values()]
            })
            st.table(df_bk)
            
        gc.collect()