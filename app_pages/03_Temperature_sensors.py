# -*- coding: utf-8 -*-
"""
Created on Tue Jun  3 14:46:13 2025

@author: BrunoFantoli
"""
import streamlit as st
import pandas as pd
import io


st.title("Temperature Sensors Data Cleaning")
st.write("This page is designed to help you clean and prepare your temperature sensor data for an analysis in Excel.")

uploaded_files = st.file_uploader("Choose one or more files", type=["csv", "txt", "xlsx", "xls"], accept_multiple_files=True)
round_time = st.checkbox("Round timestamps to nearest 15 minutes before merging", value=True)

merged_df = None

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

        # Round to nearest 15 minutes if checkbox is checked
        if round_time:
            df[time_col] = df[time_col].dt.round('15min')

        # Remove file extension from the column name
        col_name = file_name.rsplit('.', 1)[0]
        df = df.rename(columns={temp_col: col_name, time_col: "DateTime"})

        if merged_df is None:
            merged_df = df
        else:
            merged_df = pd.merge(merged_df, df, on="DateTime", how="outer")

    if merged_df is not None:
        merged_df = merged_df.sort_values("DateTime")
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
