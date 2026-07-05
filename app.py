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
    data = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False)['Adj Close']
            data[name] = df
        except:
            st.warning(f"No se pudieron descargar datos de {name} ({ticker})")
    return pd.DataFrame(data)

data = download_data(tickers, start_date, end_date)

if data.empty or len(data) < 5:
    st.error("No se pudieron descargar suficientes datos. Prueba con fechas más recientes o cambia los tickers.")
    st.stop()
else:
    # Normalizar
    normalized = (data / data.iloc[0]) * initial_capital
    normalized["50/50 Momentum+Quality"] = 0.5 * normalized.get("Momentum", 0) + 0.5 * normalized.get("Quality", 0)
    
    st.subheader("Evolución de las Carteras")
    fig = go.Figure()
    for col in normalized.columns:
        if col != "50/50 Momentum+Quality" or normalized[col].sum() > 0:
            fig.add_trace(go.Scatter(x=normalized.index, y=normalized[col], name=col))
    
    fig.update_layout(height=600, template="plotly_white", 
                     xaxis_title="Fecha", yaxis_title="Valor de la cartera (€)")
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Resultados finales")
    returns = ((normalized.iloc[-1] / normalized.iloc[0]) - 1) * 100
    st.dataframe(returns.round(2).to_frame(name="Rentabilidad Total (%)"))
    
    st.caption("Datos vía Yahoo Finance • Replicando app del vídeo")
