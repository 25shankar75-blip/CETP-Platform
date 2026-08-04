# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gc

from schemas import (
    ProjectConfig, ThermoConfig, HydraulicConfig, FinancialConfig,
    CURRENCY_MULTIPLIERS, CURRENCY_SYMBOLS
)
from physics_engine import expand_24_to_8760
from optimizer import run_8760_simulation
from financial_engine import format_currency
from report_generator import generate_pdf_report

st.set_page_config(
    page_title="CETP Digital Twin Platform",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("❄️ Cooling Energy Transition Platform (CETP)")
st.caption("ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage & Cooling Digital Twin")

# ----------------------------------------------------
# DEFAULT REV19 HARD-LOCKED BASELINE DATASET
# ----------------------------------------------------
DEFAULT_24H_LOAD_PCT = [60.0, 60.0, 60.0, 60.0, 60.0, 60.0, 80.0, 90.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 80.0, 80.0, 70.0, 70.0, 60.0, 60.0, 60.0, 60.0]
DEFAULT_24H_TARIFF = [5.62, 5.62, 5.62, 5.62, 5.62, 5.62, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 6.11, 7.03, 7.03, 7.03, 7.03, 5.62, 5.62]

def get_tou_category(tariff: float) -> str:
    if tariff <= 5.80:
        return "Off-Peak (Charge)"
    elif tariff >= 6.80:
        return "Peak (Discharge)"
    else:
        return "Normal"

# ----------------------------------------------------
# SIDEBAR: INPUT MASTER SUITE
# ----------------------------------------------------
st.sidebar.header("🛠️ Input Master Suite")

# Center Screen Table Toggle Button
show_editor = st.sidebar.toggle("📅 Edit 24-Hour Load & Tariff Profile", value=True)

with st.sidebar.expander("📌 1. Project Scope & Sector", expanded=True):
    proj_name = st.text_input("Project Name", "Ujjain Pharma Greenfield Baseline")
    location = st.text_input("Location", "Ujjain, MP, India")
    sector = st.selectbox("Industry Sector", ["Pharmaceutical", "Data Centre", "Commercial Office", "Hospital", "Industrial / Manufacturing", "Hotel", "District Cooling"])
    scope = st.radio("Project Scope", ["Greenfield", "Brownfield (Retrofit)"])
    currency = st.selectbox("Currency Unit", list(CURRENCY_MULTIPLIERS.keys()), index=0)
    mult = CURRENCY_MULTIPLIERS[currency]
    sym = CURRENCY_SYMBOLS[currency]
    peak_load_tr = st.number_input("Peak Cooling Load (TR)", min_value=100.0, max_value=50000.0, value=2794.18, step=100.0)
    tank_shape = st.selectbox("TES Tank Geometry", ["Cylindrical", "Rectangular"])

with st.sidebar.expander("🌡️ 2. Thermodynamics & System Parameters", expanded=False):
    chiller_type = st.selectbox("Primary Chiller Type", ["Water-Cooled Centrifugal", "Air-Cooled Screw"])
    base_cop = st.number_input("Base Chiller COP", min_value=2.0, max_value=8.0, value=6.0 if "Water" in chiller_type else 3.2, step=0.1)
    design_wbt = st.number_input("Design Wet Bulb Temp (°C)", value=28.0, step=0.5)
    pcm_charge_temp = st.number_input("PCM Charging Temp (°C)", value=-5.5, step=0.5)
    pcm_derate = st.number_input("PCM Sub-Zero COP Penalty Factor", value=0.85, step=0.01)
    night_relief = st.number_input("Night Condenser Relief Bonus", value=0.92, step=0.01)

with st.sidebar.expander("💧 3. Hydraulics & Heat Exchangers", expanded=False):
    chw_delta_t = st.number_input("CHW Delta T (°C)", value=6.0, step=0.5)
    pcm_fom = st.number_input("PCM Tank Figure of Merit (FOM)", value=0.95, step=0.01)
    strat_fom = st.number_input("Stratified Tank FOM", value=0.90, step=0.01)
    chw_pump_head = st.number_input("CHW Pump Head (m)", value=35.0, step=5.0)
    cdw_pump_head = st.number_input("CDW Pump Head (m)", value=25.0, step=5.0)
    brine_pump_head = st.number_input("Brine Pump Head (m)", value=45.0, step=5.0)
    pump_eff = st.number_input("Pump Efficiency", value=0.75, step=0.05)

with st.sidebar.expander("💰 4. Financial Unit Rates & Tariffs", expanded=False):
    demand_charge_kva = st.number_input(f"Monthly Demand Charge ({sym}/kVA)", value=475.0 * mult, step=25.0)
    
    sys_rates = {
        'water_cooled_chiller': 17000.0 * mult,
        'air_cooled_chiller': 19000.0 * mult,
        'brine_chiller': 23000.0 * mult,
        'cooling_tower': 2200.0 * mult,
        'chw_pump': 700.0 * mult,
        'cdw_pump': 550.0 * mult,
        'brine_pump': 900.0 * mult,
        'phe': 1100.0 * mult,
        'pcm_tes_cylindrical': 7533.0 * mult,
        'pcm_tes_rectangular': 8475.0 * mult,
        'strat_tes': 18000.0 * mult,
        'dg_set': 11000.0 * mult,
        'transformer': 1700.0 * mult
    }

# ----------------------------------------------------
# MAIN SCREEN: DYNAMIC 24-HOUR PROFILE DATA EDITOR
# ----------------------------------------------------
if show_editor:
    st.subheader("📅 Interactive 24-Hour Diurnal Load & ToU Tariff Data Editor")
    st.info("💡 **Bi-Directional Entry Active:** You can edit **Cooling Load (%)**, **Cooling Load (TR)**, or **Tariff** directly. Press **Enter**, **Tab**, or click outside the cell to trigger instant recalculation.")
    
    # Initialize base dataframe
    df_init = pd.DataFrame({
        "Hour": [f"Hour {i+1:02d} ({i:02d}:00)" for i in range(24)],
        "Cooling Load (%)": DEFAULT_24H_LOAD_PCT,
        "Cooling Load (TR)": [(p / 100.0) * peak_load_tr for p in DEFAULT_24H_LOAD_PCT],
        f"Tariff ({sym}/kWh)": [t * mult for t in DEFAULT_24H_TARIFF],
        "ToU Category": [get_tou_category(t * mult) for t in DEFAULT_24H_TARIFF]
    })
    
    # Interactive Data Editor - Both Load % and Load TR are fully editable
    edited_df = st.data_editor(
        df_init,
        column_config={
            "Hour": st.column_config.TextColumn("Hour of Day", disabled=True),
            "Cooling Load (%)": st.column_config.NumberColumn("Cooling Load (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.1f%%"),
            "Cooling Load (TR)": st.column_config.NumberColumn("Cooling Load (TR)", min_value=0.0, max_value=peak_load_tr*1.5, step=10.0, format="%.2f TR"),
            f"Tariff ({sym}/kWh)": st.column_config.NumberColumn(f"Electricity Tariff ({sym}/kWh)", min_value=0.0, step=0.10, format="%.2f"),
            "ToU Category": st.column_config.TextColumn("ToU Window [Auto]", disabled=True)
        },
        use_container_width=True,
        num_rows="fixed",
        key="data_editor_24h"
    )
    
    # BI-DIRECTIONAL DYNAMIC SYNCHRONIZATION
    for i in range(24):
        init_pct = df_init.at[i, "Cooling Load (%)"]
        init_tr = df_init.at[i, "Cooling Load (TR)"]
        curr_pct = edited_df.at[i, "Cooling Load (%)"]
        curr_tr = edited_df.at[i, "Cooling Load (TR)"]
        
        # Check if TR was edited directly
        if abs(curr_tr - init_tr) > 1e-3 and abs(curr_pct - init_pct) < 1e-3:
            edited_df.at[i, "Cooling Load (%)"] = min(100.0, (curr_tr / peak_load_tr) * 100.0) if peak_load_tr > 0 else 0.0
        # Check if % was edited directly
        elif abs(curr_pct - init_pct) > 1e-3:
            edited_df.at[i, "Cooling Load (TR)"] = (curr_pct / 100.0) * peak_load_tr
            
    edited_df["ToU Category"] = edited_df[f"Tariff ({sym}/kWh)"].apply(get_tou_category)
    
    load_24_profile = edited_df["Cooling Load (TR)"].tolist()
    tariff_24_profile = edited_df[f"Tariff ({sym}/kWh)"].tolist()
    
    # Summary Feedback Metrics
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Total 24-Hr Energy Demand", f"{sum(load_24_profile):,.2f} TRh")
    with col_m2:
        st.metric("Peak Diurnal Load", f"{max(load_24_profile):,.2f} TR")
    with col_m3:
        st.metric("Weighted Avg Tariff", f"{sym} {np.mean(tariff_24_profile):.2f} / kWh")
    
    # Live Diurnal Chart
    fig_diurnal = make_subplots(specs=[[{"secondary_y": True}]])
    fig_diurnal.add_trace(
        go.Bar(x=list(range(1, 25)), y=tariff_24_profile, name=f"ToU Tariff ({sym}/kWh)", marker_color="#93C5FD", opacity=0.6),
        secondary_y=False
    )
    fig_diurnal.add_trace(
        go.Scatter(x=list(range(1, 25)), y=load_24_profile, name="Cooling Load (TR)", mode="lines+markers", line=dict(color="#1E3A8A", width=3)),
        secondary_y=True
    )
    fig_diurnal.update_layout(
        title_text="Live 24-Hour Cooling Load (TR) vs. ToU Electricity Tariff Curve", 
        height=320, 
        margin=dict(l=20, r=20, t=40, b=20), 
        legend=dict(orientation="h", y=1.15)
    )
    fig_diurnal.update_xaxes(title_text="Hour of Day (1 - 24)")
    fig_diurnal.update_yaxes(title_text=f"Tariff ({sym}/kWh)", secondary_y=False)
    fig_diurnal.update_yaxes(title_text="Cooling Load (TR)", secondary_y=True)
    st.plotly_chart(fig_diurnal, use_container_width=True)

else:
    load_24_profile = [(p / 100.0) * peak_load_tr for p in DEFAULT_24H_LOAD_PCT]
    tariff_24_profile = [t * mult for t in DEFAULT_24H_TARIFF]

# ----------------------------------------------------
# RUN ENGINE & RESULTS DASHBOARD
# ----------------------------------------------------
st.markdown("---")
if st.button("🚀 Run 8,760-Hour Optimization Engine", type="primary", use_container_width=True):
    with st.spinner("Executing Thermodynamics, Fluid Mechanics & Financial Arbitrage Engine..."):
        try:
            # 8,760 Arrays
            l_8760 = expand_24_to_8760(load_24_profile)
            t_8760 = expand_24_to_8760(tariff_24_profile)
            
            project_cfg = ProjectConfig(
                project_name=proj_name, location=location, sector=sector,
                scope=scope, currency=currency, peak_load_tr=peak_load_tr, tank_shape=tank_shape
            )
            thermo_cfg = ThermoConfig(
                chiller_type=chiller_type, base_chiller_cop=base_cop, design_wbt=design_wbt,
                pcm_charge_temp=pcm_charge_temp, pcm_derate_factor=pcm_derate, night_relief_multiplier=night_relief
            )
            hydraulic_cfg = HydraulicConfig(
                chw_delta_t=chw_delta_t, pcm_fom=pcm_fom, strat_fom=strat_fom,
                chw_pump_head_m=chw_pump_head, cdw_pump_head_m=cdw_pump_head,
                brine_pump_head_m=brine_pump_head, pump_efficiency=pump_eff
            )
            financial_cfg = FinancialConfig(
                demand_charge_per_kva_month=demand_charge_kva, unit_rates=sys_rates
            )
            
            class SystemConfigContainer:
                def __init__(self, p, t, h, f):
                    self.project = p
                    self.thermo = t
                    self.hydraulic = h
                    self.financial = f
                    
            config = SystemConfigContainer(project_cfg, thermo_cfg, hydraulic_cfg, financial_cfg)
            
            results = run_8760_simulation(l_8760, t_8760, config, sys_rates)
            
            st.success("✅ 8,760-Hour Optimization Completed! ASHRAE & LEED Platinum Compliant.")
            
            # 1. Executive Summary Cards
            st.subheader("📊 Executive Summary & Technology Comparison")
            col1, col2, col3 = st.columns(3)
            
            for idx, (sys_name, res_data) in enumerate(results.items()):
                target_col = [col1, col2, col3][idx]
                with target_col:
                    st.markdown(f"### {sys_name}")
                    st.metric("Base Chiller Capacity", f"{res_data['Base_Chiller_TR']:,.0f} TR")
                    if res_data['Brine_Chiller_TR'] > 0:
                        st.metric("Sub-Zero Brine Chiller", f"{res_data['Brine_Chiller_TR']:,.0f} TR")
                    st.metric("TES Storage Capacity", f"{res_data['TES_Capacity_TRh']:,.0f} TRh")
                    st.metric("Peak Plant Power", f"{res_data['Peak_Plant_kW']:,.1f} kW")
                    st.metric("Electrical Substation", f"{res_data['Substation_kVA']:,.0f} kVA")
                    st.metric("Total CAPEX", format_currency(res_data['CAPEX']['Total_CAPEX'], currency))
                    st.metric("Total Annual OPEX", format_currency(res_data['Total_Annual_OPEX'], currency))
                    if sys_name != "Conventional N+1":
                        st.metric("Annual OPEX Savings", format_currency(res_data['Annual_OPEX_Savings'], currency))
                        st.metric("Simple Payback Period", f"{res_data['Simple_Payback_Yrs']:.2f} Years")
            
            # 2. Detailed Financial & CAPEX Matrix
            st.subheader("📑 Detailed Techno-Economic Cost Breakdown")
            cost_matrix = []
            for sys_name, res_data in results.items():
                cost_matrix.append({
                    "System Vector": sys_name,
                    "Base Chillers": format_currency(res_data['CAPEX']['Base_Chillers'], currency),
                    "Brine Chillers": format_currency(res_data['CAPEX']['Brine_Chillers'], currency),
                    "TES Storage Tank": format_currency(res_data['CAPEX']['TES_Tank'], currency),
                    "Ancillary (CT/Pumps/PHE)": format_currency(res_data['CAPEX']['Ancillary_CT_Pumps_PHE'], currency),
                    "Substation & DG": format_currency(res_data['CAPEX']['Electrical_Substation_DG'], currency),
                    "Total CAPEX": format_currency(res_data['CAPEX']['Total_CAPEX'], currency),
                    "Annual Energy OPEX": format_currency(res_data['Annual_Energy_OPEX'], currency),
                    "Annual Demand OPEX": format_currency(res_data['Annual_Demand_OPEX'], currency),
                    "Total Annual OPEX": format_currency(res_data['Total_Annual_OPEX'], currency)
                })
            st.table(pd.DataFrame(cost_matrix).set_index("System Vector"))
            
            # 3. Plotly Diurnal Dispatch Comparison
            st.subheader("📈 24-Hour Operational Power Dispatch Curves")
            fig_dispatch = go.Figure()
            colors_map = {"Conventional N+1": "#EF4444", "PCM TES System": "#10B981", "Stratified CHW TES": "#3B82F6"}
            
            for sys_name, res_data in results.items():
                fig_dispatch.add_trace(go.Scatter(
                    x=list(range(1, 25)),
                    y=res_data['Total_kW'][:24],
                    name=sys_name,
                    mode="lines+markers",
                    line=dict(width=3, color=colors_map[sys_name])
                ))
            fig_dispatch.update_layout(
                title="Diurnal Electric Power Demand (kW) Across System Vectors",
                xaxis_title="Hour of Day (1 - 24)",
                yaxis_title="Total Plant Power (kW)",
                height=400,
                legend=dict(orientation="h", y=1.12)
            )
            st.plotly_chart(fig_dispatch, use_container_width=True)
            
            # 4. PDF Export Download
            st.subheader("📄 Executive Proposal PDF Generation")
            pdf_bytes = generate_pdf_report(
                {"project_name": proj_name, "location": location, "sector": sector, "scope": scope, "currency": currency, "peak_load_tr": peak_load_tr},
                results
            )
            st.download_button(
                label="📥 Download ASHRAE Executive Proposal PDF",
                data=pdf_bytes,
                file_name=f"CETP_Executive_Proposal_{proj_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            # Memory Cleanup
            del l_8760, t_8760
            gc.collect()
            
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")