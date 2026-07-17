# -*- coding: utf-8 -*-
"""
Created on Tue Jun  3 14:46:13 2025

@author: BrunoFantoli
"""
import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import requests

IRM_WFS_URL = "https://opendata.meteo.be/service/ows"
IRM_LAYERS = {"Hourly": "aws_1hour", "10-minute": "aws_10min", "Daily": "aws_1day"}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "Klareco-DataCleaning/1.0 (energy audits)"}


def parse_wfs_point(wkt):
    """Parse a 'POINT (lat lon)' string as returned by the IRM/KMI WFS service."""
    match = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", str(wkt))
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


@st.cache_data(ttl=86400)
def get_irm_stations():
    """Fetch the list of IRM/KMI automatic weather stations (code, name, location, active dates)."""
    resp = requests.get(
        IRM_WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": "aws:aws_station",
            "outputformat": "text/csv",
        },
        timeout=30,
    )
    resp.raise_for_status()
    stations = pd.read_csv(io.StringIO(resp.text))
    stations[["lat", "lon"]] = stations["the_geom"].apply(lambda g: pd.Series(parse_wfs_point(g)))
    stations["date_begin"] = pd.to_datetime(stations["date_begin"], errors="coerce")
    stations["date_end"] = pd.to_datetime(stations["date_end"], errors="coerce")
    return stations


@st.cache_data(ttl=3600)
def fetch_irm_data(station_code, start_date, end_date, layer):
    """Fetch AWS observations for one station and date range from the IRM/KMI WFS service."""
    cql_filter = (
        f"(code={station_code}) AND "
        f"(timestamp between '{start_date} 00:00:00' AND '{end_date} 23:59:59')"
    )
    resp = requests.get(
        IRM_WFS_URL,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": f"aws:{layer}",
            "outputformat": "text/csv",
            "CQL_FILTER": cql_filter,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


def geocode_address(address):
    """Look up an address via OpenStreetMap Nominatim and return (lat, lon), or None if not found."""
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": address, "format": "json", "limit": 1},
        headers=NOMINATIM_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


st.title("Temperature Sensors Data Cleaning")
st.write("This page is designed to help you clean and prepare your temperature sensor data for an analysis in Excel.")

uploaded_files = st.file_uploader("Choose one or more files", type=["csv", "txt", "xlsx", "xls"], accept_multiple_files=True)
round_time = st.checkbox("Round timestamps to nearest 15 minutes before merging", value=True)

st.markdown("---")
st.markdown("#### Add outside temperature from IRM/KMI")
st.write("Automatically fetch the outside temperature from the closest IRM/KMI weather station instead of downloading it manually from opendata.meteo.be.")

use_irm = st.checkbox("Add outside temperature from IRM/KMI")

if use_irm:
    location_mode = st.radio("Locate the project by:", ["Address", "Coordinates"], horizontal=True)

    lat = lon = None
    if location_mode == "Address":
        address = st.text_input("Project address", placeholder="e.g. Rue Example 12, 1000 Bruxelles")
        if address:
            try:
                coords = geocode_address(address)
            except Exception as e:
                coords = None
                st.error(f"Could not look up that address: {e}")
            if coords:
                lat, lon = coords
                st.caption(f"Coordinates found: {lat:.4f}, {lon:.4f}")
            elif address:
                st.warning("Could not find that address. Try being more specific, or use coordinates instead.")
    else:
        col1, col2 = st.columns(2)
        lat = col1.number_input("Latitude", value=50.8503, format="%.4f")
        lon = col2.number_input("Longitude", value=4.3517, format="%.4f")

    col1, col2 = st.columns(2)
    irm_start = col1.date_input("Start date", key="irm_start")
    irm_end = col2.date_input("End date", key="irm_end")

    granularity = st.selectbox("Data granularity", list(IRM_LAYERS.keys()), index=0)

    if lat is not None and lon is not None:
        try:
            stations = get_irm_stations()
        except Exception as e:
            stations = None
            st.error(f"Could not retrieve the IRM/KMI station list: {e}")

        if stations is not None:
            start_ts = pd.Timestamp(irm_start)
            end_ts = pd.Timestamp(irm_end)
            active = stations[
                (stations["date_begin"] <= start_ts)
                & (stations["date_end"].isna() | (stations["date_end"] >= end_ts))
            ].copy()
            if active.empty:
                active = stations.copy()

            active["distance_km"] = haversine_km(lat, lon, active["lat"], active["lon"])
            nearest = active.sort_values("distance_km").iloc[0]

            st.info(f"Closest active station: **{nearest['name']}** ({nearest['distance_km']:.1f} km away)")

            if st.button("Fetch IRM/KMI data"):
                try:
                    fetched = fetch_irm_data(int(nearest["code"]), irm_start, irm_end, IRM_LAYERS[granularity])
                except Exception as e:
                    fetched = None
                    st.error(f"Could not fetch data from IRM/KMI: {e}")

                if fetched is not None:
                    if fetched.empty:
                        st.warning("No data returned for that station and date range.")
                    else:
                        fetched["timestamp"] = pd.to_datetime(fetched["timestamp"], errors="coerce")
                        fetched = fetched.dropna(subset=["timestamp"])
                        col_name = f"Outside_{nearest['name']}"
                        irm_data = fetched[["timestamp", "temp_dry_shelter_avg"]].rename(
                            columns={"timestamp": "DateTime", "temp_dry_shelter_avg": col_name}
                        )
                        st.session_state["irm_data"] = {"col_name": col_name, "df": irm_data, "station": nearest["name"]}
                        st.success(f"Fetched {len(irm_data)} rows from {nearest['name']}.")

    if "irm_data" in st.session_state:
        st.caption(
            f"Ready to merge: outside temperature from {st.session_state['irm_data']['station']}. "
            "Source: Royal Meteorological Institute of Belgium (RMI/IRM/KMI), CC BY 4.0."
        )
elif "irm_data" in st.session_state:
    del st.session_state["irm_data"]

st.markdown("---")

merged_df = None
sources = []

if uploaded_files:
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name
        file_name_lower = file_name.lower()
        if file_name_lower.endswith('.csv'):
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file)
        elif file_name_lower.endswith('.txt'):
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, delimiter=",", encoding="latin1")
        elif file_name_lower.endswith(('.xlsx', '.xls')):
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
        else:
            st.warning(f"Unsupported file type: {uploaded_file.name}")
            continue

        # Try to find the date/time and temperature columns
        possible_time_cols = [col for col in df.columns if "time" in col.lower() or "date" in col.lower()]
        possible_temp_cols = [col for col in df.columns if "temp" in col.lower() or "celsius" in col.lower() or "°c" in col.lower()]
        if not possible_time_cols or not possible_temp_cols:
            st.warning(f"Could not find time or temperature columns in {file_name}")
            continue

        time_col = possible_time_cols[0]
        temp_col = possible_temp_cols[0]

        # Prepare the DataFrame for merging
        df = df[[time_col, temp_col]].copy()
        df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
        df = df.dropna(subset=[time_col])

        # Remove file extension from the column name
        col_name = file_name.rsplit('.', 1)[0]
        df = df.rename(columns={temp_col: col_name, time_col: "DateTime"})

        sources.append(df)

if use_irm and "irm_data" in st.session_state:
    sources.append(st.session_state["irm_data"]["df"].copy())

for df in sources:
    # Round to nearest 15 minutes if checkbox is checked
    if round_time:
        df["DateTime"] = df["DateTime"].dt.round('15min')
        # Rounding can make two readings land on the same slot (e.g. a source
        # sampled more often than every 15 min) - average those together so
        # DateTime stays unique before merging.
        df = df.groupby("DateTime", as_index=False).mean()

    if merged_df is None:
        merged_df = df
    else:
        merged_df = pd.merge(merged_df, df, on="DateTime", how="outer")

if merged_df is not None:
    merged_df = merged_df.sort_values("DateTime")

    if round_time:
        # Fill in every 15-minute slot for each day covered, even where no source has data
        day_start = merged_df["DateTime"].min().normalize()
        day_end = merged_df["DateTime"].max().normalize() + pd.Timedelta(days=1) - pd.Timedelta(minutes=15)
        full_range = pd.date_range(start=day_start, end=day_end, freq="15min")
        merged_df = merged_df.set_index("DateTime").reindex(full_range).rename_axis("DateTime").reset_index()
    else:
        merged_df.reset_index(drop=True, inplace=True)

    # Output as XLSX
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        merged_df.to_excel(writer, index=False, sheet_name='MergedData')
    output.seek(0)

    st.download_button(
        label="Download Merged Data as XLSX",
        data=output,
        file_name="Merged_Temperature_Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
