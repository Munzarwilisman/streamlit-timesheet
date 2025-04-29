import streamlit as st
import pandas as pd
import re
import os
import tempfile

# Konfigurasi halaman Streamlit
st.set_page_config(page_title="Manajemen Data Timesheet", layout="wide")

# Judul Aplikasi
st.title("Manajemen Data Timesheet")

# Nama File
filename = st.text_input("Nama file .xlsx", value="timesheet_190.xlsx")
if not filename.endswith(".xlsx"):
    filename += ".xlsx"

# Fungsi Parsing Teks
def process_text_per_jalur(text, tanggal, jalur):
    lines = text.strip().split('\n')
    data_list = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match_range = re.match(r'(\d{2}\.\d{2})-(\d{2}\.\d{2}) (.+)', line)
        if match_range:
            try:
                jam_mulai = pd.to_datetime(match_range[1], format='%H.%M').strftime('%H:%M')
                jam_akhir = pd.to_datetime(match_range[2], format='%H.%M').strftime('%H:%M')
                data_list.append([tanggal, jalur, jam_mulai, jam_akhir, match_range[3]])
            except ValueError:
                continue
            continue

        match_dash_only = re.match(r'(\d{2}\.\d{2})- (.+)', line)
        if match_dash_only:
            try:
                jam = pd.to_datetime(match_dash_only[1], format='%H.%M').strftime('%H:%M')
                data_list.append([tanggal, jalur, jam, jam, match_dash_only[2]])
            except ValueError:
                continue
            continue

        match_single = re.match(r'(\d{2}\.\d{2}) (.+)', line)
        if match_single:
            try:
                jam = pd.to_datetime(match_single[1], format='%H.%M').strftime('%H:%M')
                data_list.append([tanggal, jalur, jam, jam, match_single[2]])
            except ValueError:
                continue
            continue

    return pd.DataFrame(data_list, columns=["Tanggal", "Jalur", "Jam Mulai", "Jam Akhir", "Keterangan"])

# Load data
if os.path.exists(filename):
    df = pd.read_excel(filename)
else:
    df = pd.DataFrame(columns=["Tanggal", "Jalur", "Jam Mulai", "Jam Akhir", "Keterangan"])

# Input Section
st.subheader("Input Data Baru")

tanggal = st.text_input("Tanggal (Contoh: 03 April 2025)")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Jalur A**")
    text_a = st.text_area("Input Jalur A", height=150, key="text_a")

with col2:
    st.markdown("**Jalur B**")
    text_b = st.text_area("Input Jalur B", height=150, key="text_b")

with col3:
    st.markdown("**Mode Trucking**")
    text_trucking = st.text_area("Input Trucking", height=150, key="text_trucking")

# Tombol aksi
col4, col5, col6 = st.columns(3)

with col4:
    if st.button("Tambah Data"):
        new_data = []
        if tanggal:
            if text_a:
                new_data.append(process_text_per_jalur(text_a, tanggal, 'A'))
            if text_b:
                new_data.append(process_text_per_jalur(text_b, tanggal, 'B'))
            if text_trucking:
                new_data.append(process_text_per_jalur(text_trucking, tanggal, 'Trucking'))

            if new_data:
                df = pd.concat([df] + new_data, ignore_index=True)
                df.to_excel(filename, index=False)
                st.success("Data berhasil ditambahkan!")

with col5:
    if st.button("Hapus Semua Data"):
        df = pd.DataFrame(columns=["Tanggal", "Jalur", "Jam Mulai", "Jam Akhir", "Keterangan"])
        df.to_excel(filename, index=False)
        st.success("Semua data berhasil dihapus!")

with col6:
    tanggal_options = df['Tanggal'].unique().tolist()
    delete_date = st.selectbox("Pilih Tanggal untuk Dihapus", [""] + tanggal_options)

    if st.button("Hapus Berdasarkan Tanggal"):
        if delete_date:
            df = df[df['Tanggal'] != delete_date]
            df.to_excel(filename, index=False)
            st.success(f"Data tanggal {delete_date} berhasil dihapus!")

st.subheader("Tabel Data Timesheet")
st.dataframe(df, use_container_width=True)

# Download Section
st.subheader("Download Data")

col7, col8 = st.columns(2)

with col7:
    if st.download_button("Download Semua Data", data=open(filename, "rb"), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        st.success("File berhasil didownload.")

with col8:
    if st.button("Download Data Tanpa 'Bongkar'"):
        if not df.empty:
            filtered_df = df[~df['Keterangan'].str.contains('bongkar', case=False, na=False)]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            filtered_df.to_excel(temp_file.name, index=False)

            with open(temp_file.name, "rb") as f:
                st.download_button("Klik untuk download", data=f, file_name="filtered_timesheet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
