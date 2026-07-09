import yfinance as yf
import pandas as pd

def descargar_msci_world(start="1996-01-01", end="2026-07-05"):
    """
    Usa el índice MSCI World real (^990100-USD-STRD), con histórico
    desde 1995, para poder simular desde 1997.
    """
    df = yf.download("^990100-USD-STRD", start=start, end=end, progress=False, auto_adjust=True)
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()

def simulate_fire_strategy(
    close_prices,
    start_year=1997,
    end_year=2026,
    initial_fund_value=300000,
    annual_expenses=15000,           # Gastos anuales reales (tú los defines)
    fund_withdrawal_positive=20000,  # Lo que retiras del FONDO en año positivo/plano (tú lo defines)
    cushion_multiple=3,              # Colchón = 3x gastos anuales
    inflation_rate=0.03,             # Sube gastos y colchón un 3% anual
    apply_tax=True,
    tax_rate=0.23,                   # Tipo medio aproximado IRPF sobre plusvalías (19%-28% en España)
    cost_basis_pct=0.5,              # % del importe vendido del fondo que es "coste" (resto es plusvalía)
):
    annual_prices = close_prices.resample('YE').last()
    annual_prices = annual_prices[(annual_prices.index.year >= start_year - 1) & (annual_prices.index.year <= end_year)]
    annual_returns = annual_prices.pct_change().dropna()

    fund_value = initial_fund_value
    current_expenses = annual_expenses
    current_fund_withdrawal_target = fund_withdrawal_positive
    cushion_max = cushion_multiple * current_expenses
    cushion = cushion_max  # Empieza lleno

    records = []
    prev_year_positive = True  # Año inicial de referencia

    for date, ret in annual_returns.items():
        year = date.year
        fund_before = fund_value
        fund_value = fund_value * (1 + ret)
        fund_growth = fund_value - fund_before

        tax_paid = 0
        cushion_refill = 0
        forced_from_fund = False
        source = "Fondo" if prev_year_positive else "Colchón"
        withdrawal_target = current_fund_withdrawal_target if prev_year_positive else current_expenses

        if source == "Fondo":
            gross_needed = withdrawal_target
            if apply_tax:
                taxable_gain = gross_needed * (1 - cost_basis_pct)
                tax_paid = taxable_gain * tax_rate
                gross_needed += tax_paid
            fund_value = max(0, fund_value - gross_needed)

            # Excedente de revalorización del fondo recarga el colchón vía TRASPASO
            # (fondo -> monetario, sin peaje fiscal en España, no es un reembolso a cuenta)
            surplus = fund_growth - gross_needed
            if surplus > 0 and cushion < cushion_max:
                cushion_refill = min(surplus, cushion_max - cushion)
                cushion += cushion_refill

        else:
            if cushion >= withdrawal_target:
                cushion -= withdrawal_target
                # Retiro desde el colchón (monetario -> cuenta): plusvalía ~0, impacto fiscal despreciable
            else:
                remaining = withdrawal_target - cushion
                cushion = 0
                forced_from_fund = True
                gross_needed = remaining
                if apply_tax:
                    taxable_gain = gross_needed * (1 - cost_basis_pct)
                    tax_paid = taxable_gain * tax_rate
                    gross_needed += tax_paid
                fund_value = max(0, fund_value - gross_needed)

        records.append({
            "Año": year,
            "Rentabilidad Fondo (%)": round(ret * 100, 2),
            "Año anterior": "Positivo/Plano" if prev_year_positive else "Negativo",
            "Fuente retiro": source if not forced_from_fund else "Fondo (colchón agotado)",
            "Retiro objetivo (€)": round(withdrawal_target, 2),
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

# --- Uso ---
close = descargar_msci_world()
resultado = simulate_fire_strategy(
    close,
    start_year=1997,
    end_year=2026,
    initial_fund_value=300000,   # Tu capital inicial en el fondo
    annual_expenses=15000,       # Tus gastos anuales reales
    fund_withdrawal_positive=20000,  # Lo que retiras del fondo en años buenos
    cushion_multiple=3,
    inflation_rate=0.03,
    apply_tax=True,
    tax_rate=0.23,
)
print(resultado)