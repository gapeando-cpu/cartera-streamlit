import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("📈 Comparador de Carteras Momentum + Quality")

st.sidebar.header("Configuración")
start_date = st.sidebar.date_input("Fecha de inicio", datetime(2023, 1, 1))
end_date = st.sidebar.date_input("Fecha de fin", datetime.today())
initial_capital = st.sidebar.number_input("Capital inicial (€)", value=10000, min_value=1000)
monthly_contribution = st.sidebar.number_input(
    "Aportación mensual (€)", value=0, min_value=0, step=50,
    help="Se añade el primer día de cotización de cada mes"
)

tickers = {
    "MSCI World": "IWDA.AS",
    "Momentum": "IWMO.L",
    "Quality": "IWQU.L"
}

@st.cache_data(ttl=3600)
def download_data(tickers_dict, start, end):
    data = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
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

# Cartera 50/50 (se calcula sobre precios, antes de simular aportaciones)
if "Momentum" in data.columns and "Quality" in data.columns:
    data["50/50 Momentum + Quality"] = 0.5 * data["Momentum"] + 0.5 * data["Quality"]

# --- Selector de series a mostrar en el gráfico ---
st.sidebar.header("Series a mostrar")
available_series = list(data.columns)
selected_series = [s for s in available_series if st.sidebar.checkbox(s, value=True)]

if not selected_series:
    st.warning("Selecciona al menos una serie para visualizar.")
    st.stop()

# --- Simulación con aportaciones mensuales al principio de cada mes ---
def simulate_portfolio(prices, initial_capital, monthly_contribution):
    prices = prices.dropna()
    units = initial_capital / prices.iloc[0]
    values = []
    contributed = initial_capital
    prev_period = (prices.index[0].year, prices.index[0].month)
    for i, date in enumerate(prices.index):
        current_period = (date.year, date.month)
        if i > 0 and current_period != prev_period and monthly_contribution > 0:
            units += monthly_contribution / prices.iloc[i]
            contributed += monthly_contribution
            prev_period = current_period
        values.append(units * prices.iloc[i])
    return pd.Series(values, index=prices.index), contributed

results = {}
total_contributed = {}
for col in selected_series:
    serie, contributed = simulate_portfolio(data[col], initial_capital, monthly_contribution)
    results[col] = serie
    total_contributed[col] = contributed

portfolio_values = pd.DataFrame(results)

st.subheader("Evolución de las Carteras")
fig = go.Figure()
for col in portfolio_values.columns:
    fig.add_trace(go.Scatter(x=portfolio_values.index, y=portfolio_values[col], name=col))

fig.update_layout(height=650, template="plotly_white",
                  xaxis_title="Fecha", yaxis_title="Valor de la cartera (€)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📊 Resultados finales")
summary = pd.DataFrame({
    "Valor final (€)": portfolio_values.iloc[-1].round(2),
    "Total aportado (€)": pd.Series(total_contributed).round(2),
})
summary["Ganancia (€)"] = (summary["Valor final (€)"] - summary["Total aportado (€)"]).round(2)
summary["Rentabilidad Total (%)"] = (
    (summary["Valor final (€)"] / summary["Total aportado (€)"] - 1) * 100
).round(2)

st.dataframe(summary)

st.success("¡App funcionando con tus tickers!")
st.caption("Replicando la app del vídeo de Josean Paunero")
