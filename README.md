# 💱 Real Exchange Rate Explorer

An interactive Streamlit app that shows whether one currency is **overvalued 🔥 or undervalued 🧊** in real terms against another, using monthly CPI and exchange-rate data pulled live from the **IMF SDMX 3.0 API**.

## What it does

- Pick **Country 1** and **Country 2** from every IMF economy that has monthly CPI and exchange-rate data, plus the **Euro Area** (IMF code `G163`).
- Downloads monthly data from **January 1976** onward where available.
- Computes the bilateral real exchange rate and a Real Index rebased to the average of the sample period you select.
- Interactive Plotly charts: **Real**, **Nominal**, or **Both** (two y-axes).
- A valuation verdict card, a gauge, a peak/trough tracker and a year × month "valuation calendar" heatmap.
- A **CSV download** of every observation and calculation in the selected sample.
- A step-by-step **hand-verification table** for any month.

## Economics

| Symbol | Definition |
|---|---|
| `FX1`, `FX2` | IMF exchange rate, local currency per USD (`XDC_USD`), monthly average |
| `S(t)` | Units of Country 2 currency per 1 unit of Country 1 currency = `FX2 / FX1` |
| `P1(t)`, `P2(t)` | Monthly CPI of Country 1 and Country 2 |
| `RER(t)` | `S(t) × P1(t) / P2(t)` |
| `RER*` | Average of `RER(t)` over the valid months of the user-selected sample |
| `Real Index(t)` | `100 × RER(t) / RER*`. Recalculated whenever the dates change, so it averages 100 |
| `Fair_S(t)` | `RER* × P2(t) / P1(t)`, the nominal rate at which the RER would equal its sample average |

**How to read it:** Real Index > 100 means Country 1's currency is stronger in real terms than its sample average (overvalued). Below 100 means it is weaker (undervalued). Nominal `S(t)` is plotted in actual currency units and is not normalized.

## Data

- API: `https://api.imf.org/external/sdmx/3.0` (no API key required)
- CPI: dataflow `IMF.STA/CPI`, key `{ISO3}.CPI._T.IX.M`. The Euro Area publishes HICP instead, so the app falls back to `{ISO3}.HICP._T.IX.M`.
- Exchange rate: dataflow `IMF.STA/ER`, key `{ISO3}.XDC_USD.PA_RT.M`
- **Euro members:** the IMF national FX series stop when a country adopts the euro. The app expresses them in EUR throughout: the legacy currency is divided by the official irrevocable conversion rate before adoption, and the Euro-area rate is used after.
- Months missing either CPI or FX are kept in the CSV, flagged `Valid = False` and excluded from `RER*`.
- Responses are cached for 12 hours. The country list falls back to a built-in list if the live lookup fails.

## CSV columns

`Month, FX1_<CUR1>_per_USD, FX2_<CUR2>_per_USD, S_<CUR2>_per_<CUR1>, P1_<index>_<ISO3>, P2_<index>_<ISO3>, RER, Valid, RER_star, Real_Index, Deviation_pct, Fair_S_<CUR2>_per_<CUR1>`

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requires Python 3.12.

## Deploy on Streamlit Community Cloud

1. Put `app.py`, `requirements.txt` and `README.md` at the top level of a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), then **Create app → Yup, I have an app**.
3. Select the repo, branch `main` and file `app.py`. Under **Advanced settings**, choose **Python 3.12**. Leave Secrets empty.
4. Click **Deploy**.

## Credits

Data © International Monetary Fund. Flags from [flagcdn.com](https://flagcdn.com). Built with Streamlit and Plotly. Code written with Claude (Anthropic), model Claude Opus 5.5, October 2026.
# Real-exchange-rate-app
interactive app for historical Real Exchange Rate comparison on currency pairs to evaluate over/under valued status
