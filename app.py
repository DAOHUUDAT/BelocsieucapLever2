import random
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf


# -------------------------------
# DỮ LIỆU & TÍNH TOÁN CÓ CACHE
# -------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_ticker_data(ticker: str) -> pd.DataFrame:
    """Hàm máy bơm: hút dữ liệu giá của 1 mã từ Yahoo Finance."""
    data = yf.download(f"{ticker}.VN", period="150d", progress=False)
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data


@st.cache_data(ttl=600, show_spinner=False)
def load_all_ticker_data(tickers: list[str]) -> pd.DataFrame:
    """Tải gộp nhiều mã một lần cho Radar (giảm 20 lần request)."""
    tickers_with_suffix = [f"{t}.VN" for t in tickers]
    data = yf.download(tickers_with_suffix, period="150d", progress=False, group_by="ticker")
    return data if not data.empty else pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def load_vni_data() -> pd.DataFrame:
    """Tải VN-Index với cache để tránh gọi lại mỗi rerun."""
    data = yf.download("^VNI", period="150d", progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data


def compute_rsi_pro(data: pd.Series, window: int = 14) -> pd.Series:
    """Tính RSI (vector hóa)."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


@st.cache_data(ttl=3600, show_spinner=False)
def load_vietstock_data() -> pd.DataFrame:
    """Đọc 3 file Excel trên GitHub, loại cột trùng để tránh lỗi truy vấn."""
    urls = [
        "https://github.com/DAOHUUDAT/Be-Loc-Sieu-Cap/raw/refs/heads/main/data/HOSE.xlsx",
        "https://github.com/DAOHUUDAT/Be-Loc-Sieu-Cap/raw/refs/heads/main/data/HNX.xlsx",
        "https://github.com/DAOHUUDAT/Be-Loc-Sieu-Cap/raw/refs/heads/main/data/UPCOM.xlsx",
    ]
    dfs = []
    for url in urls:
        try:
            df = pd.read_excel(url)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()]
            dfs.append(df)
        except Exception:
            continue
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


# Kích hoạt dữ liệu nện
vietstock_db = load_vietstock_data()

# -------------------------------
# 1. CẤU HÌNH HỆ THỐNG GIAO DIỆN
# -------------------------------
st.set_page_config(page_title="HÃY CHỌN CÁ ĐÚNG v6.3.15", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: bold; color: #007bff; }
    section[data-testid="stSidebar"] { width: 310px !important; }
    .stTable { border-radius: 12px; overflow: hidden; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { border-radius: 5px; padding: 10px; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "history_log" not in st.session_state:
    st.session_state["history_log"] = []
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "FPT"

# --- TỪ ĐIỂN VIỆT HÓA BCTC (để dành dùng sau) ---
DICTIONARY_BCTC = {
    "Total Revenue": "Tổng Doanh thu",
    "Operating Revenue": "Doanh thu hoạt động",
    "Cost Of Revenue": "Giá vốn hàng bán",
    "Gross Profit": "Lợi nhuận gộp",
    "Operating Expense": "Chi phí hoạt động",
    "Selling General And Administration": "Chi phí bán hàng & QLDN",
    "Selling And Marketing Expense": "Chi phí bán hàng & Marketing",
    "General And Administrative Expense": "Chi phí quản lý doanh nghiệp",
    "Rent Expense Supplemental": "Chi phí thuê bổ sung",
    "Rent And Landing Fees": "Chi phí thuê & phí bãi",
    "Depreciation And Amortization In Income Statement": "Khấu hao trong BCKQKD",
    "Depreciation Income Statement": "Khấu hao (BCKQKD)",
    "Operating Income": "Lợi nhuận từ HĐKD",
    "Total Operating Income As Reported": "Tổng LN hoạt động (Báo cáo)",
    "Total Expenses": "Tổng chi phí",
    "Other Non Operating Income Expenses": "Thu nhập/Chi phí phi hoạt động khác",
    "Special Income Charges": "Chi phí thu nhập đặc biệt",
    "Other Special Charges": "Chi phí đặc biệt khác",
    "Net Interest Income": "Thu nhập lãi thuần",
    "Interest Income": "Thu nhập lãi vay",
    "Interest Expense": "Chi phí lãi vay",
    "Net Non Operating Interest Income Expense": "Thu nhập lãi phi hoạt động thuần",
    "Total Other Finance Cost": "Tổng chi phí tài chính khác",
    "Pretax Income": "Lợi nhuận trước thuế",
    "Tax Provision": "Dự phòng thuế",
    "Net Income": "Lợi nhuận ròng",
    "Net Income Common Stockholders": "LN ròng dành cho CĐ phổ thông",
    "Normalized Income": "Lợi nhuận điều chỉnh (Normalized)",
    "Basic EPS": "EPS cơ bản",
    "Diluted EPS": "EPS pha loãng",
}

# -------------------------------
# 2. SIDEBAR: TRI KỶ & CẨM NANG
# -------------------------------
with st.sidebar:
    img_url = "https://github.com/DAOHUUDAT/Be-Loc-Sieu-Cap/blob/main/anh-tri-ky.jpg?raw=true"
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center;">
            <img src="{img_url}" style="width: 100%; border-radius: 15px; border: 2px solid #007bff; margin-bottom: 20px;"
                 onerror="this.onerror=null; this.src='https://cdn-icons-png.flaticon.com/512/1144/1144760.png';">
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.header("🎮 ĐÀI CHỈ HUY")
    t_input = st.text_input("🔍 SOI MÃ CÁ", "VNI").upper()
    st.divider()

    st.header("📓 CẨM NANG")
    with st.expander("📖 Giải mã thông số", expanded=True):
        st.markdown("### 🚀 Hệ sinh thái Cá:")
        st.write("- **SIÊU CÁ:** hội tụ 3 yếu tố: Giá > MA20 + Vol đột biến (>120%) + Sức mạnh RS khỏe hơn VN-Index.")
        st.write("- **Cá Lớn 🐋:** Xu hướng tăng bền vững (Giá nằm trên cả MA20 và MA50).")
        st.write("- **Cá Đang Lớn 🐡:** Giai đoạn chuyển mình, vừa chớm vượt MA20.")
        st.write("- **Cá Nhỏ 🐟:** Dưới trung bình, dòng tiền yếu - Tạm bỏ qua.")
        st.markdown("### 🌩️ Trạng thái dòng nước:")
        st.write("- **💪 Khỏe:** Sức mạnh tương đối (RS) dương - cá đang bơi khỏe hơn thị trường chung.")
        st.write("- **🌊 Sóng:** Vol > 150% trung bình 20 phiên - dấu hiệu 'cá mập' đang đẩy giá.")
        st.write("- **🌩️ Nhiệt độ (RSI):** Nóng (>70) dễ điều chỉnh, Lạnh (<30) quá bán.")
        st.divider()
        st.markdown(f"### 💎 Mổ xẻ chi tiết: {t_input}")
        st.write("- **🧭 Niềm tin (%):** đo sự đồng thuận giữa tăng trưởng doanh thu và vị thế giá kỹ thuật.")
        st.write("- **💰 Định giá 3 kịch bản:** Thận trọng / Cơ sở / Phi thường.")
        st.write("- **📈 Tuyệt kỹ Ichimoku:** Mây, Tenkan, Kijun giữ nguyên ý nghĩa.")
        st.write("- **🍱 Chiến thuật 'Thức ăn':** khoảng cách về MA20, kiểm tra % dư địa.")
    st.divider()
    QUOTES = [
        "“Trong đầu tư, thứ đắt đỏ nhất là sự thiếu kiên nhẫn.”",
        "“Hãy mua con cá khỏe nhất trong dòng nước yếu nhất.”",
        "“Đừng cố bắt cá khi đại dương đang có bão lớn.”",
        "“Siêu cá không xuất hiện mỗi ngày, hãy kiên nhẫn đợi điểm nổ.”",
        "“Kỷ luật là thứ tách biệt ngư dân chuyên nghiệp và kẻ đi dạo.”",
        "“Giá là thứ bạn trả, giá trị là thứ con cá mang lại.”",
    ]
    st.info(f"💡 {random.choice(QUOTES)}")
    st.divider()
    st.caption(
        """
        ⚠️ **MIỄN TRỪ TRÁCH NHIỆM:** Mọi dữ liệu & phân tích chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.
        Đầu tư luôn tiềm ẩn rủi ro. Hãy tự tìm hiểu và quản trị rủi ro cá nhân.
        """
    )

st.title("🚀 Bể Lọc v6.3.15: HÃY CHỌN CÁ ĐÚNG")

# ------------------------------------
# 3. TRẠM QUAN TRẮC ĐẠI DƯƠNG (VN-INDEX)
# ------------------------------------
inf_factor = 1.0
v_c = 1200.0
vni = load_vni_data()
if not vni.empty:
    try:
        v_c = float(vni["Close"].iloc[-1])
        vh26 = vni["High"].rolling(26).max()
        vl26 = vni["Low"].rolling(26).min()
        vh9 = vni["High"].rolling(9).max()
        vl9 = vni["Low"].rolling(9).min()
        vsa = (((vh9 + vl9) / 2 + (vh26 + vl26) / 2) / 2).shift(26).iloc[-1]
        inf_factor = 1.15 if v_c > vsa else 0.85
        st.info(
            f"🌊 Đại Dương: {'🟢 THẢ LƯỚI (Sóng Thuận)' if v_c > vsa else '🔴 ĐÁNH KẸO (Sóng Nghịch)'} | Co giãn: {inf_factor}x"
        )
    except Exception:
        pass

# -------------------------------
# 4. HỆ THỐNG TABS
# -------------------------------
tab_radar, tab_analysis, tab_bctc, tab_history = st.tabs(
    ["🎯 RADAR ELITE", "💎 CHI TIẾT SIÊU CÁ", "📊 MỔ XẺ BCTC", "📓 SỔ VÀNG"]
)

with tab_radar:
    st.subheader("🤖 Top 20 SIÊU CÁ (Hệ thống Radar)")
    elite_20 = ["DGC", "MWG", "FPT", "TCB", "SSI", "HPG", "GVR", "CTR", "DBC", "VNM", "STB", "MBB", "ACB", "KBC", "VGC", "PVS", "PVD", "ANV", "VHC", "REE"]
    radar_list = []

    all_data = load_all_ticker_data(elite_20)
    with st.spinner("Đang quét tín hiệu từ đại dương..."):
        for tk in elite_20:
            ticker_key = f"{tk}.VN"
            d = pd.DataFrame()
            if not all_data.empty and isinstance(all_data.columns, pd.MultiIndex) and ticker_key in all_data.columns.get_level_values(0):
                d = all_data.xs(ticker_key, axis=1, level=0).dropna()
            if d.empty:
                d = load_ticker_data(tk)
            if d.empty:
                continue

            p_c = d["Close"].iloc[-1]
            v_now = d["Volume"].iloc[-1]
            v_avg = d["Volume"].rolling(20).mean().iloc[-1]
            ma20 = d["Close"].rolling(20).mean().iloc[-1]
            ma50 = d["Close"].rolling(50).mean().iloc[-1]

            stock_perf = (p_c / d["Close"].iloc[-20]) - 1 if len(d) >= 20 else 0
            vni_perf = (v_c / vni["Close"].iloc[-20]) - 1 if not vni.empty and len(vni) >= 20 else 0
            is_stronger = stock_perf > vni_perf

            curr_rsi = compute_rsi_pro(d["Close"]).iloc[-1]
            temp = "🔥 Nóng" if curr_rsi > 70 else "❄️ Lạnh" if curr_rsi < 30 else "🌤️ Êm"

            if p_c > ma20 and v_now > v_avg * 1.5 and is_stronger:
                loai_ca, priority = "🚀 SIÊU CÁ", 1
            elif p_c > ma20 and p_c > ma50:
                loai_ca, priority = "Cá Lớn 🐋", 2
            elif p_c > ma20:
                loai_ca, priority = "Cá Đang Lớn 🐡", 3
            else:
                loai_ca, priority = "Cá Nhỏ 🐟", 4

            radar_list.append(
                {
                    "Mã": tk,
                    "Giá": f"{p_c:,.0f}",
                    "Sóng": "🌊 Mạnh" if v_now > v_avg * 1.5 else "☕ Lặng",
                    "Nhiệt độ": temp,
                    "Đại Dương": "💪 Khỏe" if is_stronger else "🐌 Yếu",
                    "Loại": loai_ca,
                    "Thức ăn": f"{((ma20 / p_c) - 1) * 100:+.1f}%" if p_c < ma20 else "✅ Đang no",
                    "priority": priority,
                    "RS_Raw": stock_perf - vni_perf,
                }
            )

    df_radar = pd.DataFrame(radar_list).sort_values(by=["priority", "RS_Raw"], ascending=[True, False])
    selection = st.dataframe(
        df_radar.drop(columns=["priority", "RS_Raw"]),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
    )

    if selection and len(selection.selection.rows) > 0:
        selected_idx = selection.selection.rows[0]
        st.session_state.selected_ticker = df_radar.iloc[selected_idx]["Mã"]
        st.toast(f"🎯 Đã khóa mục tiêu: {st.session_state.selected_ticker}", icon="🚀")

with tab_analysis:
    target = st.session_state.selected_ticker
    t_input = st.text_input("Nhập mã cá muốn mổ xẻ:", value=target, key="ticker_input_analysis").upper()

    if t_input != st.session_state.selected_ticker:
        st.session_state.selected_ticker = t_input
        st.rerun()

    try:
        s_df = load_ticker_data(t_input)
        if s_df.empty:
            st.error(f"Chưa lấy được dữ liệu cho {t_input}.")
            st.stop()

        t_obj = yf.Ticker(f"{t_input}.VN")
        curr_p = float(s_df["Close"].iloc[-1])

        fin_q = t_obj.quarterly_financials
        rev_growth = 0.1
        trust = 65
        if not fin_q.empty and "Total Revenue" in fin_q.index and len(fin_q.columns) >= 5:
            try:
                rev_growth = (fin_q.loc["Total Revenue"].iloc[0] / fin_q.loc["Total Revenue"].iloc[4]) - 1
                trust = int(min(100, (rev_growth * 100) + (50 if curr_p > s_df["Close"].rolling(50).mean().iloc[-1] else 0)))
            except Exception:
                pass

        st.markdown(f"### 🧭 Niềm tin {t_input}: {trust}%")
        c_p, c1, c2, c3 = st.columns(4)
        p_base = curr_p * (1 + rev_growth) * inf_factor
        c_p.metric("📍 GIÁ HIỆN TẠI", f"{curr_p:,.0f}")
        c1.metric("🐢 Thận trọng", f"{curr_p * (1 + rev_growth * 0.4) * inf_factor:,.0f}")
        c2.metric("🏰 Cơ sở", f"{p_base:,.0f}")
        c3.metric("🚀 Phi thường", f"{curr_p * (1 + rev_growth * 2) * inf_factor:,.0f}")

        st.subheader("📊 Sức khỏe tài chính 5 Quý gần nhất (Tỷ VNĐ)")
        if not fin_q.empty:
            q_rev = (fin_q.loc["Total Revenue"].iloc[:5][::-1]) / 1e9 if "Total Revenue" in fin_q.index else pd.Series(dtype=float)
            if "Net Income" in fin_q.index:
                q_net = (fin_q.loc["Net Income"].iloc[:5][::-1]) / 1e9
            elif "Net Income From Continuing Operation Net Extraordinaries" in fin_q.index:
                q_net = (fin_q.loc["Net Income From Continuing Operation Net Extraordinaries"].iloc[:5][::-1]) / 1e9
            else:
                q_net = pd.Series(dtype=float)

            if not q_rev.empty and not q_net.empty:
                fig_fin = go.Figure()
                fig_fin.add_trace(
                    go.Bar(
                        x=q_rev.index.astype(str),
                        y=q_rev,
                        name="Doanh thu",
                        marker_color="#007bff",
                        text=q_rev.apply(lambda x: f"{x:,.0f}"),
                        textposition="auto",
                    )
                )
                fig_fin.add_trace(
                    go.Bar(
                        x=q_net.index.astype(str),
                        y=q_net,
                        name="Lợi nhuận",
                        marker_color="#FFD700",
                        text=q_net.apply(lambda x: f"{x:,.1f}"),
                        textposition="auto",
                    )
                )
                fig_fin.update_layout(
                    barmode="group",
                    height=350,
                    margin=dict(l=0, r=0, t=30, b=0),
                    template="plotly_white",
                    yaxis_title="Tỷ VNĐ",
                )
                st.plotly_chart(fig_fin, use_container_width=True)

        st.subheader(f"📈 Phân tích kỹ thuật {t_input}")
        s_df["tk"] = (s_df["High"].rolling(9).max() + s_df["Low"].rolling(9).min()) / 2
        s_df["kj"] = (s_df["High"].rolling(26).max() + s_df["Low"].rolling(26).min()) / 2
        s_df["sa"] = ((s_df["tk"] + s_df["kj"]) / 2).shift(26)
        s_df["sb"] = ((s_df["High"].rolling(52).max() + s_df["Low"].rolling(52).min()) / 2).shift(26)
        s_df["Vol_Avg"] = s_df["Volume"].rolling(20).mean()

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=s_df.index, open=s_df["Open"], high=s_df["High"], low=s_df["Low"], close=s_df["Close"], name="Giá"), row=1, col=1)
        fig.add_trace(go.Scatter(x=s_df.index, y=s_df["sa"], line=dict(width=0), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=s_df.index, y=s_df["sb"], line=dict(width=0), fill="tonexty", fillcolor="rgba(0, 150, 255, 0.1)", name="Mây"), row=1, col=1)
        fig.add_trace(go.Scatter(x=s_df.index, y=s_df["tk"], line=dict(color="#FF33CC", width=2), name="Tenkan"), row=1, col=1)
        fig.add_trace(go.Scatter(x=s_df.index, y=s_df["kj"], line=dict(color="#FFD700", width=2), name="Kijun"), row=1, col=1)

        v_colors = ["#FF4136" if o > c else "#2ECC40" for o, c in zip(s_df["Open"], s_df["Close"])]
        fig.add_trace(go.Bar(x=s_df.index, y=s_df["Volume"], marker_color=v_colors, name="Vol"), row=2, col=1)
        fig.add_trace(go.Scatter(x=s_df.index, y=s_df["Vol_Avg"], line=dict(color="#39CCCC", width=1.5), name="Vol TB20"), row=2, col=1)

        fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

        if st.button(f"📌 Lưu {t_input} vào Sổ Vàng"):
            st.session_state.history_log.append({"Mã": t_input, "Giá": f"{curr_p:,.0f}", "Ngày": datetime.now().strftime("%d/%m")})
            st.rerun()
    except Exception:
        st.error(f"Đang tạm soát mã cá {t_input}...")

with tab_bctc:
    st.subheader(f"📊 Mổ xẻ nội tạng Cá: {t_input}")

    uploaded_file = st.file_uploader(f"📂 Tải lên BCTC PDF của {t_input}", type=["pdf"])
    if uploaded_file:
        st.success(f"✅ Đã nhận file. Gemini sẵn sàng mổ xẻ mã {t_input}!")

    st.divider()

    if t_input and not vietstock_db.empty:
        fish_data = vietstock_db[vietstock_db["Mã CK"] == t_input]

        if not fish_data.empty:
            row = fish_data.iloc[0]

            def find_col(keyword):
                cols = [c for c in vietstock_db.columns if keyword.lower() in str(c).lower()]
                return cols[0] if cols else None

            col_rev = find_col("Doanh thu thuần") or find_col("Doanh thu bán hàng")
            col_profit = find_col("Lợi nhuận sau thuế")
            col_inventory = find_col("Hàng tồn kho")
            col_cash = find_col("Tiền và các khoản tương đương tiền")

            col_fa1, col_fa2 = st.columns([2, 1])

            with col_fa1:
                st.write("**📑 Thông số tài chính cốt lõi (Từ file Excel):**")
                summary_data = {
                    "Chỉ số": ["Doanh thu", "Lợi nhuận sau thuế", "Hàng tồn kho", "Tiền mặt"],
                    "Giá trị (VND)": [
                        f"{row[col_rev]:,.0f}" if col_rev else "N/A",
                        f"{row[col_profit]:,.0f}" if col_profit else "N/A",
                        f"{row[col_inventory]:,.0f}" if col_inventory else "N/A",
                        f"{row[col_cash]:,.0f}" if col_cash else "N/A",
                    ],
                }
                st.table(pd.DataFrame(summary_data))

            with col_fa2:
                st.write("**🏆 Đánh giá nhanh:**")
                if col_profit and col_rev:
                    val_profit = row[col_profit]
                    val_rev = row[col_rev]
                    st.metric("Lợi nhuận", f"{val_profit/1e9:,.2f} Tỷ")
                    net_margin = (val_profit / val_rev) * 100 if val_rev > 0 else 0
                    st.metric("Biên Lợi Nhuận Ròng", f"{net_margin:.1f}%")

                    if val_profit > 0:
                        st.success("🌟 Cá có lãi, nội tạng tốt!")
                    else:
                        st.error("⚠️ Cá đang sụt cân (Lỗ)")

            st.divider()

            st.subheader("🧠 Phân tích chuyên sâu (Tầm nhìn A7)")
            c1, c2 = st.columns(2)
            if col_inventory:
                c1.info(f"📦 **Của để dành (Tồn kho):** {row[col_inventory]/1e9:,.1f} Tỷ")
            if col_cash:
                c2.info(f"💰 **Sức mạnh tiền mặt:** {row[col_cash]/1e9:,.1f} Tỷ")

            st.info("💡 Kiểm tra xem 'Hàng tồn kho' có phải là các dự án sắp mở bán không. Đó là ngòi nổ cho SIÊU CÁ!")

        else:
            st.warning(f"Mã {t_input} không có trong bộ dữ liệu 3 sàn. Bro hãy kiểm tra lại file Excel.")
    else:
        st.info("Bro hãy chọn một con cá ở Tab Radar hoặc nhập mã để bắt đầu mổ xẻ.")

with tab_history:
    st.subheader("📓 DANH SÁCH CÁ ĐÃ TẦM SOÁT")
    if st.session_state.history_log:
        st.table(pd.DataFrame(st.session_state.history_log))
        st.info(
            """
            **📌 Ghi chú cho Ngư dân:**
            * **Giá lưu:** mức giá tại thời điểm đưa cá vào tầm ngắm.
            * **Kỷ luật:** Chỉ nên giữ tối đa 5-7 mã trong Sổ Vàng để tập trung nguồn lực.
            * **Lưu ý:** Dữ liệu này sẽ tự làm sạch khi đóng trình duyệt hoặc F5.
            """
        )

        if st.button("🧹 Làm sạch sổ"):
            st.session_state.history_log = []
            st.rerun()
    else:
        st.info("Sổ vàng vẫn đang đợi những con cá lớn. Hãy nhấn nút 'Lưu vào Sổ Vàng' ở Tab Chi tiết để ghi lại mục tiêu.")
