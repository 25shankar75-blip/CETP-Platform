"""
CETP Digital Twin - Master Streamlit Frontend
File: app.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import json
import requests

from schemas import CURRENCY_MULTIPLIERS, ScopeEnum, FinancialConfig
from financial_engine import format_currency
from optimizer import optimize_plant
from report_generator import generate_pdf_report, generate_word_report

st.set_page_config(page_title="CETP Digital Twin Platform", page_icon="❄️", layout="wide")
st.markdown("""<style>.main-header { font-size: 2.2rem; font-weight: 800; color: #1e3d59; margin-bottom: 0px; } .sub-header { font-size: 1.05rem; font-weight: 500; color: #438a5e; margin-bottom: 18px; }</style>""", unsafe_allow_html=True)
st.markdown('<p class="main-header">❄️ Cooling Energy Transition Platform (CETP)</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">ASHRAE-Compliant, LEED Platinum-Grade Thermal Energy Storage Digital Twin</p>', unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_live_currency():
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/INR", timeout=3).json()
        if resp.get("result") == "success": return resp["rates"]
    except: pass
    return None

if "df_24h" not in st.session_state:
    st.session_state.df_24h = pd.DataFrame({
        "Hour": np.arange(1, 25),
        "Load (TR)": [1047.8]*8 + [1746.3]*2 + [2095.6]*2 + [2794.1]*4 + [2444.9]*4 + [2095.6]*2 + [1047.8]*2,
        "Tariff": [5.62]*6 + [6.11]*12 + [7.03]*4 + [5.62]*2,
        " ": [""]*24 # Anti-freeze column
    })

if "chiller_fleet" not in st.session_state:
    st.session_state.chiller_fleet = pd.DataFrame([{"Capacity (TR)": 1000.0, "Quantity": 2, "Type": "Water-Cooled Centrifugal"}])

if "opt_results" not in st.session_state:
    st.session_state.opt_results = None

# --- SIDEBAR NAV ---
st.sidebar.title("Navigation")
nav = st.sidebar.radio("Go to", ["🎛️ Project Setup", "📊 Load & Tariffs", "🏭 Baseline Output", "🧊 PCM TES Optimum", "🌊 Stratified TES Optimum", "💰 Financials", "📑 Report Export"])

# --- OPTIMIZER TRIGGER ---
st.sidebar.markdown("---")
if st.sidebar.button("▶️ Run Digital Twin Optimization", type="primary"):
    rates = FinancialConfig() # Pulls defaults defined in schema
    st.session_state.opt_results = optimize_plant(
        st.session_state.chiller_fleet, 
        st.session_state.df_24h["Load (TR)"].values, 
        st.session_state.df_24h["Tariff"].values, 
        st.session_state.get("proj_type", "Brownfield (Retrofit)"), 
        rates
    )
    st.sidebar.success("Optimization Complete!")

if nav == "🎛️ Project Setup":
    st.header("🎛️ Setup & Plant Configuration")
    c1, c2, c3 = st.columns(3)
    st.session_state.proj_name = c1.text_input("Project Name", "Rev19 Benchmark")
    st.session_state.location = c2.text_input("Location", "Gurugram, HR")
    st.session_state.currency = c3.selectbox("Currency", list(CURRENCY_MULTIPLIERS.keys()))
    
    st.session_state.proj_type = c1.selectbox("Scope", ["Greenfield", "Brownfield (Retrofit)"])
    st.session_state.industry = c2.selectbox("Industry", ["Data Centre", "Pharmaceutical", "Commercial", "FMCG"])
    
    st.subheader("Chiller Fleet / Existing Assets")
    st.session_state.chiller_fleet = st.data_editor(st.session_state.chiller_fleet, num_rows="dynamic", use_container_width=True)

elif nav == "📊 Load & Tariffs":
    st.header("📊 Interactive 24-Hour Diurnal Profile")
    st.session_state.df_24h = st.data_editor(st.session_state.df_24h, num_rows="fixed", use_container_width=True, hide_index=True)

elif nav in ["🏭 Baseline Output", "🧊 PCM TES Optimum", "🌊 Stratified TES Optimum"]:
    if not st.session_state.opt_results: st.warning("Please run the Optimizer first.")
    else:
        res = st.session_state.opt_results
        curr = st.session_state.currency
        
        if "Baseline" in nav:
            data = res['c']
            st.header("🏭 Existing Retrofit Baseline" if st.session_state.proj_type == "Brownfield (Retrofit)" else "🏭 Conventional N+1 Baseline")
        elif "PCM" in nav:
            data = res['p']
            st.header(f"🧊 PCM TES Optimum ({data['tes_trh']:.0f} TRh)")
            st.info(f"Dedicated Brine Charge Chiller Required: {data['chiller_tr']:.0f} TR")
        else:
            data = res['s']
            st.header(f"🌊 Stratified TES Optimum ({data['tes_trh']:.0f} TRh)")

        c1, c2, c3 = st.columns(3)
        c1.metric("Turnkey CAPEX", format_currency(data['capex'], curr))
        c2.metric("Annual OPEX", format_currency(data['opex'], curr))
        if "Baseline" not in nav: c3.metric("Simple Payback", f"{data['pb']:.2f} Yrs")
        
        df_power = pd.DataFrame({
            "Hour": np.arange(1, 25),
            "Total Demand (kW)": data['sim']['total_kw'],
            "Compressor (kW)": data['sim']['comp_kw'],
            "Pumps & Aux (kW)": data['sim']['pump_kw']
        })
        st.dataframe(df_power, use_container_width=True)

elif nav == "💰 Financials":
    if not st.session_state.opt_results: st.warning("Run optimizer first.")
    else:
        res = st.session_state.opt_results
        curr = st.session_state.currency
        st.header("💰 Executive Economics & Breakdown")
        
        df_bk = pd.DataFrame({
            "Item": list(res['c']['bk'].keys()),
            "Baseline": [format_currency(v, curr) for v in res['c']['bk'].values()],
            "PCM TES Opt.": [format_currency(v, curr) for v in res['p']['bk'].values()],
            "Strat. TES Opt.": [format_currency(v, curr) for v in res['s']['bk'].values()]
        })
        st.table(df_bk)

elif nav == "📑 Report Export":
    if not st.session_state.opt_results: st.warning("Run optimizer first.")
    else:
        st.subheader("📑 Report Dashboard & Export")
        c1, c2 = st.columns(2)
        
        pdf = generate_pdf_report(st.session_state.proj_name, st.session_state.location, st.session_state.industry, st.session_state.proj_type, st.session_state.currency, st.session_state.chiller_fleet, st.session_state.df_24h["Load (TR)"].values, st.session_state.df_24h["Tariff"].values, st.session_state.opt_results)
        c1.download_button("📥 Export High-Def PDF Report", data=pdf, file_name=f"CETP_{st.session_state.proj_name}.pdf", mime="application/pdf", use_container_width=True)