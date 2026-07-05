import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("📈 Comparador de Carteras: MSCI World vs Momentum + Quality")

st.sidebar.header("Configuración")
start_date = st.sidebar.date_input("Fecha de inicio", datetime(2023, 1, 1))  # Empezamos más reciente
end_date = st.sidebar.date_input("Fecha de fin", datetime.today())
initial_capital = st.sidebar.number_input("Capital inicial (€)", value=10000, min_value=1000)

tickers = {
    "MSCI World (IWDA)": "IWDA.AS",
    "Momentum (IWMO)": "IWMO.AS",
    "Quality (IWQU)": "IWQU.AS"
}

@st.cache_data(ttl=3600)
def download_data(tickers_dict, start, end):
    data = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty and len(df) > 5:
                data[name] = df['Close']
                st.success(f"✅ {name} cargado correctamente")
            else:
                st.warning(f"⚠️ Pocos datos para {name}")
        except Exception as e:
            st.warning(f"⚠️ Error descargando {name}")
    return pd.DataFrame(data)

data = download_data(tickers, start_date, end_date)

if data.empty or len(data) < 10:
    st.error("No hay suficientes datos. Prueba cambiando las fechas (ej. desde 2023 o 2024).")
    st.stop()

# Normalizar solo columnas con datos
normalized = pd.DataFrame()
for col in data.columns:
    if not data[col].isnull().all():
        normalized[col] = (data[col] / data[col].dropna().iloc[0]) * initial_capital

if "Momentum (IWMO)" in normalized.columns and "Quality (IWQU)" in normalized.columns:
    normalized["50/50 Momentum + Quality"] = 0.5 * normalized["Momentum (IWMO)"] + 0.5 * normalized["Quality (IWQU)"]

st.subheader("Evolución de las Carteras")
fig = go.Figure()
for col in normalized.columns:
    fig.add_trace(go.Scatter(x=normalized.index, y=normalized[col], name=col))

fig.update_layout(height=650, template="plotly_white", 
                  xaxis_title="Fecha", yaxis_title="Valor de la cartera (€)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📊 Resultados finales")
returns = ((normalized.iloc[-1] / normalized.iloc[0]) - 1) * 100
st.dataframe(returns.round(2).to_frame(name="Rentabilidad Total (%)"))

st.success("¡App funcionando!")
st.caption("Datos vía Yahoo Finance • Tickes recomendados")
