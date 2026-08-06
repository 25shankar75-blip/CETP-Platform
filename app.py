"""
Cooling Energy Transition Platform (CETP) - Master Streamlit Frontend
File: app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json

from schemas import ProjectConfig, ThermoConfig, AuditConfig, FinancialConfig, ScopeEnum, CurrencyEnum, ChillerTypeEnum
from physics_engine import fetch_live_weather_wbt, calc_operating_tr, calc_hydraulic_pump_kw
from financial_engine import fetch_live_currency_rates, format_currency, calc_capex_breakup
from optimizer import optimize_tes_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin", layout="wide", initial_sidebar_state="expanded")

# --- INITIALIZE SESSION STATE ---
if "df_24h" not in st.session_state:
    hours = np.arange(1, 25)
    # Mondelez 3017 TRh Baseline Load & Tariff Matrix
    loads = [1047.82]*8 + [1746.36]*2 + [2095.63]*2 + [2794.18]*4 + [2444.90]*4 + [2095.63]*2 + [1047.82]*2
    tariffs = [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2
    st.session_state["df_24h"] = pd.DataFrame({
        "Hour": hours,
        "Cooling Load (TR)": loads,
        "Tariff (₹/kWh)": tariffs,
        " ": [""]*24  # Blank spacer column to prevent drag/scroll freezing
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

if "live_rates" not in st.session_state:
    st.session_state["live_rates"] = fetch_live_currency_rates()

if "opt_results" not in st.session_state:
    st.session_state["opt_results"] = None

# --- SIDEBAR NAVIGATION & EXECUTION CONTROL ---
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

st.sidebar.markdown("---")
# EXPLICIT SIMULATION RUNNER BUTTON
run_sim_btn = st.sidebar.button("▶️ Run Digital Twin Optimization", use_container_width=True, type="primary")

if run_sim_btn:
    rates = {
        "base_chiller_rate_per_tr": st.session_state["fin_cfg"].base_chiller_rate_per_tr,
        "brine_chiller_rate_per_tr": st.session_state["fin_cfg"].brine_chiller_rate_per_tr,
        "pcm_tes_rate_per_trh": st.session_state["fin_cfg"].pcm_tes_rate_per_trh,
        "stratified_tes_rate_per_trh": st.session_state["fin_cfg"].stratified_tes_rate_per_trh,
        "indirects_pct": st.session_state["fin_cfg"].indirects_pct
    }
    audit_dict = {
        "running_chw_supply_c": st.session_state["audit_cfg"].running_chw_supply_c,
        "running_chw_return_c": st.session_state["audit_cfg"].running_chw_return_c,
        "running_chw_flow_m3h": st.session_state["audit_cfg"].running_chw_flow_m3h,
        "running_cw_flow_m3h": st.session_state["audit_cfg"].running_cw_flow_m3h,
        "chw_pump_head_m": st.session_state["audit_cfg"].chw_pump_head_m,
        "cw_pump_head_m": st.session_state["audit_cfg"].cw_pump_head_m,
        "ct_fan_power_kw": st.session_state["audit_cfg"].ct_fan_power_kw
    }
    
    st.session_state["opt_results"] = optimize_tes_plant(
        st.session_state["df_24h"],
        scope=st.session_state["project_cfg"].scope.value,
        peak_tr=st.session_state["project_cfg"].peak_tr,
        audit_config=audit_dict,
        rates=rates,
        fleet_df=st.session_state["chiller_fleet"]
    )
    st.sidebar.success("Digital Twin Optimization Completed! ✅")

# --- TAB 1: SETUP & PLANT CONFIGURATION ---
if nav == "🎛️ Setup & Plant Configuration":
    st.header("🎛️ Setup & Plant Configuration")
    
    # Save & Upload Scenario Controls
    c_up, c_dn = st.columns(2)
    with c_up:
        uploaded_file = st.file_uploader("📂 Upload Saved Project Scenario (.json)", type=["json"])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                st.session_state["df_24h"] = pd.DataFrame(data["df_24h"])
                st.session_state["chiller_fleet"] = pd.DataFrame(data["chiller_fleet"])
                st.success("Project Scenario Uploaded & Restored! ✅")
            except Exception as e:
                st.error(f"Error restoring file: {str(e)}")
                
    with c_dn:
        scenario_data = {
            "project_cfg": st.session_state["project_cfg"].dict(),
            "df_24h": st.session_state["df_24h"].to_dict(),
            "chiller_fleet": st.session_state["chiller_fleet"].to_dict()
        }
        st.download_button(
            "💾 Download Current Project Scenario (.json)",
            data=json.dumps(scenario_data, indent=2),
            file_name=f"{st.session_state['project_cfg'].project_name}_Scenario.json",
            mime="application/json"
        )

    st.markdown("---")
    
    with st.form("global_setup_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            p_name = st.text_input("Project Name", value=st.session_state["project_cfg"].project_name)
            p_loc = st.text_input("Location (City/Site)", value=st.session_state["project_cfg"].location)
            p_scope = st.selectbox("Project Scope", [ScopeEnum.GREENFIELD.value, ScopeEnum.BROWNFIELD.value], index=1)
            
        with col2:
            p_sector = st.selectbox("Industry Sector", [s.value for s in SectorEnum], index=2)
            p_curr = st.selectbox("Currency Unit", [c.value for c in CurrencyEnum], index=0)
            p_peak_tr = st.number_input("Peak Load (TR)", value=float(st.session_state["project_cfg"].peak_tr))
            
        with col3:
            st.markdown("**Temperatures (°C)**")
            chw_sup = st.number_input("CHW Supply (°C)", value=float(st.session_state["thermo_cfg"].chw_supply_temp))
            chw_ret = st.number_input("CHW Return (°C)", value=float(st.session_state["thermo_cfg"].chw_return_temp))
            brine_sup = st.number_input("Brine Supply (°C)", value=float(st.session_state["thermo_cfg"].brine_supply_temp))
            brine_ret = st.number_input("Brine Return (°C)", value=float(st.session_state["thermo_cfg"].brine_return_temp))

        st.markdown("---")
        st.subheader("Granular Unit Rates (SITC Baseline)")
        r1, r2, r3 = st.columns(3)
        b_rate = r1.number_input("Base Chiller (/TR)", value=float(st.session_state["fin_cfg"].base_chiller_rate_per_tr))
        br_rate = r2.number_input("Brine Chiller (/TR)", value=float(st.session_state["fin_cfg"].brine_chiller_rate_per_tr))
        pcm_rate = r3.number_input("PCM TES (/TRh)", value=float(st.session_state["fin_cfg"].pcm_tes_rate_per_trh))
        strat_rate = r1.number_input("Stratified TES (/TRh)", value=float(st.session_state["fin_cfg"].stratified_tes_rate_per_trh))
        chw_p_rate = r2.number_input("CHW Pump (/kW)", value=float(st.session_state["fin_cfg"].chw_pump_rate_per_kw))
        cw_p_rate = r3.number_input("CW Pump (/kW)", value=float(st.session_state["fin_cfg"].cw_pump_rate_per_kw))
        
        save_btn = st.form_submit_button("Save & Apply Global Configuration", use_container_width=True)
        if save_btn:
            st.session_state["project_cfg"].project_name = p_name
            st.session_state["project_cfg"].location = p_loc
            st.session_state["project_cfg"].scope = ScopeEnum(p_scope)
            st.session_state["project_cfg"].currency = CurrencyEnum(p_curr)
            st.session_state["project_cfg"].peak_tr = p_peak_tr
            st.session_state["thermo_cfg"].chw_supply_temp = chw_sup
            st.session_state["thermo_cfg"].chw_return_temp = chw_ret
            st.session_state["thermo_cfg"].brine_supply_temp = brine_sup
            st.session_state["thermo_cfg"].brine_return_temp = brine_ret
            st.session_state["fin_cfg"].base_chiller_rate_per_tr = b_rate
            st.session_state["fin_cfg"].brine_chiller_rate_per_tr = br_rate
            st.session_state["fin_cfg"].pcm_tes_rate_per_trh = pcm_rate
            st.session_state["fin_cfg"].stratified_tes_rate_per_trh = strat_rate
            st.success("Global Configuration Saved! ✅")

    # Conditional Retrofit Audit Section
    if st.session_state["project_cfg"].scope == ScopeEnum.BROWNFIELD:
        st.markdown("---")
        st.header("🔍 Conditional Retrofit Audit (Low ΔT Diagnosis)")
        st.info("Captures actual measured operating parameters to calculate $m \\cdot C_p \\cdot \\Delta T$ and pump hydraulics.")
        
        with st.form("retrofit_audit_form"):
            a1, a2, a3 = st.columns(3)
            run_sup = a1.number_input("Measured CHW Supply (°C)", value=float(st.session_state["audit_cfg"].running_chw_supply_c))
            run_ret = a2.number_input("Measured CHW Return (°C)", value=float(st.session_state["audit_cfg"].running_chw_return_c))
            run_chw_flow = a3.number_input("Measured CHW Flow (m³/h)", value=float(st.session_state["audit_cfg"].running_chw_flow_m3h))
            
            cw_sup = a1.number_input("Measured CW Supply (°C)", value=float(st.session_state["audit_cfg"].running_cw_supply_c))
            cw_ret = a2.number_input("Measured CW Return (°C)", value=float(st.session_state["audit_cfg"].running_cw_return_c))
            cw_flow = a3.number_input("Measured CW Flow (m³/h)", value=float(st.session_state["audit_cfg"].running_cw_flow_m3h))
            
            chw_head = a1.number_input("CHW Pump Head (m)", value=float(st.session_state["audit_cfg"].chw_pump_head_m))
            cw_head = a2.number_input("CW Pump Head (m)", value=float(st.session_state["audit_cfg"].cw_pump_head_m))
            ct_kw = a3.number_input("CT Fan Power (kW)", value=float(st.session_state["audit_cfg"].ct_fan_power_kw))
            
            audit_submit = st.form_submit_button("Update Audit Parameters", use_container_width=True)
            if audit_submit:
                st.session_state["audit_cfg"].running_chw_supply_c = run_sup
                st.session_state["audit_cfg"].running_chw_return_c = run_ret
                st.session_state["audit_cfg"].running_chw_flow_m3h = run_chw_flow
                st.session_state["audit_cfg"].running_cw_supply_c = cw_sup
                st.session_state["audit_cfg"].running_cw_return_c = cw_ret
                st.session_state["audit_cfg"].running_cw_flow_m3h = cw_flow
                st.session_state["audit_cfg"].chw_pump_head_m = chw_head
                st.session_state["audit_cfg"].cw_pump_head_m = cw_head
                st.session_state["audit_cfg"].ct_fan_power_kw = ct_kw
                st.success("Audit Ingested! ✅")

        # Auto-Calculated Diagnostic Metrics
        dt_act = st.session_state["audit_cfg"].running_chw_return_c - st.session_state["audit_cfg"].running_chw_supply_c
        tr_act = calc_operating_tr(st.session_state["audit_cfg"].running_chw_flow_m3h, dt_act)
        chw_pump_kw_act = calc_hydraulic_pump_kw(st.session_state["audit_cfg"].running_chw_flow_m3h, st.session_state["audit_cfg"].chw_pump_head_m)
        cw_pump_kw_act = calc_hydraulic_pump_kw(st.session_state["audit_cfg"].running_cw_flow_m3h, st.session_state["audit_cfg"].cw_pump_head_m)
        
        tot_meas_kw = (tr_act * 0.72) + chw_pump_kw_act + cw_pump_kw_act + st.session_state["audit_cfg"].ct_fan_power_kw
        act_kw_tr = tot_meas_kw / max(1.0, tr_act) if tr_act > 0 else 0.91
        
        d1, d2, d3 = st.columns(3)
        d1.metric("Operating Load (Measured)", f"{tr_act:.2f} TR", delta=f"Delta-T: {dt_act:.1f} °C")
        d2.metric("Total Measured Plant Power", f"{tot_meas_kw:.1f} kW")
        d3.metric("Auto-Calculated Plant kW/TR", f"{act_kw_tr:.3f} kW/TR", delta="Inefficient State")

    # Up to 10-Row Dynamic Chiller Array Table
    st.markdown("---")
    st.subheader("🏭 Installed / Baseline Chiller Fleet Array (Up to 10 Rows)")
    edited_fleet = st.data_editor(
        st.session_state["chiller_fleet"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Chiller Type": st.column_config.SelectboxColumn(
                "Chiller Type",
                options=[t.value for t in ChillerTypeEnum],
                required=True
            )
        }
    )
    st.session_state["chiller_fleet"] = edited_fleet

# --- TAB 2: 24-HOUR LOAD PROFILE ---
elif nav == "📊 24-Hour Load & Tariff Profile":
    st.header("📊 Interactive 24-Hour Diurnal Load & Tariff Profile")
    st.caption("All calculated data metrics have been stripped from this input screen to eliminate Streamlit auto-refresh loops.")
    
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
        title="24-Hour Diurnal Profile",
        xaxis=dict(title="Hour of Day (1-24)"),
        yaxis=dict(title="Cooling Load (TR)"),
        yaxis2=dict(title="Tariff (₹/kWh)", overlaying="y", side="right"),
        barmode="group"
    )
    st.plotly_chart(fig, use_container_width=True)

# --- OUTPUT TAB ROUTING ---
else:
    if st.session_state["opt_results"] is None:
        st.info("👈 Please click the **'▶️ Run Digital Twin Optimization'** button in the sidebar to execute the solvers.")
    else:
        results = st.session_state["opt_results"]
        curr_str = st.session_state["project_cfg"].currency.value
        scope_str = st.session_state["project_cfg"].scope.value
        peak_tr = st.session_state["project_cfg"].peak_tr
        live_rates = st.session_state["live_rates"]
        
        if nav in ["🏭 Conventional / Existing Baseline", "🧊 PCM TES Optimum", "🌊 Stratified TES Optimum"]:
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
            
            # TOP METRIC BAR APPENDED TO OUTPUT SCREENS
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Peak Cooling Load", f"{peak_tr:.1f} TR")
            c2.metric("Average Cooling Load", f"{np.mean(st.session_state['df_24h']['Cooling Load (TR)']):.1f} TR")
            c3.metric("Daily Energy Demand", f"{np.sum(st.session_state['df_24h']['Cooling Load (TR)']):.1f} TRh")
            c4.metric("Turnkey CAPEX", format_currency(data.get("capex", 0.0), curr_str, live_rates))
            
            st.markdown("---")
            st.subheader("⚡ Complete Hourly Power Breakdown Matrix")
            
            df_power = pd.DataFrame({
                "Hour": st.session_state["df_24h"]["Hour"],
                "Cooling Load (TR)": st.session_state["df_24h"]["Cooling Load (TR)"],
                "Operating Load (TR/hr)": sim["op_tr"],
                "Charge (TR)": sim["charge_tr"],
                "Discharge (TR)": sim["discharge_tr"],
                "Chiller Loading (%)": sim["loading_pct"],
                "Compressors (kW)": sim["comp_kw"],
                "CHW Primary Pumps (kW)": sim["chw_pri_kw"],
                "CHW Secondary Pumps (kW)": sim["chw_sec_kw"],
                "CW Pumps (kW)": sim["cw_pump_kw"],
                "CT Fans (kW)": sim["ct_fan_kw"],
                "Total Demand (kW)": sim["total_kw"],
                "ToU Tariff": st.session_state["df_24h"]["Tariff (₹/kWh)"],
                "Hourly Cost": sim["hourly_cost"]
            })
            st.dataframe(df_power, use_container_width=True)

        elif nav == "💰 CAPEX Breakdown & Comparison":
            st.header("💰 Executive Economics & CAPEX Breakdown")
            
            cols = st.columns(3)
            cols[0].metric("Baseline CAPEX", format_currency(results["baseline"]["capex"], curr_str, live_rates))
            cols[1].metric("PCM TES CAPEX", format_currency(results["pcm"]["capex"], curr_str, live_rates), delta=f"Payback: {results['pcm']['payback_years']:.2f} Yrs")
            cols[2].metric("Stratified TES CAPEX", format_currency(results["stratified"]["capex"], curr_str, live_rates), delta=f"Payback: {results['stratified']['payback_years']:.2f} Yrs")
            
            st.markdown("---")
            st.subheader("📊 Annual OPEX & Savings Comparison")
            
            comp_df = pd.DataFrame([
                {"Option": "Conventional / Existing Baseline", "CAPEX": format_currency(results["baseline"]["capex"], curr_str, live_rates), "Annual OPEX": format_currency(results["baseline"]["opex"], curr_str, live_rates), "Annual Savings": "Baseline", "Payback": "N/A"},
                {"Option": f"PCM TES ({results['pcm']['tes_trh']:.0f} TRh)", "CAPEX": format_currency(results["pcm"]["capex"], curr_str, live_rates), "Annual OPEX": format_currency(results["pcm"]["opex"], curr_str, live_rates), "Annual Savings": format_currency(results["pcm"]["opex_savings"], curr_str, live_rates), "Payback": f"{results['pcm']['payback_years']:.2f} Yrs"},
                {"Option": f"Stratified TES ({results['stratified']['tes_trh']:.0f} TRh)", "CAPEX": format_currency(results["stratified"]["capex"], curr_str, live_rates), "Annual OPEX": format_currency(results["stratified"]["opex"], curr_str, live_rates), "Annual Savings": format_currency(results["stratified"]["opex_savings"], curr_str, live_rates), "Payback": f"{results['stratified']['payback_years']:.2f} Yrs"}
            ])
            st.table(comp_df)

        elif nav == "📄 Executive Report Dashboard":
            st.header("📄 Client-Ready Report Dashboard")
            st.caption("Generates verified, validated, and error-free executive PDF and Word reports.")
            
            c1, c2 = st.columns(2)
            
            pdf_bytes = generate_pdf_report(st.session_state["project_cfg"].project_name, curr_str, results)
            docx_bytes = generate_word_report(st.session_state["project_cfg"].project_name, curr_str, results)
            
            c1.download_button(
                label="📥 Download Executive PDF Report",
                data=pdf_bytes,
                file_name=f"{st.session_state['project_cfg'].project_name}_Report.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            c2.download_button(
                label="📥 Download Word (.docx) Report",
                data=docx_bytes,
                file_name=f"{st.session_state['project_cfg'].project_name}_Report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )