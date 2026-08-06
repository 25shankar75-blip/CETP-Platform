import streamlit as st
import pandas as pd

# --- Input Tab 2: Chiller & Plant Configuration ---
with tab_chiller_inputs:
    st.subheader("Existing/Proposed Chiller Fleet")
    st.markdown("Enter your chiller configurations. For Retrofit, this represents the *existing* plant.")
    
    # Dynamic Data Editor for max 10 chillers
    default_fleet = pd.DataFrame([
        {"Capacity (TR)": 500.0, "Quantity": 2, "Type": "Water-Cooled Centrifugal"},
        {"Capacity (TR)": 250.0, "Quantity": 1, "Type": "Air-Cooled VFD"}
    ])
    
    edited_fleet = st.data_editor(
        default_fleet, 
        num_rows="dynamic", 
        max_rows=10, 
        use_container_width=True
    )
    
    project_scope = st.radio("Project Scope", ["Greenfield", "Retrofit (Brownfield)"])

# --- Output Tabs Generation ---
# Rename tab dynamically based on scope
conv_tab_name = "Outputs - Existing Retrofit Baseline" if project_scope == "Retrofit" else "Outputs - Conventional N+1"
out_conv, out_pcm, out_strat = st.tabs([conv_tab_name, "Outputs - PCM TES", "Outputs - Stratified TES"])

with out_conv:
    st.subheader(f"{conv_tab_name} Analysis")
    
    # Calculate here, NOT in the input tab
    total_trh = sum(st.session_state.daily_load_profile)
    total_installed_tr = sum(edited_fleet["Capacity (TR)"] * edited_fleet["Quantity"])
    
    # Top Bar Metrics appended cleanly
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Daily Load", f"{total_trh:,.0f} TRh")
    c2.metric("Installed Fleet", f"{total_installed_tr:,.0f} TR")
    if project_scope == "Retrofit":
         c3.metric("Baseline Mechanical CAPEX", "₹ 0.00 (Sunk Cost)")
    else:
         c3.metric("Estimated CAPEX", "₹ X.XX Cr")
    c4.metric("Annual OPEX", "₹ X.XX Cr")
    
    # Proceed with plotting charts below...

with out_pcm:
    st.subheader("PCM TES (Encapsulated Cryogel) - Optimized")
    c1, c2, c3, c4 = st.columns(4)
    # The optimizer output will push these numbers to ~3017 TRh and ~3.5 yr ROI
    c1.metric("Recommended TES Capacity", f"{best_pcm['trh']:,.0f} TRh")
    c2.metric("Dedicated Charge Chiller", f"{best_pcm['charge_chiller_tr']:,.0f} TR")
    c3.metric("OPEX Savings (vs Baseline)", f"₹ {pcm_savings:,.2f} Cr")
    c4.metric("Financial ROI", f"{best_pcm['roi']:.2f} Years")