import glob
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Afficionado Coffee Roasters - Sales Analytics", layout="wide")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def bucket(h):
    if 6 <= h <= 11:
        return "Morning (6-11)"
    if 12 <= h <= 16:
        return "Afternoon (12-16)"
    if 17 <= h <= 21:
        return "Evening (17-21)"
    return "Late hours (22-5)"


@st.cache_data
def prepare(df):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    # Validation
    df = df.drop_duplicates(subset="transaction_id")
    df = df[(df["transaction_qty"] > 0) & (df["unit_price"] > 0)]
    # Features
    df["revenue"] = df["transaction_qty"] * df["unit_price"]
    t = pd.to_datetime(df["transaction_time"].astype(str), errors="coerce")
    df = df[t.notna()].copy()
    df["hour"] = t[t.notna()].dt.hour
    df["time_bucket"] = df["hour"].apply(bucket)
    date_col = next((c for c in ["transaction_date", "date", "order_date"] if c in df.columns), None)
    if date_col is None:
        date_col = next((c for c in df.columns if "date" in c), None)
    if date_col:
        df["date"] = pd.to_datetime(df[date_col], errors="coerce")
        df = df[df["date"].notna()].copy()
        df["day_of_week"] = df["date"].dt.day_name()
    else:
        df["date"] = pd.NaT
        df["day_of_week"] = None
    return df, date_col is not None


@st.cache_data
def load_default():
    files = glob.glob("data/*.csv") + glob.glob("*.csv") + glob.glob("data/*.xlsx") + glob.glob("*.xlsx")
    if not files:
        return None
    f = files[0]
    return pd.read_csv(f) if f.endswith(".csv") else pd.read_excel(f)


st.title("Afficionado Coffee Roasters - Sales Trend & Time-Based Analysis")

raw = load_default()
if raw is None:
    up = st.file_uploader("Upload the transaction dataset (CSV or Excel)", type=["csv", "xlsx"])
    if up is None:
        st.info("Add the dataset to the repository (data/ folder) or upload it here.")
        st.stop()
    raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)

df, has_date = prepare(raw)

# ---------------- Sidebar controls ----------------
st.sidebar.header("Filters")
stores = sorted(df["store_location"].unique())
sel_stores = st.sidebar.multiselect("Store location", stores, default=stores)
if has_date:
    sel_days = st.sidebar.multiselect("Day of week", DAYS, default=DAYS)
else:
    sel_days = DAYS
hr = st.sidebar.slider("Hour range", 0, 23, (6, 22))
metric_choice = st.sidebar.radio("Metric", ["Revenue", "Quantity"])
metric = "revenue" if metric_choice == "Revenue" else "transaction_qty"

f = df[df["store_location"].isin(sel_stores) & df["hour"].between(hr[0], hr[1])]
if has_date:
    f = f[f["day_of_week"].isin(sel_days)]
if f.empty:
    st.warning("No data for the selected filters.")
    st.stop()

# ---------------- KPIs ----------------
c1, c2, c3 = st.columns(3)
c1.metric("Total revenue", f"${f['revenue'].sum():,.0f}")
c2.metric("Transactions", f"{f['transaction_id'].nunique():,}")
c3.metric("Units sold", f"{int(f['transaction_qty'].sum()):,}")

tab1, tab2, tab3, tab4 = st.tabs(["Sales trend", "Day of week", "Hourly demand", "Location comparison"])

with tab1:
    if has_date:
        daily = f.groupby("date", as_index=False)[metric].sum()
        st.plotly_chart(px.line(daily, x="date", y=metric, title=f"Daily {metric_choice.lower()}"), use_container_width=True)
        weekly = f.set_index("date").resample("W")[metric].sum().reset_index()
        st.plotly_chart(px.line(weekly, x="date", y=metric, markers=True, title=f"Weekly {metric_choice.lower()}"), use_container_width=True)
        by_store = f.groupby(["date", "store_location"], as_index=False)[metric].sum()
        st.plotly_chart(px.line(by_store, x="date", y=metric, color="store_location", title="Store-level trend"), use_container_width=True)
    else:
        st.info("No date column found in the dataset, so date-based trends are unavailable.")

with tab2:
    if has_date:
        per_day = f.groupby(["date", "day_of_week"], as_index=False)[metric].sum()
        avg = per_day.groupby("day_of_week")[metric].mean().reindex(DAYS).dropna().reset_index()
        st.plotly_chart(px.bar(avg, x="day_of_week", y=metric, title=f"Average daily {metric_choice.lower()} by day of week"), use_container_width=True)
        f2 = f.assign(period=f["day_of_week"].isin(["Saturday", "Sunday"]).map({True: "Weekend", False: "Weekday"}))
        wk = f2.groupby(["date", "period"], as_index=False)[metric].sum().groupby("period")[metric].mean().reset_index()
        st.plotly_chart(px.bar(wk, x="period", y=metric, title="Weekday vs weekend (average per day)"), use_container_width=True)
    else:
        st.info("No date column found, so day-of-week analysis is unavailable.")

with tab3:
    hourly = f.groupby("hour", as_index=False).agg(revenue=("revenue", "sum"), quantity=("transaction_qty", "sum"), transactions=("transaction_id", "nunique"))
    st.plotly_chart(px.line(hourly, x="hour", y="transactions", markers=True, title="Transactions by hour"), use_container_width=True)
    st.plotly_chart(px.bar(hourly, x="hour", y="revenue" if metric == "revenue" else "quantity", title=f"{metric_choice} by hour"), use_container_width=True)
    bk = f.groupby("time_bucket", as_index=False)[metric].sum()
    st.plotly_chart(px.pie(bk, names="time_bucket", values=metric, title="Share by time bucket"), use_container_width=True)

with tab4:
    st.subheader("Hourly heatmaps per store")
    for s in sel_stores:
        sub = f[f["store_location"] == s]
        if has_date:
            pv = sub.pivot_table(index="day_of_week", columns="hour", values=metric, aggfunc="sum").reindex(DAYS)
            fig = px.imshow(pv, aspect="auto", color_continuous_scale="YlOrBr", title=s)
        else:
            pv = sub.groupby("hour")[metric].sum().to_frame().T
            fig = px.imshow(pv, aspect="auto", color_continuous_scale="YlOrBr", title=s)
        st.plotly_chart(fig, use_container_width=True)
    comp = f.groupby(["hour", "store_location"], as_index=False)[metric].sum()
    st.plotly_chart(px.line(comp, x="hour", y=metric, color="store_location", title="Peak-hour comparison across stores"), use_container_width=True)
