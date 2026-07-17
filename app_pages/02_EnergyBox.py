# -*- coding: utf-8 -*-
"""
Created on Tue Jun  3 14:46:13 2025

@author: BrunoFantoli
"""
import streamlit as st
import pandas as pd
import re
import io

st.title("Energy Box Data Cleaning")
st.write("This page is designed to help you manage and analyze data from the Energy Box.")
st.write("You can upload a CSV file downloaded from the Energy Box and download an Excel file to be used for the Electricity analysis template.")

# Load the CSV
used_in_excel = st.checkbox("The data will be used in excel")

uploaded_file = st.file_uploader("Choose a file")

if uploaded_file is not None:
    # Can be used wherever a "file-like" object is accepted:
    dataframe = pd.read_csv(uploaded_file,skiprows=[0])
    df = dataframe

    # Clean the DataFrame
    df_cleaned = df.drop(columns=['No.'])
    df_cleaned = df_cleaned.iloc[:, :-1]
    df_cleaned = df_cleaned.rename(columns={"Time Stamp": "date"})
    # Remove '(float)' from all column names
    df_cleaned.columns = df_cleaned.columns.str.replace('(float)', '', regex=False).str.strip()
    
    file_name = st.text_input("Enter the base name for the files (optionnal)")
    if not file_name:
        file_name = "EnergyBox"

    # Download Excel file with all columns (selected and unselected)
    if used_in_excel:
        st.markdown("#### Download file for Excel")
        st.markdown("###### Specify Occupancy Profile for a Typical Week")
        week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        occupancy_profiles = []

        add_profile = True
        profile_idx = 0
        used_days = set()
        while add_profile:
            available_days = [d for d in week_days if d not in used_days]
            if not available_days:
                break
            selected_days = st.multiselect(
                f"Select days for occupancy profile #{profile_idx+1}",
                options=available_days,
                key=f"occ_days_{profile_idx}"
            )
            if selected_days:
                open_time = st.time_input(
                    f"Opening time for {', '.join(selected_days)}",
                    value=pd.to_datetime("08:00").time(),
                    key=f"open_{profile_idx}"
                )
                close_time = st.time_input(
                    f"Closing time for {', '.join(selected_days)}",
                    value=pd.to_datetime("18:00").time(),
                    key=f"close_{profile_idx}"
                )
                occupancy_profiles.append({
                    "days": selected_days,
                    "open": open_time,
                    "close": close_time
                })
                used_days.update(selected_days)
            add_profile = st.checkbox(
                "Add another occupancy profile",
                key=f"add_profile_{profile_idx}"
            )
            if add_profile:
                profile_idx += 1

        # --- Compute 'occupied' column for Excel export ---
        def is_occupied(row, profiles):
            weekday = row['date'].strftime("%A")
            time = row['date'].time()
            for prof in profiles:
                if weekday in prof['days']:
                    if prof['open'] <= time <= prof['close']:
                        return True
            return False

        st.markdown("###### Specify On-Peak Hours")
        if st.checkbox("The peak-time is different from 7:00 to 22:00"):
            on_peak_start = st.time_input("On-peak start time", value=pd.to_datetime("07:00").time(), key="on_peak_start")
            on_peak_end = st.time_input("On-peak end time", value=pd.to_datetime("22:00").time(), key="on_peak_end")
        else:
            on_peak_start = pd.to_datetime("07:00").time()
            on_peak_end = pd.to_datetime("22:00").time()

        weekends_on_peak = st.checkbox("Weekends are considered on-peak", key="weekends_on_peak", value=False)

        excel_buffer = io.BytesIO()
        # Use the full df (not just selected columns)
        df_excel = df_cleaned.copy()
        df_excel = df_excel.rename(columns={"Time Stamp": "date"})
        df_excel.columns = df_excel.columns.str.replace('(float)', '', regex=False).str.strip()
        df_excel['date'] = pd.to_datetime(df_excel['date'], errors='coerce')
        df_excel['is_weekend'] = df_excel['date'].dt.weekday >= 5

        if weekends_on_peak:
            df_excel['on_peak'] = df_excel['date'].dt.time.between(on_peak_start, on_peak_end) # type: ignore
        else:
            df_excel['on_peak'] = (~df_excel['is_weekend']) & df_excel['date'].dt.time.between(on_peak_start, on_peak_end) # type: ignore

        df_excel['occupied'] = df_excel.apply(lambda row: is_occupied(row, occupancy_profiles), axis=1)
        # Insert 'occupied' after 'date'
        cols = list(df_excel.columns)
        if 'occupied' in cols:
            cols.insert(cols.index('date') + 1, cols.pop(cols.index('occupied')))
            df_excel = df_excel[cols]

        # --- Normalize columns that contain units in their cells and map them to desired names ---
        import math

        def extract_numeric(val):
            """Extract first numeric token from a cell like '235.115 V' or '-1,281 kW' and return float."""
            if pd.isna(val):
                return val
            # leave pure strings like 'L' (load type) untouched
            s = str(val).strip()
            # look for a number pattern (support comma or dot decimals)
            m = re.search(r'[-+]?\d+[\d\.,]*', s)
            if not m:
                return s
            num = m.group(0).replace(',', '.')  # normalize decimal comma to dot
            try:
                return float(num)
            except Exception:
                return s

        # desired output order (keep as before)
        desired_order = [
            "date", "occupied", "on_peak", "Frequency  [Hz]", "I A  [A]", "I B  [A]", "I C  [A]", "I N  [A]", "I Average  [A]",
            "Pwr Factor A", "Pwr Factor B", "Pwr Factor C", "Pwr Factor Total",
            "VA A  [kVA]", "VA B  [kVA]", "VA C  [kVA]", "VA Total  [kVA]",
            "Volts AN  [V]", "Volts BN  [V]", "Volts CN  [V]", "Volts LN Average  [V]",
            "Volts AB  [V]", "Volts BC  [V]", "Volts CA  [V]", "Volts LL Average  [V]",
            "Watt A  [kW]", "Watt B  [kW]", "Watt C  [kW]", "Watt Total  [kW]"
        ]

        # Build a mapping from a normalized name (without unit brackets) to actual df column
        def normalize_name(name):
            # remove bracketed unit part and collapse spaces + lowercase
            name_no_unit = re.sub(r"\s*\[.*?\]", "", name).strip()
            name_no_unit = re.sub(r"\s+", " ", name_no_unit)
            return name_no_unit.lower()

        existing_map = {normalize_name(c): c for c in df_excel.columns}

        # For each desired column, try to fill from matching existing column (ignoring unit suffix),
        # and convert values to numeric when appropriate.
        for desired in desired_order:
            norm = normalize_name(desired)
            if desired in df_excel.columns:
                # exact match exists, try to convert values
                if df_excel[desired].dtype == object:
                    df_excel[desired] = df_excel[desired].apply(extract_numeric)
            elif norm in existing_map:
                src_col = existing_map[norm]
                # create the desired-named column from source column
                # convert numeric-like strings to numbers
                new_series = df_excel[src_col].apply(extract_numeric)
                df_excel[desired] = new_series
            else:
                # column missing: create empty column
                df_excel[desired] = ""

        final_cols = desired_order  # Only use desired_order, no extras

        # Reorder the DataFrame to match the desired order
        df_excel = df_excel[final_cols]

        df_excel.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        st.download_button(
            label="Download file for Excel",
            data=excel_buffer,
            file_name=f"{file_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel"
        )

