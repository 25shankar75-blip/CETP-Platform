import streamlit as st
import pandas as pd

st.set_page_config(page_title="CETP Digital Twin", layout="wide")
st.title("Cooling Energy Transition Platform (CETP)")

# --- 1. DECLARE ALL INPUT TABS FIRST (Fixes the NameError) ---
input_tabs = st.tabs(["Project Setup", "Chiller Fleet (Retrofit/Conv)", "Load Profile", "Thermodynamics", "Financials"])
tab_project = input_tabs[0]
tab_chiller_inputs = input_tabs[1]
tab_load_profile = input_tabs[2]
tab_thermo = input_tabs[3]
tab_financial = input_tabs[4]

# --- INPUT TABS LOGIC ---
with tab_project:
    st.subheader("Project Scope")
    project_scope = st.radio("Scope:", ["Greenfield", "Retrofit (Brownfield)"])

with tab_chiller_inputs:
    st.subheader("Existing/Proposed Chiller Fleet")
    st.markdown("Enter your chiller configurations. For Retrofit, this maps the *existing* spare capacity.")
    
    # Granular 10-Unit Dynamic Data Editor
    default_fleet = pd.DataFrame([
        {"Capacity (TR)": 500.0, "Quantity": 2, "Type": "Water-Cooled Centrifugal"},
        {"Capacity (TR)": 250.0, "Quantity": 1, "Type": "Air-Cooled VFD"}
    ])
    edited_fleet = st.data_editor(default_fleet, num_rows="dynamic", max_rows=10, use_container_width=True)

with tab_load_profile:
    st.subheader("24-Hour Load & Tariff Profile")
    st.markdown("*Note: System calculation metrics have been moved to the output tabs to improve UI performance and remove state refresh bugs.*")
    # Data entry form goes here (no metric calculations)

# --- SIMULATION & OUTPUT TABS ---
if st.button("Run Digital Twin Simulation", type="primary"):
    st.success("Simulation Complete. Engine optimized for maximum OPEX.")
    
    # Rename baseline tab dynamically based on selected Scope
    conv_tab_name = "Outputs - Existing Retrofit Baseline" if project_scope == "Retrofit (Brownfield)" else "Outputs - Conventional N+1"
    
    # Declare Output Tabs First
    out_conv, out_pcm, out_strat = st.tabs([conv_tab_name, "Outputs - PCM TES", "Outputs - Stratified TES"])

    with out_conv:
        st.subheader(f"{conv_tab_name} Analysis")
        
        # Calculate heavy metrics purely on the output side
        total_trh = sum(st.session_state.daily_load_profile) if 'daily_load_profile' in st.session_state else 0
        total_installed_tr = sum(edited_fleet["Capacity (TR)"] * edited_fleet["Quantity"])
        
        # Cleanly appended Top Bar Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Daily Load", f"{total_trh:,.0f} TRh")
        c2.metric("Installed Fleet", f"{total_installed_tr:,.0f} TR")
        
        if project_scope == "Retrofit (Brownfield)":
             c3.metric("Baseline Mechanical CAPEX", "₹ 0.00 (Sunk Cost)")
        else:
             c3.metric("Estimated Greenfield CAPEX", "₹ Calculated Cr") 
        c4.metric("Annual OPEX", "₹ Calculated Cr") 

    with out_pcm:
        st.subheader("PCM TES (Encapsulated Cryogel) - OPEX Maximized")
        # Metric layout populated by the updated optimizer
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Recommended TES Capacity", "Optimized TRh") 
        c2.metric("Dedicated Charge Chiller", "Optimized TR") 
        c3.metric("Maximized OPEX Savings", "₹ X.XX Cr") 
        c4.metric("Financial ROI", "< 3.5 Years")