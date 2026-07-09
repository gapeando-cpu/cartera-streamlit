import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime
import json
import os

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("Comparador de Carteras Momentum + Quality")

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

st.sidebar.header("Configuracion")

app_mode = st.sidebar.radio(
    "Modo de simulacion",
    ["Acumulacion (aportaciones)", "Retiro (fase de jubilacion)"],
    help="Elige si estas ahorrando/aportando o si ya estas retirando dinero con la regla del colchon"
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
                st.sidebar.success(f"{name} cargado")
            else:
                st.sidebar.warning(f"Datos insuficientes para {name}")
        except Exception as e:
            st.sidebar.warning(f"Error descargando {name}: {e}")
    return data

@st.cache_data(ttl=3600)
def download_single_series(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()

# ============================================================
# MODO RETIRO (ESTRATEGIA MEZCLA: COLCHON + TENDENCIA + GUARDRAILS, MENSUAL)
# ============================================================
if app_mode == "Retiro (fase de jubilacion)":
    st.header("Simulacion de Retiro Mensual: Estrategia Mezcla (Colchon + Guardrails)")
    st.caption(
        "Estrategia basada en evidencia (Bengen, Trinity Study, Guyton-Klinger): "
        "cubo de liquidez (colchon) para evitar vender en caidas, retiro condicionado a la "
        "tendencia del mercado, ajuste dinamico del gasto (guardrails) y congelacion de la "
        "subida por inflacion tras periodos negativos (regla 'sin subida')."
    )

    col1, col2 = st.sidebar.columns(2)
    start_year_ret = col1.number_input("Ano inicio", min_value=1997, max_value=2026, value=1997)
    end_year_ret = col2.number_input("Ano fin", min_value=1997, max_value=2026, value=2026)

    st.sidebar.subheader("Activo o estrategia de crecimiento")

    if "custom_strategies" not in st.session_state:
        st.session_state.custom_strategies = load_strategies_from_disk()

    growth_options = ["MSCI World (historico ampliado desde 1997)"] + list(tickers.keys())
    if st.session_state.custom_strategies:
        growth_options += [f"[Estrategia] {name}" for name in st.session_state.custom_strategies]

    growth_choice = st.sidebar.selectbox(
        "Con que inviertes el Fondo durante el retiro?",
        growth_options,
        help="Puedes elegir un unico activo, o una de tus estrategias personalizadas creadas en modo Acumulacion"
    )

    st.sidebar.subheader("Capital y gastos")
    initial_fund_value = st.sidebar.number_input("Capital inicial en el Fondo (EUR)", value=300000, min_value=1000, step=10000)
    annual_expenses = st.sidebar.number_input("Gastos anuales (EUR)", value=15000, min_value=1000, step=500,
        help="Se retiran del Colchon en meses de mercado bajista. Tambien define el tamano del Colchon.")
    fund_withdrawal_positive = st.sidebar.number_input("Retiro anual del Fondo en tendencia alcista (EUR)", value=20000, min_value=0, step=500,
        help="Cantidad anual (repartida en 12 meses) que retiras del Fondo cuando la tendencia de los ultimos 12 meses es positiva")

    st.sidebar.subheader("Inflacion y fiscalidad")
    inflation_rate_ret = st.sidebar.number_input("Inflacion anual (%)", value=3.0, min_value=0.0, max_value=15.0, step=0.5) / 100
    skip_cola_on_down_year = st.sidebar.checkbox(
        "Congelar subida por inflacion tras ano bajista (regla 'sin subida')", value=True,
        help="Regla de Guyton-Klinger: si la rentabilidad de los ultimos 12 meses fue negativa, no se sube el gasto por inflacion ese ano"
    )
    apply_tax = st.sidebar.checkbox("Aplicar IRPF sobre plusvalias al vender del Fondo", value=True)
    tax_rate = st.sidebar.number_input("Tipo medio IRPF (%)", value=23.0, min_value=0.0, max_value=50.0, step=1.0,
        disabled=not apply_tax) / 100
    cost_basis_pct = st.sidebar.slider("% del importe vendido considerado 'coste' (resto es plusvalia)",
        min_value=0, max_value=100, value=50, disabled=not apply_tax) / 100

    st.sidebar.subheader("Colchon (cubo de liquidez, capado a inflacion)")
    cushion_multiple = st.sidebar.number_input("Multiplo de gastos anuales para el Colchon", value=3.0, min_value=1.0, step=0.5,
        help="Ej: 3x gastos anuales = tamano objetivo del cubo de liquidez")
    cushion_desired_return = st.sidebar.number_input(
        "Rendimiento anual deseado del Colchon (%)", value=2.0, min_value=0.0, max_value=15.0, step=0.5,
        help="El colchon crece a este ritmo cada mes, pero NUNCA por encima de la inflacion (se aplica el minimo entre ambos)."
    ) / 100
    cushion_effective_return = min(cushion_desired_return, inflation_rate_ret)
    st.sidebar.caption(f"Rendimiento efectivo del Colchon: {cushion_effective_return*100:.2f}% anual (minimo entre deseado e inflacion)")

    st.sidebar.subheader("Guardrails (ajuste dinamico del gasto)")
    use_guardrails = st.sidebar.checkbox(
        "Activar guardrails de Guyton-Klinger", value=True,
        help="Ajusta el gasto anual si la tasa de retiro implicita se aleja demasiado de la inicial"
    )
    guardrail_band = st.sidebar.slider(
        "Banda de guardrail (%)", min_value=5, max_value=40, value=20, disabled=not use_guardrails,
        help="Si la tasa de retiro actual supera la inicial +banda%, se recorta el gasto; si cae por debajo de -banda%, se sube"
    ) / 100
    guardrail_adjustment = st.sidebar.slider(
        "Ajuste al activar guardrail (%)", min_value=5, max_value=25, value=10, disabled=not use_guardrails,
        help="Porcentaje de recorte o subida real del gasto anual cuando se dispara un guardrail"
    ) / 100

    if growth_choice == "MSCI World (historico ampliado desde 1997)":
        growth_series = download_single_series(HISTORICAL_INDEX_TICKER, "1996-01-01", "2026-07-05")
        growth_label = "MSCI World (indice historico)"
    elif growth_choice.startswith("[Estrategia] "):
        strategy_name = growth_choice.replace("[Estrategia] ", "")
        weights_pct = st.session_state.custom_strategies[strategy_name]
        assets_needed = list(weights_pct.keys())
        data_strategy = download_data({a: tickers[a] for a in assets_needed}, "2015-01-01", "2026-07-05")
        combined = pd.concat(data_strategy, axis=1).ffill().dropna()
        normalized = combined / combined.iloc[0]
        weights_frac = {a: w / 100 for a, w in weights_pct.items()}
        growth_series = sum(normalized[a] * weights_frac[a] for a in assets_needed) * initial_fund_value
        growth_series = growth_series / growth_series.iloc[0]
        growth_label = f"Estrategia '{strategy_name}' (sin rebalanceo, buy&hold para esta simulacion)"
    else:
        growth_series = download_single_series(tickers[growth_choice], "1996-01-01", "2026-07-05")
        growth_label = growth_choice

    st.info(
        f"Activo de crecimiento del Fondo: {growth_label} | "
        f"Colchon: {cushion_effective_return*100:.2f}% anual (capado a inflacion) | "
        f"Guardrails: {'activos' if use_guardrails else 'desactivados'}"
    )

    def simulate_withdrawal_mixed_monthly(
        growth_prices, start_year, end_year,
        initial_fund_value, annual_expenses, fund_withdrawal_positive,
        cushion_multiple, cushion_effective_return, inflation_rate,
        apply_tax, tax_rate, cost_basis_pct,
        skip_cola_on_down_year, use_guardrails, guardrail_band, guardrail_adjustment
    ):
        monthly_prices = growth_prices.resample('ME').last()
        min_year_available = monthly_prices.index.year.min()
        effective_start_year = max(start_year, min_year_available)

        monthly_prices = monthly_prices[
            (monthly_prices.index.year >= effective_start_year - 1) &
            (monthly_prices.index.year <= end_year)
        ]
        monthly_returns = monthly_prices.pct_change().dropna()
        trailing_12m_return = monthly_prices.pct_change(12).reindex(monthly_returns.index)

        monthly_infl = (1 + inflation_rate) ** (1 / 12) - 1
        monthly_cushion_rate = (1 + cushion_effective_return) ** (1 / 12) - 1

        fund_value = initial_fund_value
        current_annual_expenses = annual_expenses
        current_annual_fund_withdrawal = fund_withdrawal_positive
        initial_withdrawal_rate = fund_withdrawal_positive / initial_fund_value if initial_fund_value > 0 else 0

        cushion_max = cushion_multiple * current_annual_expenses
        cushion = cushion_max

        records = []
        months_elapsed = 0

        for dt, ret in monthly_returns.items():
            year = dt.year
            month = dt.month
            trend = trailing_12m_return.get(dt, None)
            market_bullish = (trend is not None) and (trend >= 0)

            fund_before = fund_value
            fund_value = fund_value * (1 + ret)
            fund_growth = fund_value - fund_before
            cushion = cushion * (1 + monthly_cushion_rate)

            monthly_fund_target = current_annual_fund_withdrawal / 12
            monthly_expenses_target = current_annual_expenses / 12

            tax_paid, cushion_refill, forced = 0, 0, False

            if market_bullish or trend is None:
                source = "Fondo"
                target = monthly_fund_target
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
                source = "Colchon"
                target = monthly_expenses_target
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

            months_elapsed += 1

            if months_elapsed > 1 and month == 1:
                freeze_cola = skip_cola_on_down_year and (trend is not None) and (trend < 0)
                if not freeze_cola:
                    current_annual_expenses *= (1 + inflation_rate)
                    current_annual_fund_withdrawal *= (1 + inflation_rate)

                if use_guardrails and fund_value > 0:
                    current_rate = current_annual_fund_withdrawal / fund_value
                    upper_bound = initial_withdrawal_rate * (1 + guardrail_band)
                    lower_bound = initial_withdrawal_rate * (1 - guardrail_band)
                    if current_rate > upper_bound:
                        current_annual_fund_withdrawal *= (1 - guardrail_adjustment)
                        current_annual_expenses *= (1 - guardrail_adjustment)
                    elif current_rate < lower_bound:
                        current_annual_fund_withdrawal *= (1 + guardrail_adjustment)
                        current_annual_expenses *= (1 + guardrail_adjustment)

                cushion_max = cushion_multiple * current_annual_expenses

            records.append({
                "Fecha": dt,
                "Ano": year,
                "Mes": month,
                "Rentabilidad Fondo (%)": round(ret * 100, 2),
                "Tendencia 12m": "Alcista" if market_bullish else ("Bajista" if trend is not None else "N/D"),
                "Fuente retiro": source if not forced else "Fondo (colchon agotado)",
                "Retiro del mes (EUR)": round(target, 2),
                "Impuestos del mes (EUR)": round(tax_paid, 2),
                "Recarga colchon (EUR)": round(cushion_refill, 2),
                "Gasto anual vigente (EUR)": round(current_annual_expenses, 2),
                "Retiro Fondo anual vigente (EUR)": round(current_annual_fund_withdrawal, 2),
                "Valor Fondo (EUR)": round(fund_value, 2),
                "Colchon (EUR)": round(cushion, 2),
                "Patrimonio Total (EUR)": round(fund_value + cushion, 2),
            })

        return pd.DataFrame(records), effective_start_year

    resultado_retiro, eff_year = simulate_withdrawal_mixed_monthly(
        growth_series,
        int(start_year_ret), int(end_year_ret),
        initial_fund_value, annual_expenses, fund_withdrawal_positive,
        cushion_multiple, cushion_effective_return, inflation_rate_ret,
        apply_tax, tax_rate, cost_basis_pct,
        skip_cola_on_down_year, use_guardrails, guardrail_band, guardrail_adjustment
    )

    if eff_year > start_year_ret:
        st.warning(f"El activo/estrategia elegido no tiene historico desde {start_year_ret}. La simulacion empieza en {eff_year} (primer mes con datos disponibles para ese activo de crecimiento).")

    st.subheader(f"Evolucion Mensual del Patrimonio ({eff_year}-{end_year_ret})")
    fig_ret = go.Figure()
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["Fecha"], y=resultado_retiro["Valor Fondo (EUR)"],
        name="Fondo", stackgroup="one", mode="lines"))
    fig_ret.add_trace(go.Scatter(x=resultado_retiro["Fecha"], y=resultado_retiro["Colchon (EUR)"],
        name=f"Colchon (capado a inflacion, {cushion_effective_return*100:.1f}%)", stackgroup="one", mode="lines"))
    fig_ret.update_layout(height=500, template="plotly_white",
        xaxis_title="Fecha", yaxis_title="Valor (EUR)")
    st.plotly_chart(fig_ret, use_container_width=True)

    agotado = resultado_retiro[resultado_retiro["Patrimonio Total (EUR)"] <= 0]
    if not agotado.empty:
        primera_fecha = agotado.iloc[0]["Fecha"]
        st.error(f"El patrimonio se agota en {primera_fecha.strftime('%m/%Y')}.")
    else:
        st.success(f"El patrimonio sobrevive todo el periodo. Valor final: {resultado_retiro.iloc[-1]['Patrimonio Total (EUR)']:,.2f} EUR")

    st.subheader("Resumen anual (agregado desde la simulacion mensual)")
    yearly_summary = resultado_retiro.groupby("Ano").agg(
        Retiro_Total_Fondo=("Retiro del mes (EUR)", lambda x: x[resultado_retiro.loc[x.index, "Fuente retiro"].str.contains("Fondo")].sum()),
        Retiro_Total_Colchon=("Retiro del mes (EUR)", lambda x: x[resultado_retiro.loc[x.index, "Fuente retiro"] == "Colchon"].sum()),
        Impuestos_Pagados=("Impuestos del mes (EUR)", "sum"),
        Recarga_Colchon=("Recarga colchon (EUR)", "sum"),
        Valor_Fondo_Fin_Ano=("Valor Fondo (EUR)", "last"),
        Colchon_Fin_Ano=("Colchon (EUR)", "last"),
        Patrimonio_Total_Fin_Ano=("Patrimonio Total (EUR)", "last"),
        Gasto_Anual_Vigente=("Gasto anual vigente (EUR)", "last"),
    ).reset_index()
    st.dataframe(yearly_summary, use_container_width=True)

    st.subheader("Detalle mes a mes")
    st.dataframe(resultado_retiro, use_container_width=True)

    total_taxes = resultado_retiro["Impuestos del mes (EUR)"].sum()
    months_from_fund = (resultado_retiro["Fuente retiro"].str.contains("Fondo")).sum()
    months_from_cushion = (resultado_retiro["Fuente retiro"] == "Colchon").sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total impuestos pagados", f"{total_taxes:,.0f} EUR")
    m2.metric("Meses retirando del Fondo", months_from_fund)
    m3.metric("Meses retirando del Colchon", months_from_cushion)

    csv = resultado_retiro.to_csv(index=False).encode('utf-8')
    st.download_button("Descargar simulacion mensual (CSV)", csv, "simulacion_retiro_mensual.csv", "text/csv")

    st.stop()

# ============================================================
# MODO ACUMULACION
# ============================================================

st.sidebar.subheader("Acceso rapido por ano")
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

initial_capital = st.sidebar.number_input("Capital inicial (EUR)", value=10000, min_value=1000)
monthly_contribution = st.sidebar.number_input(
    "Aportacion mensual (EUR)", value=0, min_value=0, step=50,
    help="Se anade el primer dia de cotizacion de cada mes"
)
rebalance_band = st.sidebar.slider(
    "Banda de rebalanceo relativa (%)", min_value=1, max_value=50, value=5,
    help="Ej: con un objetivo del 90% y banda del 5%, se rebalancea si el peso sale del rango 85.5%-94.5% (90% +/- 5% de 90%)"
) / 100
transaction_fee = st.sidebar.number_input(
    "Coste de transaccion (%)", value=0.10, min_value=0.0, max_value=5.0, step=0.05,
    help="Comision aplicada sobre cada compra, aportacion y rebalanceo (ej. 0.10% tipico en brokers de bajo coste)"
) / 100

data_dict = download_data(tickers, start_date, end_date)

if len(data_dict) < 2:
    st.error("No hay suficientes datos. Prueba con otras fechas.")
    st.stop()

data = pd.concat(data_dict, axis=1)
data = data.ffill()

available_assets = list(data.columns)

st.sidebar.header("Estrategias personalizadas")

if "custom_strategies" not in st.session_state:
    st.session_state.custom_strategies = load_strategies_from_disk()

with st.sidebar.expander("Crear nueva estrategia"):
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
        col1.write(f"{name}: {st.session_state.custom_strategies[name]}")
        if col2.button("Borrar", key=f"del_{name}"):
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
    prices_subset = data[assets_needed].dropna()
    if prices_subset.empty:
        st.warning(f"La estrategia '{name}' no tiene fechas con datos comunes para todos sus activos en este rango.")
        continue
    serie, contributed, reb_dates, weight_df, fees = simulate_custom_strategy(
        prices_subset, weights_pct, initial_capital, monthly_contribution, rebalance_band, transaction_fee
    )
    results[name] = serie
    total_contributed[name] = contributed
    rebalance_info[name] = len(reb_dates)
    fees_info[name] = fees
    weight_histories[name] = weight_df

portfolio_values = pd.DataFrame(results)

st.subheader(f"Evolucion de las Carteras ({start_date} a {end_date})")
fig = go.Figure()
for col in portfolio_values.columns:
    serie_plot = portfolio_values[col].dropna()
    fig.add_trace(go.Scatter(x=serie_plot.index, y=serie_plot.values, name=col))

fig.update_layout(height=650, template="plotly_white",
                  xaxis_title="Fecha", yaxis_title="Valor de la cartera")
st.plotly_chart(fig, use_container_width=True)

if weight_histories:
    st.subheader("Composicion de pesos en el tiempo (estrategias personalizadas)")
    strategy_to_plot = st.selectbox("Elige una estrategia para ver su evolucion de pesos", list(weight_histories.keys()))
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
            title=f"Evolucion de pesos - objetivo: {target_weights}"
        )
        st.plotly_chart(fig_weights, use_container_width=True)

st.subheader("Resultados finales")
summary_data = {}
for col in portfolio_values.columns:
    serie = portfolio_values[col].dropna()
    if serie.empty:
        continue
    cagr_val = cagr(serie)
    summary_data[col] = {
        "Valor final": round(serie.iloc[-1], 2),
        "Total aportado": round(total_contributed[col], 2),
        "Comisiones pagadas": round(fees_info.get(col, 0), 2),
        "Ganancia neta": round(serie.iloc[-1] - total_contributed[col], 2),
        "Rentabilidad Total (%)": round((serie.iloc[-1] / total_contributed[col] - 1) * 100, 2),
        "Rentabilidad Anualizada (%)": round(cagr_val, 2) if not pd.isna(cagr_val) else "Periodo muy corto",
        "Maximo Drawdown (%)": round(max_drawdown(serie), 2),
        "Numero Rebalanceos": rebalance_info.get(col, "-")
    }

summary = pd.DataFrame(summary_data).T
st.dataframe(summary)

st.success("App funcionando con tus tickers!")