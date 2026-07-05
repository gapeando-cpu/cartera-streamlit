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

# Tickers recomendados por ti (Europeos)
tickers = {
    "MSCI World (IWDA)": "IWDA.xd",   # iShares Core MSCI World
    "Momentum (IWMO)": "IWMOM.xd",     # MSCI World Momentum
    "Quality (IWQU)": "IWQU.xd"       # MSCI World Quality
}

@st.cache_data(ttl=3600)
def download_data(tickers_dict, start, end):
    data = {}
    for name, ticker in tickers_dict.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                data[name] = df['Close']
                st.success(f"✅ Datos cargados de {name}")
            else:
                st.warning(f"⚠️ Sin datos para {name} ({ticker})")
        except Exception:
            st.warning(f"⚠️ Error al descargar {name} ({ticker})")
    return pd.DataFrame(data)

data = download_data(tickers, start_date, end_date)

if data.empty or len(data) < 10:
    st.error("No se pudieron descargar suficientes datos. Prueba acortando el rango de fechas (ej. desde 2023).")
    st.stop()
else:
    normalized = (data / data.iloc[0]) * initial_capital
    
    # Cartera 50/50
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
    
    st.success("¡App funcionando con tus tickers!")
    st.caption("Datos de Yahoo Finance • Replicando la app del vídeo de Josean Paunero")
