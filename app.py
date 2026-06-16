"""
Google Play Store Analytics — Interactive Dashboard
====================================================
Streamlit app implementing the 6 internship visualizations on the Kaggle
Google Play Store dataset, with interactive slicers and IST time-window gating.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Deploy free:
    Push this repo to GitHub -> share.streamlit.io -> "New app" -> point to app.py
"""
import hashlib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_prep import load_data, in_ist_window, TRANS

st.set_page_config(page_title="Play Store Analytics", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_data
def get_data():
    return load_data()


try:
    df = get_data()
except FileNotFoundError:
    st.error("Place `googleplaystore.csv` (and `googleplaystore_user_reviews.csv`) "
             "next to app.py, then reload.")
    st.stop()

# ----------------------------------------------------------------------------
# Sidebar — global slicers (interactive filtering / drill-down)
# ----------------------------------------------------------------------------
st.sidebar.title("🎛️ Filters")
override = st.sidebar.toggle("Ignore IST time windows (preview all)", value=True,
                             help="When OFF, each chart only shows during its IST window.")

all_cats = sorted(df["Category"].dropna().unique())
sel_cats = st.sidebar.multiselect("Category slicer (applies to all tabs)",
                                  all_cats, default=all_cats)
rmin, rmax = st.sidebar.slider("Rating range", 0.0, 5.0, (0.0, 5.0), 0.1)
types = st.sidebar.multiselect("App type", ["Free", "Paid"], default=["Free", "Paid"])
st.sidebar.caption("Tab-specific filters (from the brief) are applied automatically "
                   "inside each chart.")

base = df[df["Category"].isin(sel_cats) &
          df["Rating"].between(rmin, rmax) &
          df["Type"].isin(types)].copy()

st.title("📱 Google Play Store Analytics Dashboard")
st.caption("Six interactive visualizations · IST-gated · built on the Kaggle Google "
           "Play Store dataset")

# KPI header
k1, k2, k3, k4 = st.columns(4)
k1.metric("Apps", f"{len(base):,}")
k2.metric("Categories", base["Category"].nunique())
k3.metric("Total installs", f"{base['Installs'].sum()/1e9:.2f} B")
k4.metric("Avg rating", f"{base['Rating'].mean():.2f}")

tabs = st.tabs(["1 · Grouped Bar", "2 · Choropleth", "3 · Dual-Axis",
                "4 · Time Series", "5 · Bubble", "6 · Stacked Area"])


def gated(start, end, label):
    if in_ist_window(start, end, override):
        return True
    st.info(f"⏰ **{label}** is only visible **{start}:00–{end}:00 IST**. "
            f"Toggle *Ignore IST time windows* in the sidebar to preview.")
    return False


# ----------------------------------------------------------------- Task 1
with tabs[0]:
    st.subheader("Avg Rating & Total Reviews — Top 10 Categories by Installs")
    st.caption("Filters: last update in January · app size ≥ 10M · avg rating ≥ 4.0 · window 3–5 PM IST")
    if gated(15, 17, "Grouped bar chart"):
        # filter apps: updated in January AND size >= 10 MB
        d = base[(base["Update_Month"] == 1) & (base["Size_MB"] >= 10)]
        g = d.groupby("Category").agg(AvgRating=("Rating", "mean"),
                                      TotalReviews=("Reviews", "sum"),
                                      Installs=("Installs", "sum")).reset_index()
        g = g[g["AvgRating"] >= 4.0]                       # drop categories rating < 4.0
        g = g.sort_values("Installs", ascending=False).head(10)
        if g.empty:
            st.warning("No categories pass these filters in the current selection.")
        else:
            fig = go.Figure()
            fig.add_bar(x=g["Category"], y=g["AvgRating"], name="Avg Rating", yaxis="y1")
            fig.add_bar(x=g["Category"], y=g["TotalReviews"], name="Total Reviews", yaxis="y2")
            fig.update_layout(barmode="group", yaxis=dict(title="Avg Rating"),
                              yaxis2=dict(title="Total Reviews", overlaying="y", side="right"),
                              legend=dict(orientation="h"), height=520)
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------- Task 2
with tabs[1]:
    st.subheader("Global Installs by Country — Top 5 Categories")
    st.caption("Filters: exclude categories starting A/C/G/S · top 5 by installs · highlight >1M · window 6–8 PM IST")
    st.info("Note: dataset has no country field. A deterministic synthetic country "
            "is assigned per app so the map renders (documented demo mapping).")
    if gated(18, 20, "Choropleth map"):
        d = base[~base["Category"].str[0].isin(list("ACGS"))]
        top = (d.groupby("Category")["Installs"].sum()
                 .sort_values(ascending=False).head(5).index.tolist())
        d = d[d["Category"].isin(top)]
        if d.empty:
            st.warning("No categories pass these filters in the current selection.")
        else:
            countries = ["USA", "IND", "BRA", "GBR", "DEU", "FRA", "JPN", "RUS",
                         "CAN", "AUS", "MEX", "IDN", "NGA", "ZAF", "KOR"]
            d = d.assign(Country=d["App"].apply(
                lambda a: countries[int(hashlib.md5(str(a).encode()).hexdigest(), 16) % len(countries)]))
            geo = d.groupby("Country")["Installs"].sum().reset_index()
            big = d.groupby("Category")["Installs"].sum()
            big = big[big > 1_000_000].index.tolist()
            fig = px.choropleth(geo, locations="Country", color="Installs",
                                locationmode="ISO-3", color_continuous_scale="Viridis")
            # visual highlight: annotate the >1M categories directly on the figure
            if big:
                fig.add_annotation(x=0.5, y=1.08, xref="paper", yref="paper",
                                   showarrow=False, align="center",
                                   text="🔴 <b>Highlighted (installs > 1M):</b> " + ", ".join(big),
                                   font=dict(color="crimson", size=14),
                                   bgcolor="rgba(255,220,220,0.6)", bordercolor="crimson",
                                   borderwidth=1, borderpad=4)
            fig.update_layout(height=560, margin=dict(l=0, r=0, t=60, b=0))
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------- Task 3
with tabs[2]:
    st.subheader("Avg Installs & Revenue — Free vs Paid (Top 3 Categories)")
    st.caption("Filters: installs ≥ 10k · revenue ≥ $10k · Android > 4.0 · size > 15M · "
               "Everyone · name ≤ 30 chars · window 1–2 PM IST")
    st.caption("⚠️ Revenue ≥ $10k is applied literally to every app; free apps (revenue $0) "
               "are therefore excluded, so this view typically shows paid apps.")
    if gated(13, 14, "Dual-axis chart"):
        d = base[(base["Installs"] >= 10000) & (base["Revenue"] >= 10000) &
                 (base["Android_Min"] > 4.0) & (base["Size_MB"] > 15) &
                 (base["Content Rating"] == "Everyone") & (base["NameLen"] <= 30)]
        top3 = (d.groupby("Category")["Installs"].sum()
                  .sort_values(ascending=False).head(3).index.tolist())
        d = d[d["Category"].isin(top3)]
        if d.empty:
            st.warning("No apps pass these filters in the current selection.")
        else:
            g = d.groupby(["Category", "Type"]).agg(AvgInstalls=("Installs", "mean"),
                                                     AvgRevenue=("Revenue", "mean")).reset_index()
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            for t, col in [("Free", "#4C72B0"), ("Paid", "#DD8452")]:
                sub = g[g["Type"] == t]
                fig.add_bar(x=sub["Category"], y=sub["AvgInstalls"], name=f"{t} avg installs",
                            marker_color=col)
            for t, col in [("Free", "#55A868"), ("Paid", "#C44E52")]:
                sub = g[g["Type"] == t]
                fig.add_trace(go.Scatter(x=sub["Category"], y=sub["AvgRevenue"],
                              mode="lines+markers", name=f"{t} avg revenue",
                              line=dict(color=col)), secondary_y=True)
            fig.update_yaxes(title_text="Avg Installs", secondary_y=False)
            fig.update_yaxes(title_text="Avg Revenue ($)", secondary_y=True)
            fig.update_layout(barmode="group", legend=dict(orientation="h"), height=520)
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------- Task 4
with tabs[3]:
    st.subheader("Installs Over Time by Category (>20% MoM growth shaded)")
    st.caption("Filters: category E/C/B · name not x/y/z · no letter 'S' · reviews > 500 · "
               "translate Beauty→Hindi, Business→Tamil, Dating→German · window 6–9 PM IST")
    if gated(18, 21, "Time series chart"):
        d = base[base["Category"].str[0].isin(list("ECB")) & (base["Reviews"] > 500) &
                 ~base["App"].str[0].str.lower().isin(list("xyz")) &
                 ~base["App"].str.contains("S", case=True, na=False)].dropna(subset=["Update_Period"])
        if d.empty:
            st.warning("No apps pass these filters in the current selection.")
        else:
            ts = (d.groupby(["Update_Period", "Category"])["Installs"].sum()
                    .reset_index().sort_values("Update_Period"))
            fig = go.Figure()
            for cat in ts["Category"].unique():
                sub = ts[ts["Category"] == cat].copy()
                sub["MoM"] = sub["Installs"].pct_change()
                fig.add_trace(go.Scatter(x=sub["Update_Period"], y=sub["Installs"],
                              mode="lines+markers", name=TRANS.get(cat, cat)))
                for i in range(1, len(sub)):
                    if sub["MoM"].iloc[i] > 0.20:
                        fig.add_trace(go.Scatter(
                            x=[sub["Update_Period"].iloc[i-1], sub["Update_Period"].iloc[i]],
                            y=[sub["Installs"].iloc[i-1], sub["Installs"].iloc[i]],
                            fill="tozeroy", mode="none", showlegend=False,
                            fillcolor="rgba(255,165,0,0.25)"))
            fig.update_layout(xaxis_title="Month", yaxis_title="Total Installs", height=520)
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------- Task 5
with tabs[4]:
    st.subheader("App Size vs Rating (bubble = installs)")
    st.caption("Filters: rating > 3.5 · selected categories · reviews > 500 · no 'S' · "
               "subjectivity > 0.5 · installs > 50k · Game highlighted pink · window 5–7 PM IST")
    if gated(17, 19, "Bubble chart"):
        cats = ["GAME", "BEAUTY", "BUSINESS", "COMICS", "COMMUNICATION", "DATING",
                "ENTERTAINMENT", "SOCIAL", "EVENTS"]
        d = base[base["Category"].isin(cats) & (base["Rating"] > 3.5) &
                 (base["Reviews"] > 500) & (base["Installs"] > 50000) &
                 ~base["App"].str.contains("S", case=True, na=False) &
                 (base["Sentiment_Subjectivity"] > 0.5)].copy()
        if d.empty:
            st.warning("No apps pass these filters (often the sentiment file is missing).")
        else:
            d["Label"] = d["Category"].replace(TRANS)
            fig = px.scatter(d, x="Size_MB", y="Rating", size="Installs", color="Label",
                             hover_name="App", size_max=50)
            fig.for_each_trace(lambda t: t.update(marker_color="hotpink") if t.name == "GAME" else None)
            fig.update_layout(height=520)
            st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------- Task 6
with tabs[5]:
    st.subheader("Cumulative Installs Over Time by Category")
    st.caption("Filters: rating ≥ 4.2 · no digits in name · category T/P · reviews > 1000 · "
               "size 20–80MB · translate Travel→French, Productivity→Spanish, Photography→Japanese · "
               "window 4–6 PM IST")
    if gated(16, 18, "Stacked area chart"):
        d = base[base["Category"].str[0].isin(list("TP")) & (base["Rating"] >= 4.2) &
                 (base["Reviews"] > 1000) & (base["Size_MB"].between(20, 80)) &
                 ~base["App"].str.contains(r"\d", regex=True, na=False)].dropna(subset=["Update_Period"])
        if d.empty:
            st.warning("No apps pass these filters in the current selection.")
        else:
            ts = (d.groupby(["Update_Period", "Category"])["Installs"].sum()
                    .reset_index().sort_values("Update_Period"))
            ts["Cumulative"] = ts.groupby("Category")["Installs"].cumsum()
            ts["Label"] = ts["Category"].replace(TRANS)
            fig = px.area(ts, x="Update_Period", y="Cumulative", color="Label")

            # color-intensity highlight: shade any month where any category grew >25% MoM
            hot_months = set()
            for cat in ts["Category"].unique():
                sub = ts[ts["Category"] == cat].sort_values("Update_Period")
                growth = sub["Installs"].pct_change()
                hot_months.update(sub.loc[growth > 0.25, "Update_Period"].tolist())
            periods = pd.to_datetime(sorted(pd.Series(ts["Update_Period"].unique())))
            half = (periods[1] - periods[0]) / 2 if len(periods) > 1 else pd.Timedelta(days=15)
            for m in sorted(hot_months):
                m = pd.Timestamp(m)
                fig.add_vrect(x0=m - half, x1=m + half,
                              fillcolor="rgba(0,0,0,0.28)", line_width=0, layer="above")
            fig.update_layout(height=540, xaxis_title="Month", yaxis_title="Cumulative Installs")
            st.plotly_chart(fig, use_container_width=True)
            if hot_months:
                st.caption("Intensified bands mark months with >25% MoM growth in any category: "
                           + ", ".join(f"{m:%Y-%m}" for m in sorted(hot_months)))

st.divider()
st.caption("Built for the Elevance Skills internship · dataset: Kaggle 'Google Play Store Apps'")
