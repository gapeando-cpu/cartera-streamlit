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
                    close = close.iloc[:, 0]  # Asegura que sea una Serie 1-D
                data[name] = close
                st.success(f"✅ {name} cargado")
            else:
                st.warning(f"⚠️ Datos insuficientes para {name}")
        except Exception as e:
            st.warning(f"⚠️ Error descargando {name}: {e}")
    return data

data_dict = download_data(tickers, start_date, end_date)

if len(data_dict) < 2:
    st.error("No hay suficientes datos. Prueba con otras fechas.")
    st.stop()

# Crear DataFrame con alineación de fechas
data = pd.concat(data_dict, axis=1)
data = data.dropna(how='all')  # Eliminar filas completamente vacías
data = data.ffill().dropna()   # Rellenar huecos y quitar filas incompletas restantes

# Normalizar
normalized = (data / data.iloc[0]) * initial_capital

# Cartera 50/50 (solo si ambos activos están disponibles)
if "Momentum" in normalized.columns and "Quality" in normalized.columns:
    normalized["50/50 Momentum + Quality"] = 0.5 * normalized["Momentum"] + 0.5 * normalized["Quality"]

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
st.caption("Replicando la app del vídeo de Josean Paunero")
