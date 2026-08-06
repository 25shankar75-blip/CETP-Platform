"""
CETP Digital Twin - Master Streamlit Interface
File: app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from schemas import ProjectConfig, ThermoConfig, AuditConfig, FinancialConfig, ScopeEnum, CurrencyEnum
from physics_engine import calc_operating_tr
from financial_engine import format_currency, calc_capex_breakup
from optimizer import optimize_tes_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin", layout="wide", initial_sidebar_state="expanded")

# --- INITIALIZE SESSION STATE ---
if "df_24h" not in st.session_state:
    hours = np.arange(1, 25)
    # Mondelez 3017 TRh Profile
    loads = [1047.82]*8 + [1746.36]*2 + [2095.63]*2 + [2794.18]*4 + [2444.90]*4 + [2095.63]*2 + [1047.82]*2
    tariffs = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2
    st.session_state["df_24h"] = pd.DataFrame({
        "Hour": hours,
        "Cooling Load (TR)": loads,
        "Tariff (₹/kWh)": tariffs
    })

if "chiller_fleet" not in st.session_state:
    st.session_state["chiller_fleet"] = pd.DataFrame([
        {"Capacity (TR)": 1000.0, "Quantity": 2, "Chiller Type": "Water-Cooled Centrifugal"},
        {"Capacity (TR)": 800.0, "Quantity": 1, "Chiller Type": "Water-Cooled VFD Screw"}
    ])

if "project_cfg" not in st.session_state:
    st.session_state["project_cfg"] = ProjectConfig()

if "thermo_cfg" not in st.session_state:
    st.session_state["thermo_cfg"] = ThermoConfig()

if "audit_cfg" not in st.session_state:
    st.session_state["audit_cfg"] = AuditConfig()

if "fin_cfg" not in st.session_state:
    st.session_state["fin_cfg"] = FinancialConfig()

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("❄️ CETP Digital Twin")
st.sidebar.caption("Cooling Energy Transition Platform")

nav = st.sidebar.radio("Navigation", [
    "🎛️ Setup & Plant Configuration",
    "📊 24-Hour Load & Tariff Profile",
    "🏭 Conventional / Existing Baseline",
    "🧊 PCM TES Optimum",
    "🌊 Stratified TES Optimum",
    "💰 CAPEX Breakdown & Comparison",
    "📄 Executive Report Dashboard"
])

# MAIN WORKSPACE ROUTING
if nav == "🎛️ Setup & Plant Configuration":
    st.header("🎛️ Project & Global Setup")
    
    with st.form("global_setup_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            p_name = st.text_input("Project Name", value=st.session_state["project_cfg"].project_name)
            p_loc = st.text_input("Location", value=st.session_state["project_cfg"].location)
            p_scope = st.selectbox("Project Scope", [ScopeEnum.GREENFIELD.value, ScopeEnum.BROWNFIELD.value], index=1)
            
        with col2:
            p_sector = st.selectbox("Industry Sector", ["Pharmaceutical", "Data Centre", "FMCG", "Auto", "Commercial"], index=2)
            p_curr = st.selectbox("Currency Unit", [c.value for c in CurrencyEnum], index=0)
            p_peak_tr = st.number_input("Peak Load (TR)", value=float(st.session_state["project_cfg"].peak_tr))
            
        with col3:
            st.markdown("**Temperatures (°C)**")
            chw_sup = st.number_input("CHW Supply (°C)", value=7.0)
            chw_ret = st.number_input("CHW Return (°C)", value=14.0)
            brine_sup = st.number_input("Brine Supply (°C)", value=-5.5)
            
        st.markdown("---")
        st.subheader("Unit Cost Rates (SITC Baseline)")
        r1, r2, r3 = st.columns(3)
        b_rate = r1.number_input("Base Chiller (/TR)", value=22000.0)
        br_rate = r2.number_input("Brine Chiller (/TR)", value=25000.0)
        pcm_rate = r3.number_input("PCM TES (/TRh)", value=7800.0)
        strat_rate = r1.number_input("Stratified TES (/TRh)", value=18000.0)
        dg_rate = r2.number_input("DG Set (/kVA)", value=12500.0)
        
        save_btn = st.form_submit_button("Save & Apply Global Configuration", use_container_width=True)
        if save_btn:
            st.session_state["project_cfg"].project_name = p_name
            st.session_state["project_cfg"].location = p_loc
            st.session_state["project_cfg"].scope = ScopeEnum(p_scope)
            st.session_state["project_cfg"].currency = CurrencyEnum(p_curr)
            st.session_state["project_cfg"].peak_tr = p_peak_tr
            st.session_state["fin_cfg"].base_chiller_rate_per_tr = b_rate
            st.session_state["fin_cfg"].brine_chiller_rate_per_tr = br_rate
            st.session_state["fin_cfg"].pcm_tes_rate_per_trh = pcm_rate
            st.session_state["fin_cfg"].stratified_tes_rate_per_trh = strat_rate
            st.session_state["fin_cfg"].dg_set_rate_per_kva = dg_rate
            st.success("Global Configuration Saved Successfully! ✅")

    # Conditional Retrofit Audit Section
    if st.session_state["project_cfg"].scope == ScopeEnum.BROWNFIELD:
        st.markdown("---")
        st.header("🔍 Conditional Retrofit Audit (Low ΔT Diagnosis)")
        st.info("Captures actual operating parameters to calculate $m \\cdot C_p \\cdot \\Delta T$ inefficiencies.")
        
        with st.form("retrofit_audit_form"):
            a_col1, a_col2, a_col3 = st.columns(3)
            run_sup = a_col1.number_input("Running CHW Supply (°C)", value=8.0)
            run_ret = a_col2.number_input("Running CHW Return (°C)", value=12.0)
            run_flow = a_col3.number_input("Running Flow Rate (m³/h)", value=500.0)
            
            p_head = a_col1.number_input("Existing Pump Head (m)", value=30.0)
            ct_power = a_col2.number_input("CT Fan Power (kW)", value=45.0)
            act_kw_tr = a_col3.number_input("Audited Plant kW/TR", value=0.91)
            
            audit_submit = st.form_submit_button("Update Audit Parameters", use_container_width=True)
            if audit_submit:
                st.session_state["audit_cfg"].running_chw_supply_c = run_sup
                st.session_state["audit_cfg"].running_chw_return_c = run_ret
                st.session_state["audit_cfg"].running_chw_flow_m3h = run_flow
                st.session_state["audit_cfg"].chw_pump_head_m = p_head
                st.session_state["audit_cfg"].ct_fan_power_kw = ct_power
                st.session_state["audit_cfg"].actual_kw_per_tr = act_kw_tr
                st.success("Retrofit Audit Diagnostics Ingested! ✅")
                
        # Calculated Audit Metric Display
        dt_actual = st.session_state["audit_cfg"].running_chw_return_c - st.session_state["audit_cfg"].running_chw_supply_c
        tr_actual = calc_operating_tr(st.session_state["audit_cfg"].running_chw_flow_m3h, dt_actual)
        st.metric("Diagnosed Operating TR (Actual)", f"{tr_actual:.2f} TR", delta=f"Delta-T: {dt_actual:.1f} °C (Inefficient)")

    # Up to 10-Row Chiller Fleet Array
    st.markdown("---")
    st.subheader("🏭 Installed / Baseline Chiller Fleet Array")
    edited_fleet = st.data_editor(
        st.session_state["chiller_fleet"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )
    st.session_state["chiller_fleet"] = edited_fleet

elif nav == "📊 24-Hour Load & Tariff Profile":
    st.header("📊 Interactive 24-Hour Load & ToU Tariff Matrix")
    st.markdown("Calculated data metrics have been stripped from this input screen to eliminate Streamlit rerun loops.")
    
    edited_df = st.data_editor(
        st.session_state["df_24h"],
        num_rows="fixed",
        use_container_width=True,
        hide_index=True
    )
    st.session_state["df_24h"] = edited_df
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=edited_df["Hour"], y=edited_df["Cooling Load (TR)"], name="Cooling Load (TR)", marker_color="#00B4D8"))
    fig.add_trace(go.Scatter(x=edited_df["Hour"], y=edited_df["Tariff (₹/kWh)"], name="ToU Tariff", yaxis="y2", line=dict(color="#FF006E", width=3)))
    fig.update_layout(
        title="24-Hour Cooling Load Profile vs. ToU Tariff",
        xaxis=dict(title="Hour of Day (1-24)"),
        yaxis=dict(title="Cooling Load (TR)"),
        yaxis2=dict(title="Tariff (₹/kWh)", overlaying="y", side="right"),
        barmode="group"
    )
    st.plotly_chart(fig, use_container_width=True)

# SIMULATION EXECUTION & OUTPUT ROUTING
else:
    rates = {
        "base_chiller_rate_per_tr": st.session_state["fin_cfg"].base_chiller_rate_per_tr,
        "brine_chiller_rate_per_tr": st.session_state["fin_cfg"].brine_chiller_rate_per_tr,
        "pcm_tes_rate_per_trh": st.session_state["fin_cfg"].pcm_tes_rate_per_trh,
        "stratified_tes_rate_per_trh": st.session_state["fin_cfg"].stratified_tes_rate_per_trh,
        "indirects_pct": st.session_state["fin_cfg"].indirects_pct
    }
    
    audit_dict = {
        "running_chw_flow_m3h": st.session_state["audit_cfg"].running_chw_flow_m3h,
        "chw_pump_head_m": st.session_state["audit_cfg"].chw_pump_head_m,
        "cw_pump_head_m": st.session_state["audit_cfg"].cw_pump_head_m,
        "ct_fan_power_kw": st.session_state["audit_cfg"].ct_fan_power_kw,
        "actual_kw_per_tr": st.session_state["audit_cfg"].actual_kw_per_tr
    }
    
    curr_str = st.session_state["project_cfg"].currency.value
    scope_str = st.session_state["project_cfg"].scope.value
    peak_tr = st.session_state["project_cfg"].peak_tr
    
    # Run Digital Twin Optimizer
    results = optimize_tes_plant(
        st.session_state["df_24h"],
        scope=scope_str,
        peak_tr=peak_tr,
        audit_config=audit_dict,
        rates=rates
    )
    
    if nav in ["🏭 Conventional / Existing Baseline", "🧊 PCM TES Optimum", "🌊 Stratified TES Optimum"]:
        # Select target dataset
        if "Conventional" in nav:
            res_key = "baseline"
            title = "Outputs - Existing Retrofit Baseline" if scope_str == "Brownfield (Retrofit)" else "Outputs - Conventional N+1 Baseline"
        elif "PCM" in nav:
            res_key = "pcm"
            title = f"Outputs - PCM TES Optimum ({results['pcm']['tes_trh']:.0f} TRh)"
        else:
            res_key = "stratified"
            title = f"Outputs - Stratified TES Optimum ({results['stratified']['tes_trh']:.0f} TRh)"
            
        data = results[res_key]
        sim = data["sim"] if "sim" in data else data
        
        st.header(title)
        
        # Output Top Metric Bar
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Peak Load", f"{peak_tr:.1f} TR")
        c2.metric("Average Load", f"{np.mean(st.session_state['df_24h']['Cooling Load (TR)']):.1f} TR")
        c3.metric("Daily Energy Demand", f"{np.sum(st.session_state['df_24h']['Cooling Load (TR)']):.1f} TRh")
        c4.metric("Turnkey CAPEX", format_currency(data.get("capex", 0.0), curr_str))
        
        st.markdown("---")
        st.subheader("⚡ Hourly Power Breakdown Matrix (kW)")
        
        if res_key == "baseline":
            df_power = pd.DataFrame({
                "Hour": st.session_state["df_24h"]["Hour"],
                "Compressors (kW)": sim["comp_kw"],
                "CHW Pumps (kW)": sim["chw_pump_kw"],
                "CW Pumps (kW)": sim["cw_pump_kw"],
                "CT Fans (kW)": sim["ct_fan_kw"],
                "Total Demand (kW)": sim["total_kw"]
            })
        elif res_key == "pcm":
            df_power = pd.DataFrame({
                "Hour": st.session_state["df_24h"]["Hour"],
                "Brine Charge Chiller (kW)": sim["charge_kw"],
                "Base Chillers (kW)": sim["base_chiller_kw"],
                "Pumps & Aux (kW)": sim["pump_kw"],
                "Total Demand (kW)": sim["total_kw"],
                "Mode": sim["mode"]
            })
        else:
            df_power = pd.DataFrame({
                "Hour": st.session_state["df_24h"]["Hour"],
                "Compressors (kW)": sim["comp_kw"],
                "Pumps & Aux (kW)": sim["pump_kw"],
                "Total Demand (kW)": sim["total_kw"],
                "Mode": sim["mode"]
            })
            
        st.dataframe(df_power, use_container_width=True)

    elif nav == "💰 CAPEX Breakdown & Comparison":
        st.header("💰 Executive Economics & CAPEX Breakdown")
        
        cols = st.columns(3)
        cols[0].metric("Baseline CAPEX", format_currency(results["baseline"]["capex"], curr_str))
        cols[1].metric("PCM TES CAPEX", format_currency(results["pcm"]["capex"], curr_str), delta=f"Payback: {results['pcm']['payback_years']:.2f} Yrs")
        cols[2].metric("Stratified TES CAPEX", format_currency(results["stratified"]["capex"], curr_str), delta=f"Payback: {results['stratified']['payback_years']:.2f} Yrs")
        
        st.markdown("---")
        st.subheader("📊 Annual OPEX & Savings Comparison")
        
        comp_df = pd.DataFrame([
            {"Option": "Conventional Baseline", "CAPEX": format_currency(results["baseline"]["capex"], curr_str), "Annual OPEX": format_currency(results["baseline"]["opex"], curr_str), "Annual Savings": "Baseline", "Payback": "N/A"},
            {"Option": f"PCM TES ({results['pcm']['tes_trh']:.0f} TRh)", "CAPEX": format_currency(results["pcm"]["capex"], curr_str), "Annual OPEX": format_currency(results["pcm"]["opex"], curr_str), "Annual Savings": format_currency(results["pcm"]["opex_savings"], curr_str), "Payback": f"{results['pcm']['payback_years']:.2f} Yrs"},
            {"Option": f"Stratified TES ({results['stratified']['tes_trh']:.0f} TRh)", "CAPEX": format_currency(results["stratified"]["capex"], curr_str), "Annual OPEX": format_currency(results["stratified"]["opex"], curr_str), "Annual Savings": format_currency(results["stratified"]["opex_savings"], curr_str), "Payback": f"{results['stratified']['payback_years']:.2f} Yrs"}
        ])
        st.table(comp_df)

    elif nav == "📄 Executive Report Dashboard":
        st.header("📄 Client-Ready Report Generator")
        st.markdown("Export comprehensive, validated engineering documentation.")
        
        col1, col2 = st.columns(2)
        
        pdf_bytes = generate_pdf_report(st.session_state["project_cfg"].project_name, curr_str, results)
        docx_bytes = generate_word_report(st.session_state["project_cfg"].project_name, curr_str, results)
        
        col1.download_button(
            label="📥 Download Executive PDF Report",
            data=pdf_bytes,
            file_name=f"{st.session_state['project_cfg'].project_name}_Report.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
        col2.download_button(
            label="📥 Download Word (.docx) Report",
            data=docx_bytes,
            file_name=f"{st.session_state['project_cfg'].project_name}_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )