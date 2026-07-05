import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Comparador Carteras", layout="wide")
st.title("📈 Comparador de Carteras: MSCI World vs Momentum + Quality")

st.sidebar.header("Configuración")
start_date = st.sidebar.date_input("Fecha de inicio", datetime(2020, 1, 1))
end_date = st.sidebar.date_input("Fecha de fin", datetime.today())
initial_capital = st.sidebar.number_input("Capital inicial (€)", value=10000, min_value=1000)

tickers = {
    "MSCI World": "URTH",
    "Momentum": "MTUM",
    "Quality": "QUAL"
}

@st.cache_data
def download_data(tickers_dict, start, end):
    data = yf.download(list(tickers_dict.values()), start=start, end=end)['Adj Close']
    data.columns = list(tickers_dict.keys())
    return data

data = download_data(tickers, start_date, end_date)

if data.empty or len(data) < 2:
    st.error("No se pudieron descargar datos. Prueba cambiar las fechas.")
else:
    normalized = (data / data.iloc[0]) * initial_capital
    normalized["50/50 Momentum+Quality"] = 0.5 * normalized["Momentum"] + 0.5 * normalized["Quality"]
    
    st.subheader("Evolución de las Carteras")
    fig = go.Figure()
    for col in normalized.columns:
        fig.add_trace(go.Scatter(x=normalized.index, y=normalized[col], name=col))
    
    fig.update_layout(height=600, template="plotly_white", 
                     xaxis_title="Fecha", yaxis_title="Valor de la cartera (€)")
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Resultados finales")
    returns = ((normalized.iloc[-1] / normalized.iloc[0]) - 1) * 100
    st.dataframe(returns.round(2).to_frame(name="Rentabilidad Total (%)"))
    
    st.caption("Datos vía Yahoo Finance • Replicando app del vídeo de Josean Paunero")
