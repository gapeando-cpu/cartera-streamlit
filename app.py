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

app_mode = st.sidebar.radio(
    "Modo de simulación",
    ["📈 Acumulación (aportaciones)", "💸 Retiro (fase de jubilación)"],
    help="Elige si estás ahorrando/aportando o si ya estás retirando dinero con la regla del colchón"
)

# ============================================================
# MODO RETIRO (FASE DE JUBILACIÓN CON COLCHÓN)
# ============================================================
if app_mode == "💸 Retiro (fase de jubilación)":
    st.header("💸 Simulación de Retiro con Colchón")
    st.caption("Simula desde 1997 usando el índice MSCI World real, con reglas de retiro según el año anterior y un colchón en monetario.")

    col1, col2 = st.sidebar.columns(2)
    start_year_ret = col1.number_input("Año inicio", min_value=1997, max_value=2026, value=1997)
    end_year_ret = col2.number_input("Año fin", min_value=1997, max_value=2026, value=2026)

    st.sidebar.subheader("💰 Capital y gastos")
    initial_fund_value = st.sidebar.number_input("Capital inicial en el Fondo (€)", value=300000, min_value=1000, step=10000)
    annual_expenses = st.sidebar.number_input("Gastos anuales (€)", value=15000, min_value=1000, step=500,
        help="Se retiran del Colchón en años negativos. También define el tamaño del Colchón.")
    fund_withdrawal_positive = st.sidebar.number_input("Retiro del Fondo en año positivo/plano (€)", value=20000, min_value=0, step=500,
        help="Cantidad que retiras del Fondo cuando el año ANTERIOR fue positivo o plano")

    st.sidebar.subheader("🛡️ Colchón (Monetario)")
    cushion_multiple = st.sidebar.number_input("Múltiplo de gastos anuales para el Colchón", value=3.0, min_value=1.0, step=0.5,
        help="Ej: 3x gastos anuales = límite máximo del colchón")

    st.sidebar.subheader("📊 Inflación y fiscalidad")
    inflation_rate_ret = st.sidebar.number_input("Inflación anual (%)", value=3.0, min_value=0.0, max_value=15.0, step=0.5) / 100
    apply_tax = st.sidebar.checkbox("Aplicar IRPF sobre plusvalías al vender del Fondo", value=True)
    tax_rate = st.sidebar.number_input("Tipo medio IRPF (%)", value=23.0, min_value=0.0, max_value=50.0, step=1.0,
        disabled=not apply_tax) / 100
    cost_basis_pct = st.sidebar.slider("% del importe vendido considerado 'coste' (resto es plusvalía)",
        min_value=0, max_value=100, value=50, disabled=not apply_tax) / 100

    @st.cache_data(ttl=3600)
    def descargar_msci_world_historico(start="1996-01-01", end="2026-07-05"):
        df = yf.download("^990100-USD-STRD", start=start, end=end, progress=False, auto_adjust=True)
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna()

    def simulate_withdrawal_strategy(
        close_prices, start_year, end_year,
        initial_fund_value, annual_expenses, fund_withdrawal_positive,
        cushion_multiple, inflation_rate, apply_tax, tax_rate, cost_basis_pct
    ):
        annual_prices = close_prices.resample('YE').last()
        annual_prices = annual_prices[(annual_prices.index.year >= start_year - 1) & (annual_prices.index.year <= end_year)]
        annual_returns = annual_prices.pct_change().dropna()

        fund_value = initial_fund_value
        current_expenses = annual_expenses
        current_fund_withdrawal_target = fund_withdrawal_positive
        cushion_max = cushion_multiple * current_expenses
        cushion = cushion_max

        records = []
        prev_year_positive = True

        for dt, ret in annual_returns.items():
            year = dt.year
            fund_before = fund_value
            fund_value = fund_value * (1 + ret)
            fund_growth = fund_value - fund_before

            tax_paid, cushion_refill, forced = 0, 0, False
            source = "Fondo" if prev_year_positive else "Colchón"
            target = current_fund_withdrawal_target if prev_year_positive else current_expenses

            if source == "Fondo":
                needed = target
                if apply_tax:
                    gain = needed * (1 - cost_basis_pct)
                    tax_paid = gain * tax_rate
                    needed += tax_paid
                fund_value = max(0, fund_value - needed)

                # Excedente de revalorización recarga el colchón vía traspaso (sin peaje fiscal)
                surplus = fund_growth - needed
                if surplus > 0 and cushion < cushion_max:
                    cushion_refill = min(surplus, cushion_max - cushion)
                    cushion += cushion_refill
            else:
                if cushion >= target:
                    cushion -= target
                else:
                    remaining = target - cushion
                    cushion = 0
                    forced = True
                    needed = remaining
                    if apply_tax:
                        gain = needed * (1 - cost_basis_pct)
                        tax_paid = gain * tax_rate
                        needed += tax_paid
                    fund_value = max(0, fund_value - needed)

            records.append({
                "Año": year,
                "Rentabilidad Fondo (%)": round(ret * 100, 2),
                "Año anterior": "Positivo/Plano" if prev_year_positive else "Negativo",
                "Fuente retiro": source if not forced else "Fondo (colchón agotado)",
                "Retiro objetivo (€)": round(target, 2),
                "Impuestos pagados (€)": round(tax_paid, 2),
                "Recarga colchón (€)": round(cushion_refill, 2),
                "Valor Fondo (€)": round(fund_value, 2),
                "Colchón (€)": round(cushion, 2),
                "Gastos anuales (€)": round(current_expenses, 2),
                "Retiro fondo objetivo (€)": round(current_fund_withdrawal_target, 2),
                "Límite colchón (€)": round(cushion_max, 2),
                "Patrimonio Total (€)": round(fund_value + cushion, 2),
            })

            prev_year_positive = ret >= 0
            current_expenses *= (1 + inflation_rate)
            current_fund_withdrawal_target *= (1 + inflation_rate)
            cushion_max = cushion_multiple * current_expenses

        return pd.DataFrame(records)

    close_hist = descargar_msci_world_historico()

    resultado_retiro = simulate_withdrawal_strategy(
        close_hist,
        start_year=int(start_year_ret),
        end_year=int(end_year_ret),
        initial_fund_value=initial_fund_value,
        annual_expenses=annual_expenses,
        fund_withdrawal_positive=fund_withdrawal_positive,
        cushion_multiple=cushion_multiple,
        inflation_rate=inflation_rate_ret,
        apply_tax=apply_tax,
        tax_rate=tax_rate,
        cost_basis_pct=cost_basis_pct,
    )

    st.subheader(f"Evolución del Patrimonio ({start_year_ret}-{end_year_ret})")
    fig_ret = go.Figure()
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["Año"], y=resultado_retiro["Valor Fondo (€)"],
        name="Fondo", stackgroup="one", mode="lines"))
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["Año"], y=resultado_retiro["Colchón (€)"],
        name="Colchón (Monetario)", stackgroup="one", mode="lines"))
    fig_ret.update_layout(height=500, template="plotly_white",
        xaxis_title="Año", yaxis_title="Valor (€)")
    st.plotly_chart(fig_ret, use_container_width=True)

    agotado = resultado_retiro[resultado_retiro["Patrimonio Total (€)"] <= 0]
    if not agotado.empty:
        st.error(f"⚠️ El patrimonio se agota en el año {agotado.iloc[0]['Año']}.")
    else:
        st.success(f"✅ El patrimonio sobrevive todo el periodo. Valor final: {resultado_retiro.iloc[-1]['Patrimonio Total (€)']:,.2f} €")

    st.subheader("📋 Detalle año a año")
    st.dataframe(resultado_retiro, use_container_width=True)

    total_taxes = resultado_retiro["Impuestos pagados (€)"].sum()
    years_from_fund = (resultado_retiro["Fuente retiro"].str.contains("Fondo")).sum()
    years_from_cushion = (resultado_retiro["Fuente retiro"] == "Colchón").sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total impuestos pagados", f"{total_taxes:,.0f} €")
    m2.metric("Años retirando del Fondo", years_from_fund)
    m3.metric("Años retirando del Colchón", years_from_cushion)

    csv = resultado_retiro.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar simulación (CSV)", csv, "simulacion_retiro.csv", "text/csv")

    st.stop()

# ============================================================
# MODO ACUMULACIÓN (TU APP ORIGINAL, SIN CAMBIOS)
# ============================================================

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
      