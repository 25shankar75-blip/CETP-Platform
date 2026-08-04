# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import gc

from schemas import ProjectConfig, ThermoConfig, HydraulicConfig, FinancialConfig, CURRENCY_MULTIPLIERS, CURRENCY_SYMBOLS
from physics_engine import expand_24_to_8760
from optimizer import run_8760_simulation
from financial_engine import format_currency
from report_generator import generate_pdf_report

st.set_page_config(page_title="CETP Digital Twin", page_icon="❄️", layout="wide")
st.title("❄️ Cooling Energy Transition Platform (CETP)")

DEFAULT_LOAD = [60, 60, 60, 60, 60, 60, 80, 90, 100, 100, 100, 100, 100, 100, 90, 90, 80, 80, 70, 70, 60, 60, 60, 60]
DEFAULT_TARIFF = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2

st.sidebar.header("🛠️ Input Master Suite")
proj_name = st.sidebar.text_input("Project Name", "Ujjain Pharma Baseline")
scope = st.sidebar.radio("Project Scope", ["Greenfield", "Brownfield (Retrofit)"])
currency = st.sidebar.selectbox("Currency Unit", list(CURRENCY_MULTIPLIERS.keys()))
mult = CURRENCY_MULTIPLIERS[currency]
sym = CURRENCY_SYMBOLS[currency]
peak_load_tr = st.sidebar.number_input("Peak Cooling Load (TR)", value=2794.18)

# 24-Hour Editor (with Delta Tracking retained)
if "df_24" not in st.session_state or st.session_state.get("pk") != peak_load_tr:
    st.session_state["df_24"] = pd.DataFrame({
        "Hour": [f"Hr {i}" for i in range(24)],
        "Load (%)": DEFAULT_LOAD,
        "Load (TR)": [(p/100)*peak_load_tr for p in DEFAULT_LOAD],
        f"Tariff ({sym})": [t*mult for t in DEFAULT_TARIFF]
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

rates = {'water_cooled_chiller': 17000*mult, 'brine_chiller': 23000*mult, 'pcm_tes_cylindrical': 7533*mult, 'strat_tes': 18000*mult, 'cooling_tower': 2200*mult, 'chw_pump': 700*mult, 'cdw_pump': 550*mult, 'brine_pump': 900*mult, 'phe': 1100*mult, 'dg_set': 11000*mult, 'transformer': 1700*mult}

if st.button("🚀 Run 8,760-Hour Simulation", type="primary", use_container_width=True):
    with st.spinner("Executing Mathematical Optimization..."):
        config = type("Mock", (object,), {
            "project": ProjectConfig(project_name=proj_name, scope=scope, currency=currency, peak_load_tr=peak_load_tr),
            "thermo": ThermoConfig(), "hydraulic": HydraulicConfig(),
            "financial": FinancialConfig(demand_charge_per_kva_month=475*mult)
        })
        
        results = run_8760_simulation(expand_24_to_8760(load_arr), expand_24_to_8760(tar_arr), config, rates)
        
        # RESTORED: Exhaustive Tabs for Detailed Outputs
        st.subheader("🖥️ Executive Dashboard & Simulation Tabs")
        t1, t2, t3 = st.tabs(["Conventional N+1", "PCM TES System", "Stratified CHW TES"])
        
        def render_tab_content(sys_name, data):
            colA, colB, colC = st.columns(3)
            with colA:
                st.metric("Primary Base Chiller", f"{data['Base_TR']:,.0f} TR")
                if data['Brine_TR'] > 0: st.metric("Sub-Zero Brine Chiller", f"{data['Brine_TR']:,.0f} TR")
                st.metric("TES Storage Volume", f"{data['TES_TRh']:,.0f} TRh")
                st.metric("Electrical Substation Needed", f"{data['Sub_kVA']:,.0f} kVA")
            with colB:
                st.metric("Daily Off-Peak Charge", f"{data['Charge_TRh']:,.0f} TRh")
                st.metric("Daily Peak Discharge", f"{data['Discharge_TRh']:,.0f} TRh")
                st.metric("Total Plant Peak Power", f"{data['Peak_kW']:,.1f} kW")
            with colC:
                st.metric("Total Turnkey CAPEX", format_currency(data['CAPEX']['Total_CAPEX'], currency))
                st.metric("Total Annual OPEX", format_currency(data['Tot_OPEX'], currency))
                if sys_name != "Conventional N+1":
                    st.metric("Annual OPEX Savings", format_currency(data['Savings'], currency))
                    st.metric("ROI / Simple Payback", f"{data['Payback']:.2f} Years" if data['Payback'] > 0 else "Instant (Negative Premium)")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(range(24)), y=data['Total_kW'][:24], name='Dispatch Power (kW)', fill='tozeroy', marker_color="#1E3A8A"))
            fig.update_layout(title=f"24-Hour Power Curve: {sys_name}", height=300, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with t1: render_tab_content("Conventional N+1", results["Conventional N+1"])
        with t2: render_tab_content("PCM TES", results["PCM TES"])
        with t3: render_tab_content("Stratified TES", results["Stratified TES"])

        pdf = generate_pdf_report({"project_name": proj_name, "currency": currency}, results)
        st.download_button("📄 Download Executive Proposal", data=pdf, file_name="CETP_Report.pdf", mime="application/pdf")
        gc.collect()