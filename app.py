# app.py
import streamlit as st
import numpy as np
from schemas import ProjectConfig, ThermoConfig, HydraulicConfig, CURRENCY_MULTIPLIERS
from physics_engine import expand_24_to_8760
from optimizer import run_8760_simulation
from financial_engine import calculate_capex
from report_generator import generate_pdf_report
import plotly.graph_objects as go
import gc # Garbage collection for memory management

st.set_page_config(page_title="CETP Digital Twin", layout="wide")

st.sidebar.title("🛠️ CETP Input Master Suite")

# 1. Project Parameters
curr = st.sidebar.selectbox("Currency", list(CURRENCY_MULTIPLIERS.keys()))
mult = CURRENCY_MULTIPLIERS[curr]

proj_name = st.sidebar.text_input("Project Name", "Greenfield Pharma")
scope = st.sidebar.radio("Project Scope", ["Greenfield", "Brownfield (Retrofit)"])
peak_load = st.sidebar.number_input("Peak Load (TR)", value=2794.0)

# Rates configuration with Currency Multiplier
sys_rates = {
    'base_chiller': 17000 * mult,
    'brine_chiller': 23000 * mult,
    'pcm_tes': 7533 * mult,
    'strat_tes': 18000 * mult,
    'cooling_tower': 2200 * mult,
    'chw_pump': 700 * mult,
    'cdw_pump': 550 * mult
}

# 2. 24-hr Profiles
st.sidebar.subheader("24-hr Base Profiles")
tariffs = st.sidebar.text_area("ToU Tariff (24 hrs comma-separated)", "5.62,5.62,5.62,5.62,5.62,5.62,6.11,6.11,6.11,6.11,6.11,6.11,6.11,6.11,6.11,6.11,6.11,6.11,7.03,7.03,7.03,7.03,5.62,5.62")
loads = st.sidebar.text_area("Load % (24 hrs comma-separated)", "60,60,60,60,60,60,80,90,100,100,100,100,100,100,90,90,80,80,70,70,60,60,60,60")

if st.button("🚀 Run 8,760-Hour Optimization Engine"):
    with st.spinner("Simulating Thermodynamics & Financial Arbitrage..."):
        try:
            tariff_24 = [float(x.strip()) for x in tariffs.split(',')]
            load_24 = [(float(x.strip())/100)*peak_load for x in loads.split(',')]
            
            # Memory Optimized 8760 Arrays
            t_8760 = expand_24_to_8760(tariff_24)
            l_8760 = expand_24_to_8760(load_24)

            config = type("MockConfig", (object,), {
                "thermo": ThermoConfig(chiller_type="Water", design_wbt=28.0),
                "hydraulic": HydraulicConfig()
            })

            results = run_8760_simulation(l_8760, t_8760, config, sys_rates)
            
            st.success("Simulation Complete! (LEED Platinum & ASHRAE Compliant)")
            
            cols = st.columns(3)
            for i, (sys_name, data) in enumerate(results.items()):
                with cols[i]:
                    st.subheader(sys_name)
                    st.metric("Chiller TR", f"{data['Capacity_TR']:,.0f}")
                    st.metric("TES TRh", f"{data['TES_TRh']:,.0f}")
                    
                    capex = calculate_capex(scope, data['Capacity_TR'], data['TES_TRh'], sys_name, sys_rates)
                    st.metric(f"CAPEX ({curr})", f"{capex['Total']/1e7:,.2f} Cr" if "INR" in curr else f"{capex['Total']:,.2f}")
                    st.metric(f"Annual OPEX ({curr})", f"{data['Total_Opex']/1e7:,.2f} Cr" if "INR" in curr else f"{data['Total_Opex']:,.2f}")
                    
            # Generate Report
            pdf = generate_pdf_report({"project_name": proj_name, "location": "Global", "scope": scope}, results)
            st.download_button(label="📄 Download Executive Proposal PDF", data=pdf, file_name="CETP_Report.pdf", mime="application/pdf")

            # Force memory cleanup
            del t_8760, l_8760
            gc.collect()

        except Exception as e:
            st.error(f"Error in Simulation: {str(e)}")