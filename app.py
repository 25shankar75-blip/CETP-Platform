import streamlit as st
import pandas as pd
from optimizer import optimize_tes_capacity

st.set_page_config(page_title="CETP Digital Twin", layout="wide")
st.title("Cooling Energy Transition Platform (CETP)")

# --- Default Session State Initialization ---
if 'daily_load_profile' not in st.session_state:
    st.session_state.daily_load_profile = [2500]*8 + [4500]*8 + [3000]*8 
if 'tariff_profile' not in st.session_state:
    st.session_state.tariff_profile = [6.0]*8 + [12.0]*8 + [9.0]*8
if 'dg_outage_hours' not in st.session_state:
    st.session_state.dg_outage_hours = [0.0]*12 + [22.0]*4 + [0.0]*8 

# --- DECLARE ALL INPUT TABS FIRST (Fixes NameError) ---
input_tabs = st.tabs(["Project Setup", "Chiller Fleet", "Load Profile", "Thermodynamics", "Financials"])

with input_tabs[0]:
    with st.form("project_form"):
        st.subheader("Project Scope & Location")
        project_scope = st.radio("Scope:", ["Greenfield", "Retrofit (Brownfield)"])
        currency = st.selectbox("Currency Selection:", ["INR (₹)", "USD ($)", "EUR (€)", "AED (د.إ)", "MYR (RM)"])
        st.form_submit_button("Save Setup")

with input_tabs[1]:
    with st.form("chiller_form"):
        st.subheader("Existing/Proposed Chiller Fleet")
        st.markdown("Enter your chiller configurations. For Retrofit, this maps the *existing* spare capacity.")
        
        default_fleet = pd.DataFrame([
            {"Capacity (TR)": 500.0, "Quantity": 2, "Type": "Water-Cooled Centrifugal"},
            {"Capacity (TR)": 250.0, "Quantity": 1, "Type": "Air-Cooled VFD"}
        ])
        
        # ERROR FIX: Removed invalid 'max_rows=10'. Streamlit will now render perfectly.
        edited_fleet = st.data_editor(default_fleet, num_rows="dynamic", use_container_width=True)
        st.form_submit_button("Save Fleet Configuration")

with input_tabs[2]:
    with st.form("load_form"):
        st.subheader("24-Hour Load & Tariff Profile")
        st.markdown("*Note: System calculation metrics are moved to the output tabs to improve UI performance.*")
        st.line_chart(st.session_state.daily_load_profile)
        st.form_submit_button("Confirm Load Profiles")

with input_tabs[3]:
    with st.form("thermo_form"):
        st.subheader("Thermodynamics (CoolProp & WBT)")
        st.number_input("CHW Supply (°C)", value=5.0)
        st.number_input("Ambient Design WBT (°C)", value=28.0)
        st.form_submit_button("Save Thermodynamics")

with input_tabs[4]:
    with st.form("fin_form"):
        st.subheader("Financial Engine Variables")
        st.number_input("Discount Rate (%)", value=10.0)
        st.form_submit_button("Save Financial Settings")

st.divider()

# --- SIMULATION EXECUTOR ---
if st.button("🚀 Run Digital Twin Simulation", type="primary", use_container_width=True):
    st.success("Simulation Complete. Engine optimized for maximum absolute OPEX.")
    
    chiller_dict_list = edited_fleet.to_dict('records')
    total_installed_tr = sum(edited_fleet["Capacity (TR)"] * edited_fleet["Quantity"])
    total_trh = sum(st.session_state.daily_load_profile)
    
    # Run the aggressive optimizer
    best_pcm, best_strat, bl_opex, bl_capex = optimize_tes_capacity(
        st.session_state.daily_load_profile, 
        st.session_state.tariff_profile, 
        st.session_state.dg_outage_hours,
        project_scope, 
        chiller_dict_list, 
        currency
    )
    
    # Dynamic Retrofit vs Conventional N+1 Output Layout
    conv_tab_name = "Outputs - Existing Retrofit Baseline" if project_scope == "Retrofit (Brownfield)" else "Outputs - Conventional N+1"
    out_tabs = st.tabs([conv_tab_name, "Outputs - PCM TES", "Outputs - Stratified TES", "Hydraulics", "Cash Flows", "Reports"])

    with out_tabs[0]:
        st.subheader(f"{conv_tab_name} Analysis")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Daily Load", f"{total_trh:,.0f} TRh")
        c2.metric("Installed Fleet", f"{total_installed_tr:,.0f} TR")
        
        if project_scope == "Retrofit (Brownfield)":
             c3.metric("Baseline Mechanical CAPEX", f"{currency[:3]} 0.00 (Sunk)")
        else:
             c3.metric("Estimated Greenfield CAPEX", f"{currency[:3]} {bl_capex:,.0f}") 
        c4.metric("Annual OPEX", f"{currency[:3]} {bl_opex:,.0f}") 

    with out_tabs[1]:
        st.subheader("PCM TES (Encapsulated Cryogel) - OPEX Maximized")
        c1, c2, c3, c4 = st.columns(4)
        if best_pcm['trh'] > 0:
            c1.metric("Recommended TES Capacity", f"{best_pcm['trh']:,.0f} TRh") 
            c2.metric("Dedicated Charge Chiller", f"{best_pcm['charge_chiller_tr']:,.0f} TR") 
            c3.metric("Maximized OPEX Savings", f"{currency[:3]} {best_pcm['savings']:,.0f}") 
            c4.metric("Financial ROI", f"{best_pcm['roi']:.2f} Years")
        else:
            st.warning("No feasible PCM configuration found within ROI limits.")

    with out_tabs[2]:
        st.subheader("Stratified Water TES - Spare Capacity Optimized")
        c1, c2, c3, c4 = st.columns(4)
        if best_strat['trh'] > 0:
            c1.metric("Recommended TES Capacity", f"{best_strat['trh']:,.0f} TRh") 
            c2.metric("Required Fleet Charging TR", "Uses Existing Spare") 
            c3.metric("Maximized OPEX Savings", f"{currency[:3]} {best_strat['savings']:,.0f}") 
            c4.metric("Financial ROI", f"{best_strat['roi']:.2f} Years")
        else:
            st.warning("No feasible Stratified configuration found (insufficient spare chiller capacity during off-peak window).")
            
    with out_tabs[3]: st.info("Hydraulic calculations and affinity pump curves render here.")
    with out_tabs[4]: st.info("NPV / Cash flow matrices render here.")
    with out_tabs[5]: st.info("PDF and DOCX download buttons render here.")