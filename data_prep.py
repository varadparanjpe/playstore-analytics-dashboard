"""
Shared data loading & cleaning for the Google Play Store analytics project.
Used by both the Streamlit dashboard (app.py) and the notebook.
"""
import pandas as pd
import numpy as np
import re
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# Category-name translations required by the brief
TRANS = {
    "BEAUTY": "सौंदर्य",            # Hindi
    "BUSINESS": "வணிகம்",          # Tamil
    "DATING": "Partnersuche",       # German
    "TRAVEL_AND_LOCAL": "Voyages et local",   # French
    "PRODUCTIVITY": "Productividad",          # Spanish
    "PHOTOGRAPHY": "写真",                     # Japanese
}


def _size_to_mb(x):
    s = str(x).strip()
    if s.endswith("M"):
        return float(s[:-1])
    if s.endswith("k"):
        return float(s[:-1]) / 1024
    if s.endswith("G"):
        return float(s[:-1]) * 1024
    return np.nan


def _android_min(x):
    m = re.match(r"(\d+\.?\d*)", str(x))
    return float(m.group(1)) if m else np.nan


def load_data(playstore_csv="googleplaystore.csv",
              reviews_csv="googleplaystore_user_reviews.csv"):
    """Return a cleaned, analysis-ready DataFrame."""
    raw = pd.read_csv(playstore_csv)
    df = raw.dropna(subset=["Category"]).copy()
    df = df[df["Category"] != "1.9"]                      # known corrupt row

    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    df["Reviews"] = pd.to_numeric(df["Reviews"], errors="coerce")

    df["Installs"] = (df["Installs"].astype(str)
                      .str.replace("[+,]", "", regex=True)
                      .replace("Free", np.nan))
    df["Installs"] = pd.to_numeric(df["Installs"], errors="coerce")

    df["Price"] = df["Price"].astype(str).str.replace("$", "", regex=False)
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0)

    df["Size_MB"] = df["Size"].apply(_size_to_mb)
    df["Android_Min"] = df["Android Ver"].apply(_android_min)

    df["Last Updated"] = pd.to_datetime(df["Last Updated"], errors="coerce")
    df["Update_Month"] = df["Last Updated"].dt.month
    df["Update_Period"] = df["Last Updated"].dt.to_period("M").dt.to_timestamp()

    df["Revenue"] = np.where(df["Type"] == "Paid",
                             df["Price"] * df["Installs"], 0)
    df["NameLen"] = df["App"].astype(str).str.len()

    df = (df.sort_values("Reviews", ascending=False)
            .drop_duplicates("App").reset_index(drop=True))

    # merge mean sentiment subjectivity (Task 5)
    try:
        rev = pd.read_csv(reviews_csv)
        sent = (rev.dropna(subset=["Sentiment_Subjectivity"])
                   .groupby("App")["Sentiment_Subjectivity"].mean()
                   .rename("Sentiment_Subjectivity"))
        df = df.merge(sent, on="App", how="left")
    except FileNotFoundError:
        df["Sentiment_Subjectivity"] = np.nan

    return df


def in_ist_window(start_hour, end_hour, override=False):
    """True if 'now' (IST) is within [start_hour, end_hour) or override set."""
    if override:
        return True
    now = datetime.now(IST)
    h = now.hour + now.minute / 60
    return start_hour <= h < end_hour
