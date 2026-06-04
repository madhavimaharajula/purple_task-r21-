import os

import time

import requests

import pandas as pd

import plotly.express as px

import streamlit as st

from streamlit_autorefresh import st_autorefresh



API = os.getenv("STORE_INTEL_API", "http://localhost:8000")



st.set_page_config(page_title="Store Intelligence", layout="wide")

st.sidebar.title("Store Intelligence")

store_id = st.sidebar.text_input("Store ID", "ST1008")

refresh = st.sidebar.slider("Auto-refresh (sec)", 2, 30, 5)



# Auto-refresh the whole script every `refresh` seconds (no while True!)

#st_autorefresh(interval=refresh * 1000, key="auto_refresh")

def safe_get(path, params=None):

    try:

        r = requests.get(f"{API}{path}", params=params, timeout=5)



        if not r.text.strip():

            return []



        return r.json()



    except Exception:

        return []



st.title(f"📊 {store_id} — Live KPIs")



kpis = safe_get(f"/stores/{store_id}/kpis") or {}

funnel = safe_get(f"/stores/{store_id}/funnel") or {}

heatmap = safe_get(f"/stores/{store_id}/heatmap") or {}

events = safe_get(f"/stores/{store_id}/events", {"limit": 50}) or []

anomalies = safe_get(f"/stores/{store_id}/anomalies") or []



# ---- KPI row ----

# ---- KPI row ----

c1, c2, c3, c4, c5, c6 = st.columns(6)



c1.metric("Entries", int(kpis.get("total_entries", 0) or 0))

c2.metric("Exits", int(kpis.get("total_exits", 0) or 0))

c3.metric("Currently Inside", int(kpis.get("current_inside", 0) or 0))

c4.metric("Zone Visits", int(kpis.get("zone_visits", 0) or 0))

c5.metric("Billings", int(kpis.get("billing_events", 0) or 0))



conv = float(kpis.get("conversion_rate", 0) or 0)

c6.metric("Conversion", f"{conv*100:.1f}%")



# ---- Charts ----

col_a, col_b = st.columns(2)



with col_a:

    st.subheader("Funnel")

    if funnel:

        df_f = pd.DataFrame(funnel)



        if "n" in df_f.columns and "stage" in df_f.columns:

            fig_funnel = px.funnel(df_f, x="n", y="stage")

            st.plotly_chart(

                fig_funnel,

                use_container_width=True,

                key="funnel_chart"

            )

        else:

            st.dataframe(df_f)

    else:

        st.info("No funnel data yet.")

with col_b:

    st.subheader("Zone heatmap (visits)")

    if heatmap:

        df_h = pd.DataFrame(heatmap)



        if "zone_name" in df_h.columns and "visits" in df_h.columns:

            fig_heat = px.bar(df_h, x="zone_name", y="visits")

            st.plotly_chart(

                fig_heat,

                use_container_width=True,

                key="heatmap_chart"

            )

        else:

            st.dataframe(df_h)

    else:

        st.info("No heatmap data yet.")



# ---- Recent events ----

st.subheader("Recent events")

if events:

    st.dataframe(pd.DataFrame(events), use_container_width=True)

else:

    st.info("No recent events.")



# ---- Anomalies ----

st.subheader("Anomalies")

if anomalies:

    st.error(pd.DataFrame(anomalies))

else:

    st.success("No anomalies detected")
