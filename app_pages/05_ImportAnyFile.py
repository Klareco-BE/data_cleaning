import streamlit as st
import pandas as pd
import io

st.title("General File Import")
st.write("This page allows you to upload any data file (CSV, Excel) and export selected variables into a single Excel file for further analysis.")
st.write("Please ensure your data includes a date/time column and the variables you wish to export in different columns.")

uploaded_file = st.file_uploader("Upload your data file (CSV, Excel, etc.)", type=["csv", "xlsx", "xls"])

df = None
if uploaded_file:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(uploaded_file)
    else:
        st.error("Unsupported file type.")

if df is not None:
    columns = list(df.columns)
    date_col = st.selectbox("Select the date/time column:", columns, key="date_col")
    variable_columns = st.multiselect(
        "Select variables to export:",
        [col for col in columns if col != date_col]
    )
    if variable_columns:
        file_name = st.text_input("Optional file name", key="fname")

        out_df = pd.DataFrame({"date": pd.to_datetime(df[date_col], errors='coerce')})
        for var in variable_columns:
            out_df[var] = df[var]

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            out_df.to_excel(writer, index=False, sheet_name='Data')
        excel_buffer.seek(0)

        out_file_name = f"{file_name if file_name else 'ExportedData'}.xlsx"
        st.download_button(
            label="Download Excel file",
            data=excel_buffer,
            file_name=out_file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel"
        )

else:
    st.info("Please upload a file to begin.")
