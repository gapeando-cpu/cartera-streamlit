import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("📈 Comparador de Carteras: MSCI World vs Momentum + Quality")

st.sidebar.header("Configuración")
start_date = st.sidebar.date_input("Fecha de inicio", datetime(2023, 1, 1))
end_date = st.sidebar.date_input("Fecha de fin", datetime.today())
initial_capital = st.sidebar.number_input("Capital inicial (€)", value=10000, min_value=1000)

tickers = {
    "MSCI World (IWDA)": "IWDA.AS",
    "Momentum (IWMO)": "IWMO.mi",
    "Quality (IWQU)": "IWQU.mi"
}

@st.cache_data(ttl=3600)
def download_data(tickers_dict, start, end):
    data_dict = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty and len(df) > 5:
                series = df['Close']
                data_dict[name] = series
                st.success(f"✅ {name} cargado")
            else:
                st.warning(f"⚠️ Datos insuficientes para {name}")
        except:
            st.warning(f"⚠️ Error al descargar {name}")
    return data_dict

data_dict = download_data(tickers, start_date, end_date)

if len(data_dict) == 0:
    st.error("No se descargó ningún ticker.")
    st.stop()

# Crear DataFrame alineando fechas
data = pd.DataFrame(data_dict)

if data.empty:
    st.error("No hay datos válidos.")
    st.stop()

# Normalizar
normalized = pd.DataFrame(index=data.index)
for col in data.columns:
    col_data = data[col].dropna()
    if not col_data.empty:
        first_valid = col_data.iloc[0]
        normalized[col] = (data[col] / first_valid) * initial_capital

# Cartera 50/50
if "Momentum (IWMO)" in normalized.columns and "Quality (IWQU)" in normalized.columns:
    normalized["50/50 Momentum + Quality"] = (
        0.5 * normalized["Momentum (IWMO)"] + 0.5 * normalized["Quality (IWQU)"]
    )

st.subheader("Evolución de las Carteras")
fig = go.Figure()
for col in normalized.columns:
    fig.add_trace(go.Scatter(x=normalized.index, y=normalized[col], name=col))

fig.update_layout(height=650, template="plotly_white", 
                  xaxis_title="Fecha", yaxis_title="Valor (€)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📊 Resultados finales")
returns = ((normalized.iloc[-1] / normalized.iloc[0]) - 1) * 100
st.dataframe(returns.round(2).to_frame(name="Rentabilidad Total (%)"))

st.success("¡App lista!")
st.caption("Datos de Yahoo Finance")
