import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO
import plotly.express as px
from datetime import datetime, timedelta

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Timesheet Dashboard", layout="wide")

# ---------- THEME ----------
st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', sans-serif; }
    h1,h2,h3,h4 { color: #60a5fa; }
    .stButton>button {
        border-radius: 8px; background-color: #2563eb; color: #fff; font-weight: 600;
        border: none; padding: 0.5em 1.2em; box-shadow: 0px 2px 6px rgba(0,0,0,0.4);
    }
    .stButton>button:hover { background-color: #1d4ed8; transform: scale(1.02); }
    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; background-color: #f1f5f9 !important; color: #1e293b !important; }
</style>
""", unsafe_allow_html=True)

# ---------------- TITLE ----------------
st.title("📘 Timesheet Dashboard PLTU")
st.caption("Konversi laporan WA → timesheet (deteksi tanggal, shift, jalur A/B/Trucking, durasi, Pareto)")

# ---------------- STATE / COLUMNS ----------------
columns = ["Tanggal", "Shift", "Jalur", "Jam Mulai", "Jam Akhir", "Keterangan", "Durasi (Jam)"]
if 'data' not in st.session_state:
    st.session_state['data'] = pd.DataFrame(columns=columns)

# ---------------- FILE NAME INPUT ----------------
filename = st.text_input('🗂️ Nama file .xlsx', value='timesheet_190.xlsx')
if not filename.endswith('.xlsx'):
    filename += '.xlsx'

# ---------------- DURASI ----------------
def hitung_durasi(jam_mulai, jam_akhir):
    try:
        jm = str(jam_mulai).replace('.', ':')
        ja = str(jam_akhir).replace('.', ':')
        t1 = datetime.strptime(jm, "%H:%M")
        t2 = datetime.strptime(ja, "%H:%M")
        if t2 < t1:
            t2 += timedelta(days=1)
        return round((t2 - t1).total_seconds() / 3600, 2)
    except Exception:
        return 0.0

# ---------------- LOAD EXISTING ----------------
if os.path.exists(filename):
    try:
        df = pd.read_excel(filename)
        # ensure columns present (incl. Shift)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        # recalc Durasi defensively
        df["Durasi (Jam)"] = df.apply(lambda r: hitung_durasi(r["Jam Mulai"], r["Jam Akhir"]), axis=1)
        st.session_state['data'] = df
    except Exception:
        # jika file korup / tidak sesuai, abaikan
        pass

# ---------------- PARSER (PERBAIKAN SHIFT) ----------------
def parse_laporan_multijalur(text):
    """
    Parse pasted WA report:
      - Detect date lines like '05 oktober 2025' or '05-10-2025'
      - Detect Shift header ONLY when it is a header line (anchored)
      - Detect Jalur headers: 'Jalur A', 'Jalur B', 'Trucking' (anchored)
      - Parse activities: 'HH.MM-HH.MM Description' or 'HH.MM Description'
    Returns dataframe with columns = columns
    """
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    tanggal = None
    shift = None
    data_list = []
    current_jalur = None

    bulan_map = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
    }

    # 1) detect date & shift from header lines (scan once)
    for l in lines:
        l_strip = l.strip()
        l_lower = l_strip.lower()

        # date with month name (Indonesia) e.g. "05 oktober 2025"
        m_name = re.match(r'^\s*(\d{1,2})\s+([a-z]+)\s+(\d{4})\s*$', l_lower)
        if m_name:
            d, bulan_str, y = m_name.groups()
            if bulan_str in bulan_map:
                try:
                    tanggal = datetime(int(y), bulan_map[bulan_str], int(d)).strftime("%d %B %Y")
                except:
                    tanggal = f"{d} {bulan_str} {y}"
            continue

        # date numeric e.g. "05-10-2025" or "05/10/2025"
        m_num = re.match(r'^\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*$', l_strip)
        if m_num:
            d, m, y = m_num.groups()
            try:
                tanggal = datetime(int(y), int(m), int(d)).strftime("%d %B %Y")
            except:
                tanggal = f"{d}-{m}-{y}"
            continue

        # SHIFT: only match if line starts with "Shift" (anchored), e.g. "Shift B" or "Shift: B (pagi)"
        m_shift = re.match(r'^\s*Shift\b[:\s\-]*(.+)$', l_strip, re.IGNORECASE)
        if m_shift:
            shift_val = m_shift.group(1).strip()
            # normalize small variations (optional)
            shift = shift_val
            continue

    if not tanggal:
        tanggal = "Tidak Diketahui"
    if not shift:
        shift = "Tidak Diketahui"

    # 2) parse activities; only change current_jalur when header line appears anchored
    for l in lines:
        l_strip = l.strip()

        # Jalur headers anchored:
        m_jalur_a = re.match(r'^\s*Jalur\s*A\b.*$', l_strip, re.IGNORECASE)
        m_jalur_b = re.match(r'^\s*Jalur\s*B\b.*$', l_strip, re.IGNORECASE)
        m_truck = re.match(r'^\s*(Mode\s+)?Trucking\b.*$', l_strip, re.IGNORECASE)

        if m_jalur_a:
            current_jalur = "A"
            continue
        if m_jalur_b:
            current_jalur = "B"
            continue
        if m_truck:
            current_jalur = "Trucking"
            continue

        if not current_jalur:
            # skip lines until a jalur header found
            continue

        # Match HH.MM-HH.MM Description
        m_range = re.match(r'^\s*(\d{1,2}[\.:]\d{2})\s*-\s*(\d{1,2}[\.:]\d{2})\s+(.+)$', l_strip)
        if m_range:
            jm, ja, ket = m_range.groups()
            jm = jm.replace('.', ':'); ja = ja.replace('.', ':')
            dur = hitung_durasi(jm, ja)
            data_list.append([tanggal, shift, current_jalur, jm, ja, ket.strip(), dur])
            continue

        # Match HH.MM Description (single time)
        m_single = re.match(r'^\s*(\d{1,2}[\.:]\d{2})\s+(.+)$', l_strip)
        if m_single:
            jm, ket = m_single.groups()
            jm = jm.replace('.', ':')
            data_list.append([tanggal, shift, current_jalur, jm, jm, ket.strip(), 0.0])
            continue

        # otherwise ignore (notes etc.)

    if data_list:
        return pd.DataFrame(data_list, columns=columns)
    else:
        return pd.DataFrame(columns=columns)

# ---------------- UI: PASTE LAPORAN ----------------
st.markdown("### 📋 Paste Laporan Harian (satu kali untuk semua jalur)")
laporan_text = st.text_area(
    "Tempel teks laporan (misal: tanggal lalu 'Shift B' lalu 'Jalur A' ...):",
    height=320,
    placeholder="05 oktober 2025\nShift B\n\nJalur A\n16.00-16.15 Patrol chek jalur bongkar\n..."
)

if st.button("🧩 Proses Laporan Otomatis"):
    if not laporan_text.strip():
        st.warning("⚠️ Tempel laporan terlebih dahulu.")
    else:
        df_new = parse_laporan_multijalur(laporan_text)
        if not df_new.empty:
            # append and recalc durations to be safe
            st.session_state['data'] = pd.concat([st.session_state['data'], df_new], ignore_index=True)
            st.session_state['data']["Durasi (Jam)"] = st.session_state['data'].apply(
                lambda r: hitung_durasi(r["Jam Mulai"], r["Jam Akhir"]), axis=1
            )
            st.session_state['data'].to_excel(filename, index=False)
            st.success(f"✅ Berhasil menambahkan {len(df_new)} baris. Shift: {df_new['Shift'].iloc[0]}")
        else:
            st.error("❌ Tidak menemukan aktivitas valid di laporan.")

# ---------------- HAPUS DATA ----------------
st.markdown("---")
c1, c2 = st.columns(2)
with c1:
    if st.button("🧹 Hapus Semua Data"):
        st.session_state['data'] = pd.DataFrame(columns=columns)
        st.session_state['data'].to_excel(filename, index=False)
        st.warning("⚠️ Semua data dihapus.")
with c2:
    if not st.session_state['data'].empty:
        tanggal_opsi = st.session_state['data']['Tanggal'].dropna().unique().tolist()
        pilih = st.selectbox("🗓️ Pilih tanggal untuk hapus", options=[None] + tanggal_opsi)
        if st.button("❌ Hapus Berdasarkan Tanggal") and pilih:
            st.session_state['data'] = st.session_state['data'][st.session_state['data']['Tanggal'] != pilih]
            st.session_state['data'].to_excel(filename, index=False)
            st.warning(f"🗓️ Data tanggal {pilih} dihapus.")

# ---------------- TABEL ----------------
st.markdown("---")
st.subheader("📊 Rekap Timesheet")
if not st.session_state['data'].empty:
    df_display = st.session_state['data'].copy()
    # ensure Durasi up-to-date
    df_display["Durasi (Jam)"] = df_display.apply(lambda r: hitung_durasi(r["Jam Mulai"], r["Jam Akhir"]), axis=1)

    def highlight_bongkar(row):
        return ['background-color: #ffe4e6' if 'bongkar' in str(row.Keterangan).lower() else '' for _ in row]

    st.dataframe(df_display.style.apply(highlight_bongkar, axis=1), use_container_width=True, hide_index=True)
else:
    st.info("Belum ada data.")

# ---------------- PARETO ----------------
if not st.session_state['data'].empty:
    st.markdown("---")
    st.subheader("📈 Pareto Durasi Aktivitas (tanpa 'bongkar')")
    df_nb = st.session_state['data'][~st.session_state['data']['Keterangan'].astype(str).str.contains('bongkar', case=False, na=False)]

    if not df_nb.empty:
        pareto = df_nb.groupby("Keterangan", as_index=False)["Durasi (Jam)"].sum().sort_values(by="Durasi (Jam)", ascending=False)
        pareto["Kumulatif (%)"] = 100 * pareto["Durasi (Jam)"].cumsum() / pareto["Durasi (Jam)"].sum()

        fig = px.bar(pareto, x="Keterangan", y="Durasi (Jam)", text="Durasi (Jam)",
                     title="Pareto Aktivitas Tanpa Bongkar", color="Durasi (Jam)", color_continuous_scale="Blues")
        fig.update_traces(texttemplate='%{text:.2f} jam', textposition='outside')
        fig.update_layout(plot_bgcolor='#0f172a', paper_bgcolor='#0f172a', font_color='#f8fafc', title_x=0.5)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 📊 Pareto per Jalur")
        for j in df_nb["Jalur"].unique():
            sub = df_nb[df_nb["Jalur"] == j]
            p = sub.groupby("Keterangan", as_index=False)["Durasi (Jam)"].sum().sort_values(by="Durasi (Jam)", ascending=False)
            fig_j = px.bar(p, x="Keterangan", y="Durasi (Jam)", text="Durasi (Jam)",
                           title=f"Pareto Jalur {j}", color="Durasi (Jam)", color_continuous_scale="Blues")
            fig_j.update_traces(texttemplate='%{text:.2f} jam', textposition='outside')
            fig_j.update_layout(plot_bgcolor='#0f172a', paper_bgcolor='#0f172a', font_color='#f8fafc', title_x=0.5)
            st.plotly_chart(fig_j, use_container_width=True)
    else:
        st.info("Tidak ada data numerik (tanpa 'bongkar') untuk Pareto.")

# ---------------- DOWNLOAD ----------------
st.markdown("---")
d1, d2 = st.columns(2)
with d1:
    buf_all = BytesIO()
    st.session_state['data'].to_excel(buf_all, index=False)
    buf_all.seek(0)
    st.download_button("💾 Download Semua Data", data=buf_all, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with d2:
    buf_f = BytesIO()
    df_filtered = st.session_state['data'][~st.session_state['data']['Keterangan'].astype(str).str.contains('bongkar', case=False, na=False)]
    df_filtered.to_excel(buf_f, index=False)
    buf_f.seek(0)
    st.download_button("📁 Download Tanpa 'Bongkar'", data=buf_f, file_name=f"filtered_{filename}", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
