import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime
import json
import os

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("ðŸ“ˆ Comparador de Carteras Momentum + Quality")

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

tickers = {
    "MSCI World": "URTH",
    "MSCI World Value": "IWVL.L",
    "Momentum": "IWMO.L",
    "Quality": "IWQU.L",
    "Renta Fija LP": "IDTL.L",
    "Monetario": "IB01.L",
    "Oro": "IGLN.L",
    "Emergentes": "EEM",
    "Small Caps": "IJR",
}

HISTORICAL_INDEX_TICKER = "^990100-USD-STRD"

st.sidebar.header("ConfiguraciÃ³n")

app_mode = st.sidebar.radio(
    "Modo de simulaciÃ³n",
    ["ðŸ“ˆ AcumulaciÃ³n (aportaciones)", "ðŸ’¸ Retiro (fase de jubilaciÃ³n)"],
    help="Elige si estÃ¡s ahorrando/aportando o si ya estÃ¡s retirando dinero con la regla del colchÃ³n"
)

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
                st.sidebar.success(f"âœ… {name} cargado")
            else:
                st.sidebar.warning(f"âš ï¸ Datos insuficientes para {name}")
        except Exception as e:
            st.sidebar.warning(f"âš ï¸ Error descargando {name}: {e}")
    return data

@st.cache_data(ttl=3600)
def download_single_series(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()

# ============================================================
# MODO RETIRO (FASE DE JUBILACIÃ“N CON COLCHÃ“N)
# ============================================================
if app_mode == "ðŸ’¸ Retiro (fase de jubilaciÃ³n)":
    st.header("ðŸ’¸ SimulaciÃ³n de Retiro con ColchÃ³n")
    st.caption("El ColchÃ³n NO depende de ningÃºn ETF real. Tiene un rendimiento anual deseado, pero nunca puede superar la inflaciÃ³n de ese aÃ±o.")

    col1, col2 = st.sidebar.columns(2)
    start_year_ret = col1.number_input("AÃ±o inicio", min_value=1997, max_value=2026, value=1997)
    end_year_ret = col2.number_input("AÃ±o fin", min_value=1997, max_value=2026, value=2026)

    st.sidebar.subheader("ðŸ“Š Activo o estrategia de crecimiento")

    if "custom_strategies" not in st.session_state:
        st.session_state.custom_strategies = load_strategies_from_disk()

    growth_options = ["MSCI World (histÃ³rico ampliado desde 1997)"] + list(tickers.keys())
    if st.session_state.custom_strategies:
        growth_options += [f"ðŸ“ {name}" for name in st.session_state.custom_strategies]

    growth_choice = st.sidebar.selectbox(
        "Â¿Con quÃ© inviertes el Fondo durante el retiro?",
        growth_options,
        help="Puedes elegir un Ãºnico activo, o una de tus estrategias personalizadas creadas en modo AcumulaciÃ³n"
    )

    st.sidebar.subheader("ðŸ’° Capital y gastos")
    initial_fund_value = st.sidebar.number_input("Capital inicial en el Fondo (â‚¬)", value=300000, min_value=1000, step=10000)
    annual_expenses = st.sidebar.number_input("Gastos anuales (â‚¬)", value=15000, min_value=1000, step=500,
        help="Se retiran del ColchÃ³n en aÃ±os negativos. TambiÃ©n define el tamaÃ±o del ColchÃ³n.")
    fund_withdrawal_positive = st.sidebar.number_input("Retiro del Fondo en aÃ±o positivo/plano (â‚¬)", value=20000, min_value=0, step=500,
        help="Cantidad que retiras del Fondo cuando el aÃ±o ANTERIOR fue positivo o plano")

    st.sidebar.subheader("ðŸ“Š InflaciÃ³n y fiscalidad")
    inflation_rate_ret = st.sidebar.number_input("InflaciÃ³n anual (%)", value=3.0, min_value=0.0, max_value=15.0, step=0.5) / 100
    apply_tax = st.sidebar.checkbox("Aplicar IRPF sobre plusvalÃ­as al vender del Fondo", value=True)
    tax_rate = st.sidebar.number_input("Tipo medio IRPF (%)", value=23.0, min_value=0.0, max_value=50.0, step=1.0,
        disabled=not apply_tax) / 100
    cost_basis_pct = st.sidebar.slider("% del importe vendido considerado 'coste' (resto es plusvalÃ­a)",
        min_value=0, max_value=100, value=50, disabled=not apply_tax) / 100

    st.sidebar.subheader("ðŸ›¡ï¸ ColchÃ³n (sin ETF, capado a inflaciÃ³n)")
    cushion_multiple = st.sidebar.number_input("MÃºltiplo de gastos anuales para el ColchÃ³n", value=3.0, min_value=1.0, step=0.5,
        help="Ej: 3x gastos anuales = lÃ­mite mÃ¡ximo del colchÃ³n")
    cushion_desired_return = st.sidebar.number_input(
        "Rendimiento anual deseado del ColchÃ³n (%)", value=2.0, min_value=0.0, max_value=15.0, step=0.5,
        help="El colchÃ³n crecerÃ¡ a este ritmo cada aÃ±o, pero NUNCA por encima de la inflaciÃ³n de ese aÃ±o (se aplica el mÃ­nimo entre ambos)."
    ) / 100
    cushion_effective_return = min(cushion_desired_return, inflation_rate_ret)
    st.sidebar.caption(f"âž¡ï¸ Rendimiento efectivo del ColchÃ³n: **{cushion_effective_return*100:.2f}%** (mÃ­nimo entre deseado e inflaciÃ³n)")

    if growth_choice == "MSCI World (histÃ³rico ampliado desde 1997)":
        growth_series = download_single_series(HISTORICAL_INDEX_TICKER, "1996-01-01", "2026-07-05")
        growth_label = "MSCI World (Ã­ndice histÃ³rico)"
    elif growth_choice.startswith("ðŸ“ "):
        strategy_name = growth_choice.replace("ðŸ“ ", "")
        weights_pct = st.session_state.custom_strategies[strategy_name]
        assets_needed = list(weights_pct.keys())
        data_strategy = download_data({a: tickers[a] for a in assets_needed}, "2015-01-01", "2026-07-05")
        combined = pd.concat(data_strategy, axis=1).ffill().dropna()
        normalized = combined / combined.iloc[0]
        weights_frac = {a: w / 100 for a, w in weights_pct.items()}
        growth_series = sum(normalized[a] * weights_frac[a] for a in assets_needed) * initial_fund_value
        growth_series = growth_series / growth_series.iloc[0]
        growth_label = f"Estrategia '{strategy_name}' (sin rebalanceo, buy&hold para esta simulaciÃ³n)"
    else:
        growth_series = download_single_series(tickers[growth_choice], "1996-01-01", "2026-07-05")
        growth_label = growth_choice

    st.info(f"ðŸ“Œ Activo de crecimiento del Fondo: **{growth_label}** Â· ColchÃ³n: **{cushion_effective_return*100:.2f}% anual (capado a inflaciÃ³n)**")

    def simulate_withdrawal_capped_cushion(
        growth_prices, start_year, end_year,
        initial_fund_value, annual_expenses, fund_withdrawal_positive,
        cushion_multiple, cushion_desired_return, inflation_rate,
        apply_tax, tax_rate, cost_basis_pct
    ):
        growth_annual = growth_prices.resample('YE').last()
        min_year_available = growth_annual.index.year.min()
        effective_start_year = max(start_year, min_year_available)

        growth_annual = growth_annual[(growth_annual.index.year >= effective_start_year - 1) & (growth_annual.index.year <= end_year)]
        growth_returns = growth_annual.pct_change().dropna()

        fund_value = initial_fund_value
        current_expenses = annual_expenses
        current_fund_withdrawal_target = fund_withdrawal_positive
        cushion_max = cushion_multiple * current_expenses
        cushion = cushion_max
        cushion_growth_rate = min(cushion_desired_return, inflation_rate)

        records = []
        prev_year_positive = True

        for dt, ret in growth_returns.items():
            year = dt.year
            fund_before = fund_value
            fund_value = fund_value * (1 + ret)
            fund_growth = fund_value - fund_before

            cushion = cushion * (1 + cushion_growth_rate)

            tax_paid, cushion_refill, forced = 0, 0, False
            source = "Fondo" if prev_year_positive else "ColchÃ³n"
            target = current_fund_withdrawal_target if prev_year_positive else current_expenses

            if source == "Fondo":
                needed = target
                if apply_tax:
                    gain = needed * (1 - cost_basis_pct)
                    tax_paid = gain * tax_rate
                    needed += tax_paid
                fund_value = max(0, fund_value - needed)

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
                "AÃ±o": year,
                "Rentabilidad Fondo (%)": round(ret * 100, 2),
                "Rentabilidad ColchÃ³n (%)": round(cushion_growth_rate * 100, 2),
                "AÃ±o anterior": "Positivo/Plano" if prev_year_positive else "Negativo",
                "Fuente retiro": source if not forced else "Fondo (colchÃ³n agotado)",
                "Retiro objetivo (â‚¬)": round(target, 2),
                "Impuestos pagados (â‚¬)": round(tax_paid, 2),
                "Recarga colchÃ³n (â‚¬)": round(cushion_refill, 2),
                "Valor Fondo (â‚¬)": round(fund_value, 2),
                "ColchÃ³n (â‚¬)": round(cushion, 2),
                "Patrimonio Total (â‚¬)": round(fund_value + cushion, 2),
            })

            prev_year_positive = ret >= 0
            current_expenses *= (1 + inflation_rate)
            current_fund_withdrawal_target *= (1 + inflation_rate)
            cushion_max = cushion_multiple * current_expenses

        return pd.DataFrame(records), effective_start_year

    resultado_retiro, eff_year = simulate_withdrawal_capped_cushion(
        growth_series,
        int(start_year_ret), int(end_year_ret),
        initial_fund_value, annual_expenses, fund_withdrawal_positive,
        cushion_multiple, cushion_desired_return, inflation_rate_ret,
        apply_tax, tax_rate, cost_basis_pct
    )

    if eff_year > start_year_ret:
        st.warning(f"âš ï¸ El activo/estrategia elegido no tiene histÃ³rico desde {start_year_ret}. La simulaciÃ³n empieza en {eff_year} (primer aÃ±o con datos disponibles para ese activo de crecimiento).")

    st.subheader(f"EvoluciÃ³n del Patrimonio ({eff_year}-{end_year_ret})")
    fig_ret = go.Figure()
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["AÃ±o"], y=resultado_retiro["Valor Fondo (â‚¬)"],
        name="Fondo", stackgroup="one", mode="lines"))
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["AÃ±o"], y=resultado_retiro["ColchÃ³n (â‚¬)"],
        name=f"ColchÃ³n (capado a inflaciÃ³n, {cushion_effective_return*100:.1f}%)", stackgroup="one", mode="lines"))
    fig_ret.update_layout(height=500, template="plotly_white",
        xaxis_title="AÃ±o", yaxis_title="Valor (â‚¬)")
    st.plotly_chart(fig_ret, use_container_width=True)

    agotado = resultado_retiro[resultado_retiro["Patrimonio Total (â‚¬)"] <= 0]
    if not agotado.empty:
        st.error(f"âš ï¸ El patrimonio se agota en el aÃ±o {agotado.iloc[0]['AÃ±o']}.")
    else:
        st.success(f"âœ… El patrimonio sobrevive todo el periodo. Valor final: {resultado_retiro.iloc[-1]['Patrimonio Total (â‚¬)']:,.2f} â‚¬")

    st.subheader("ðŸ“‹ Detalle aÃ±o a aÃ±o")
    st.dataframe(resultado_retiro, use_container_width=True)

    total_taxes = resultado_retiro["Impuestos pagados (â‚¬)"].sum()
    years_from_fund = (resultado_retiro["Fuente retiro"].str.contains("Fondo")).sum()
    years_from_cushion = (resultado_retiro["Fuente retiro"] == "ColchÃ³n").sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total impuestos pagados", f"{total_taxes:,.0f} â‚¬")
    m2.metric("AÃ±os retirando del Fondo", years_from_fund)
    m3.metric("AÃ±os retirando del ColchÃ³n", years_from_cushion)

    csv = resultado_retiro.to_csv(index=False).encode('utf-8')
    st.download_button("ðŸ“¥ Descargar simulaciÃ³n (CSV)", csv, "simulacion_retiro.csv", "text/csv")

    st.stop()

# ============================================================
# MODO ACUMULACIÃ“N
# ============================================================

st.sidebar.subheader("Acceso rÃ¡pido por aÃ±o")
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

initial_capital = st.sidebar.number_input("Capital inicial (â‚¬)", value=10000, min_value=1000)
monthly_contribution = st.sidebar.number_input(
    "AportaciÃ³n mensual (â‚¬)", value=0, min_value=0, step=50,
    help="Se aÃ±ade el primer dÃ­a de cotizaciÃ³n de cada mes"
)
rebalance_band = st.sidebar.slider(
    "Banda de rebalanceo relativa (%)", min_value=1, max_value=50, value=5,
    help="Ej: con un objetivo del 90% y banda del 5%, se rebalancea si el peso sale del rango 85,5%-94,5% (90% Â± 5% de 90%)"
) / 100
transaction_fee = st.sidebar.number_input(
    "Coste de transacciÃ³n (%)", value=0.10, min_value=0.0, max_value=5.0, step=0.05,
    help="ComisiÃ³n aplicada sobre cada compra, aportaciÃ³n y rebalanceo (ej. 0.10% tÃ­pico en brokers de bajo coste)"
) / 100

data_dict = download_data(tickers, start_date, end_date)

if len(data_dict) < 2:
    st.error("No hay suficientes datos. Prueba con otras fechas.")
    st.stop()

data = pd.concat(data_dict, axis=1)
data = data.ffill()

available_assets = list(data.columns)

st.sidebar.header("ðŸŽ¯ Estrategias personalizadas")

if "custom_strategies" not in st.session_state:
    st.session_state.custom_strategies = load_strategies_from_disk()

with st.sidebar.expander("âž• Crear nueva estrategia"):
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
        if col2.button("ðŸ—‘ï¸", key=f"del_{name}"):
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
   