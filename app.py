import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime
import json
import os

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("📈 Comparador de Carteras Momentum + Quality")

STRATEGIES_FILE = "strategies.json"

def load_strategies_from_disk():
    if os.path.exists(STRATEGIES_FILE):
        try:
            with open(STRATEGIES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_strategies_to_disk(strategies):
    with open(STRATEGIES_FILE, "w") as f:
        json.dump(strategies, f, indent=2)

st.sidebar.header("Configuración")

# --- Accesos rápidos por año ---
st.sidebar.subheader("Acceso rápido por año")
current_year = datetime.today().year
available_years = list(range(2020, current_year + 1))

if "start_date" not in st.session_state:
    st.session_state.start_date = date(2023, 1, 1)
if "end_date" not in st.session_state:
    st.session_state.end_date = datetime.today().date()

cols = st.sidebar.columns(3)
for i, year in enumerate(available_years):
    col = cols[i % 3]
    if col.button(str(year)):
        st.session_state.start_date = date(year, 1, 1)
        st.session_state.end_date = date(year, 12, 31) if year != current_year else datetime.today().date()

start_date = st.sidebar.date_input("Fecha de inicio", st.session_state.start_date, key="start_date")
end_date = st.sidebar.date_input("Fecha de fin", st.session_state.end_date, key="end_date")

initial_capital = st.sidebar.number_input("Capital inicial (€)", value=10000, min_value=1000)
monthly_contribution = st.sidebar.number_input(
    "Aportación mensual (€)", value=0, min_value=0, step=50,
    help="Se añade el primer día de cotización de cada mes"
)
rebalance_band = st.sidebar.slider(
    "Banda de rebalanceo relativa (%)", min_value=1, max_value=50, value=5,
    help="Ej: con un objetivo del 90% y banda del 5%, se rebalancea si el peso sale del rango 85,5%-94,5% (90% ± 5% de 90%)"
) / 100
transaction_fee = st.sidebar.number_input(
    "Coste de transacción (%)", value=0.10, min_value=0.0, max_value=5.0, step=0.05,
    help="Comisión aplicada sobre cada compra, aportación y rebalanceo (ej. 0.10% típico en brokers de bajo coste)"
) / 100

tickers = {
    "MSCI World": "URTH",
    "Momentum": "IWMO.L",
    "Quality": "IWQU.L",
    "Renta Fija LP": "IDTL.L",
    "Monetario": "IB01.L",
    "Oro": "IGLN.L",
    "Emergentes": "EEM",
    "Small Caps": "IJR",
}

@st.cache_data(ttl=3600)
def download_data(tickers_dict, start, end):
    data = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty and 'Volume' in df.columns:
                df = df[df['Volume'] > 0]
            if not df.empty and len(df) > 10:
                close = df['Close']
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                data[name] = close
                st.sidebar.success(f"✅ {name} cargado")
            else:
                st.sidebar.warning(f"⚠️ Datos insuficientes para {name}")
        except Exception as e:
            st.sidebar.warning(f"⚠️ Error descargando {name}: {e}")
    return data

data_dict = download_data(tickers, start_date, end_date)

if len(data_dict) < 2:
    st.error("No hay suficientes datos. Prueba con otras fechas.")
    st.stop()

data = pd.concat(data_dict, axis=1)
data = data.dropna(how='all')
data = data.ffill().dropna()

available_assets = list(data.columns)

# --- Estrategias personalizadas (persistentes en disco) ---
st.sidebar.header("🎯 Estrategias personalizadas")

if "custom_strategies" not in st.session_state:
    st.session_state.custom_strategies = load_strategies_from_disk()

with st.sidebar.expander("➕ Crear nueva estrategia"):
    strategy_name = st.text_input("Nombre de la estrategia", key="new_strategy_name")
    st.write("Asigna el % de cada activo (deben sumar 100%):")
    strategy_weights = {}
    for asset in available_assets:
        w = st.number_input(f"{asset} (%)", min_value=0, max_value=100, value=0, step=5, key=f"w_{asset}")
        if w > 0:
            strategy_weights[asset] = w
    total_pct = sum(strategy_weights.values())
    st.caption(f"Total asignado: {total_pct}%")
    if st.button("Guardar estrategia"):
        if not strategy_name:
            st.warning("Ponle un nombre a la estrategia.")
        elif total_pct != 100:
            st.warning("Los porcentajes deben sumar exactamente 100%.")
        else:
            st.session_state.custom_strategies[strategy_name] = strategy_weights
            save_strategies_to_disk(st.session_state.custom_strategies)
            st.success(f"Estrategia '{strategy_name}' guardada permanentemente.")

if st.session_state.custom_strategies:
    st.sidebar.subheader("Estrategias guardadas")
    for name in list(st.session_state.custom_strategies.keys()):
        col1, col2 = st.sidebar.columns([3, 1])
        col1.write(f"**{name}**: {st.session_state.custom_strategies[name]}")
        if col2.button("🗑️", key=f"del_{name}"):
            del st.session_state.custom_strategies[name]
            save_strategies_to_disk(st.session_state.custom_strategies)
            st.rerun()

st.sidebar.header("Series base a mostrar")
selected_series = [s for s in available_assets if st.sidebar.checkbox(s, value=False, key=f"chk_{s}")]

selected_strategies = []
if st.session_state.custom_strategies:
    st.sidebar.header("Estrategias a mostrar")
    for name in st.session_state.custom_strategies:
        if st.sidebar.checkbox(name, value=True, key=f"chk_strat_{name}"):
            selected_strategies.append(name)

if not selected_series and not selected_strategies:
    st.warning("Selecciona al menos una serie o estrategia para visualizar.")
    st.stop()

def simulate_portfolio(prices, initial_capital, monthly_contribution, fee_pct=0.0):
    prices = prices.dropna()
    units = (initial_capital * (1 - fee_pct)) / prices.iloc[0]
    values = []
    contributed = initial_capital
    total_fees = initial_capital * fee_pct
    prev_period = (prices.index[0].year, prices.index[0].month)
    for i, dt in enumerate(prices.index):
        current_period = (dt.year, dt.month)
        if i > 0 and current_period != prev_period and monthly_contribution > 0:
            fee_amount = monthly_contribution * fee_pct
            units += (monthly_contribution - fee_amount) / prices.iloc[i]
            contributed += monthly_contribution
            total_fees += fee_amount
            prev_period = current_period
        values.append(units * prices.iloc[i])
    return pd.Series(values, index=prices.index), contributed, total_fees

def simulate_custom_strategy(prices_df, weights_pct, initial_capital, monthly_contribution, band, fee_pct=0.0):
    prices_df = prices_df.dropna()
    assets = list(weights_pct.keys())
    weights = {a: w / 100 for a, w in weights_pct.items()}

    shares = {a: (initial_capital * weights[a] * (1 - fee_pct)) / prices_df[a].iloc[0] for a in assets}
    values = []
    contributed = initial_capital
    total_fees = initial_capital * fee_pct
    prev_period = (prices_df.index[0].year, prices_df.index[0].month)
    rebalance_dates = []
    weight_history = []

    for i, dt in enumerate(prices_df.index):
        current_prices = prices_df.loc[dt]
        current_period = (dt.year, dt.month)

        if i > 0 and current_period != prev_period and monthly_contribution > 0:
            fee_amount = monthly_contribution * fee_pct
            net_contribution = monthly_contribution - fee_amount
            for a in assets:
                shares[a] += (net_contribution * weights[a]) / current_prices[a]
            contributed += monthly_contribution
            total_fees += fee_amount
            prev_period = current_period

        asset_values = {a: shares[a] * current_prices[a] for a in assets}
        total_value = sum(asset_values.values())
        actual_w = {a: asset_values[a] / total_value for a in assets}
        weight_history.append({"date": dt, **actual_w})

        needs_rebalance = any(
            abs(actual_w[a] - weights[a]) / weights[a] > band for a in assets
        )

        if needs_rebalance:
            turnover = sum(abs(total_value * weights[a] - asset_values[a]) for a in assets) / 2
            fee_amount = turnover * fee_pct
            total_value_after_fee = total_value - fee_amount
            for a in assets:
                shares[a] = (total_value_after_fee * weights[a]) / current_prices[a]
            rebalance_dates.append(dt)
            total_fees += fee_amount
            total_value = total_value_after_fee

        values.append(total_value)

    weight_df = pd.DataFrame(weight_history).set_index("date") if weight_history else pd.DataFrame()
    return pd.Series(values, index=prices_df.index), contributed, rebalance_dates, weight_df, total_fees

def cagr(series):
    days = (series.index[-1] - series.index[0]).days
    if days < 90:
        return float("nan")
    years = days / 365.25
    return ((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1) * 100

def max_drawdown(series):
    cummax = series.cummax()
    dd = series / cummax - 1
    return dd.min() * 100

results = {}
total_contributed = {}
rebalance_info = {}
fees_info = {}
weight_histories = {}

for col in selected_series:
    serie, contributed, fees = simulate_portfolio(data[col], initial_capital, monthly_contribution, transaction_fee)
    results[col] = serie
    total_contributed[col] = contributed
    fees_info[col] = fees

for name in selected_strategies:
    weights_pct = st.session_state.custom_strategies[name]
    assets_needed = list(weights_pct.keys())
    if not all(a in data.columns for a in assets_needed):
        st.warning(f"La estrategia '{name}' usa activos sin datos disponibles en este rango.")
        continue
    prices_subset = data[assets_needed]
    serie, contributed, reb_dates, weight_df, fees = simulate_custom_strategy(
        prices_subset, weights_pct, initial_capital, monthly_contribution, rebalance_band, transaction_fee
    )
    results[name] = serie
    total_contributed[name] = contributed
    rebalance_info[name] = len(reb_dates)
    fees_info[name] = fees
    weight_histories[name] = weight_df

portfolio_values = pd.DataFrame(results).dropna()

st.subheader(f"Evolución de las Carteras ({start_date} a {end_date})")
fig = go.Figure()
for col in portfolio_values.columns:
    fig.add_trace(go.Scatter(x=portfolio_values.index, y=portfolio_values[col], name=col))

fig.update_layout(height=650, template="plotly_white",
                  xaxis_title="Fecha", yaxis_title="Valor de la cartera")
st.plotly_chart(fig, use_container_width=True)

# --- Gráfico de composición de pesos en el tiempo ---
if weight_histories:
    st.subheader("📐 Composición de pesos en el tiempo (estrategias personalizadas)")
    strategy_to_plot = st.selectbox("Elige una estrategia para ver su evolución de pesos", list(weight_histories.keys()))
    wdf = weight_histories[strategy_to_plot]
    if not wdf.empty:
        fig_weights = go.Figure()
        for asset in wdf.columns:
            fig_weights.add_trace(go.Scatter(
                x=wdf.index, y=wdf[asset] * 100,
                name=asset, stackgroup="one", mode="lines"
            ))
        target_weights = st.session_state.custom_strategies[strategy_to_plot]
        fig_weights.update_layout(
            height=450, template="plotly_white",
            xaxis_title="Fecha", yaxis_title="Peso (%)",
            title=f"Evolución de pesos — objetivo: {target_weights}"
        )
        st.plotly_chart(fig_weights, use_container_width=True)

st.subheader("📊 Resultados finales")
summary_data = {}
for col in portfolio_values.columns:
    serie = portfolio_values[col]
    cagr_val = cagr(serie)
    summary_data[col] = {
        "Valor final": round(serie.iloc[-1], 2),
        "Total aportado": round(total_contributed[col], 2),
        "Comisiones pagadas": round(fees_info.get(col, 0), 2),
        "Ganancia neta": round(serie.iloc[-1] - total_contributed[col], 2),
        "Rentabilidad Total (%)": round((serie.iloc[-1] / total_contributed[col] - 1) * 100, 2),
        "Rentabilidad Anualizada (%)": round(cagr_val, 2) if not pd.isna(cagr_val) else "Periodo muy corto",
        "Máximo Drawdown (%)": round(max_drawdown(serie), 2),
        "Nº Rebalanceos": rebalance_info.get(col, "—")
    }

summary = pd.DataFrame(summary_data).T
st.dataframe(summary)

st.success("¡App funcionando con tus tickers!")