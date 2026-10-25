"""
Real Exchange Rate Explorer
---------------------------
Streamlit app that pulls monthly CPI and exchange-rate data from the IMF
SDMX 3.0 API and computes the bilateral real exchange rate (RER).

Definitions
    S(t)      = units of Country 2 currency per 1 unit of Country 1 currency
    P1, P2    = monthly CPI of Country 1 and Country 2
    RER(t)    = S(t) * P1(t) / P2(t)
    RER*      = average RER(t) over valid months in the selected sample
    Index(t)  = 100 * RER(t) / RER*

IMF exchange rates are quoted as local currency per USD (XDC_USD), so
    S(t) = FX2(t) / FX1(t)   where FXi = Country i currency per USD.
"""

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
IMF_BASE = "https://api.imf.org/external/sdmx/3.0"
HEADERS = {"Accept": "application/json", "User-Agent": "rer-explorer/1.0"}
SAMPLE_START = pd.Period("1976-01", freq="M")
EURO_AREA = "G163"

CPI_KEY = "{iso}.CPI._T.IX.M"      # headline CPI index, monthly
HICP_KEY = "{iso}.HICP._T.IX.M"    # Euro area publishes HICP instead of CPI
FX_KEY = "{iso}.XDC_USD.PA_RT.M"   # local currency per USD, period average

# Colours
C_OVER = "#FF5A5F"     # overvalued (hot)
C_UNDER = "#3B82F6"    # undervalued (cold)
C_FAIR = "#10B981"     # near fair value
C_REAL = "#7C3AED"     # real index line
C_NOM = "#F59E0B"      # nominal S line
FAIR_BAND = 5.0        # +/- % around 100 treated as "fair-ish"

# ISO3 -> (display name, ISO2 for flag, currency code)
# Also serves as the fallback country list if the live IMF lookup fails.
COUNTRIES = {
    "ABW": ("Aruba", "aw", "AWG"), "AFG": ("Afghanistan", "af", "AFN"),
    "AGO": ("Angola", "ao", "AOA"), "ALB": ("Albania", "al", "ALL"),
    "ARE": ("United Arab Emirates", "ae", "AED"), "ARG": ("Argentina", "ar", "ARS"),
    "ARM": ("Armenia", "am", "AMD"), "ATG": ("Antigua and Barbuda", "ag", "XCD"),
    "AUS": ("Australia", "au", "AUD"), "AUT": ("Austria", "at", "EUR"),
    "AZE": ("Azerbaijan", "az", "AZN"), "BDI": ("Burundi", "bi", "BIF"),
    "BEL": ("Belgium", "be", "EUR"), "BEN": ("Benin", "bj", "XOF"),
    "BFA": ("Burkina Faso", "bf", "XOF"), "BGD": ("Bangladesh", "bd", "BDT"),
    "BGR": ("Bulgaria", "bg", "EUR"), "BHR": ("Bahrain", "bh", "BHD"),
    "BHS": ("Bahamas", "bs", "BSD"), "BIH": ("Bosnia and Herzegovina", "ba", "BAM"),
    "BLR": ("Belarus", "by", "BYN"), "BLZ": ("Belize", "bz", "BZD"),
    "BOL": ("Bolivia", "bo", "BOB"), "BRA": ("Brazil", "br", "BRL"),
    "BRB": ("Barbados", "bb", "BBD"), "BRN": ("Brunei Darussalam", "bn", "BND"),
    "BTN": ("Bhutan", "bt", "BTN"), "BWA": ("Botswana", "bw", "BWP"),
    "CAF": ("Central African Republic", "cf", "XAF"), "CAN": ("Canada", "ca", "CAD"),
    "CHE": ("Switzerland", "ch", "CHF"), "CHL": ("Chile", "cl", "CLP"),
    "CHN": ("China", "cn", "CNY"), "CIV": ("Côte d'Ivoire", "ci", "XOF"),
    "CMR": ("Cameroon", "cm", "XAF"), "COD": ("Congo, Dem. Rep.", "cd", "CDF"),
    "COG": ("Congo, Rep.", "cg", "XAF"), "COL": ("Colombia", "co", "COP"),
    "COM": ("Comoros", "km", "KMF"), "CPV": ("Cabo Verde", "cv", "CVE"),
    "CRI": ("Costa Rica", "cr", "CRC"), "CUW": ("Curaçao", "cw", "XCG"),
    "CYP": ("Cyprus", "cy", "EUR"), "CZE": ("Czech Republic", "cz", "CZK"),
    "DEU": ("Germany", "de", "EUR"), "DJI": ("Djibouti", "dj", "DJF"),
    "DMA": ("Dominica", "dm", "XCD"), "DNK": ("Denmark", "dk", "DKK"),
    "DOM": ("Dominican Republic", "do", "DOP"), "DZA": ("Algeria", "dz", "DZD"),
    "ECU": ("Ecuador", "ec", "USD"), "EGY": ("Egypt", "eg", "EGP"),
    "ESP": ("Spain", "es", "EUR"), "EST": ("Estonia", "ee", "EUR"),
    "ETH": ("Ethiopia", "et", "ETB"), "FIN": ("Finland", "fi", "EUR"),
    "FJI": ("Fiji", "fj", "FJD"), "FRA": ("France", "fr", "EUR"),
    "G163": ("Euro Area", "eu", "EUR"), "GAB": ("Gabon", "ga", "XAF"),
    "GBR": ("United Kingdom", "gb", "GBP"), "GEO": ("Georgia", "ge", "GEL"),
    "GHA": ("Ghana", "gh", "GHS"), "GIN": ("Guinea", "gn", "GNF"),
    "GLP": ("Guadeloupe", "gp", "EUR"), "GMB": ("Gambia", "gm", "GMD"),
    "GNB": ("Guinea-Bissau", "gw", "XOF"), "GNQ": ("Equatorial Guinea", "gq", "XAF"),
    "GRC": ("Greece", "gr", "EUR"), "GRD": ("Grenada", "gd", "XCD"),
    "GTM": ("Guatemala", "gt", "GTQ"), "GUY": ("Guyana", "gy", "GYD"),
    "HKG": ("Hong Kong SAR", "hk", "HKD"), "HND": ("Honduras", "hn", "HNL"),
    "HRV": ("Croatia", "hr", "EUR"), "HTI": ("Haiti", "ht", "HTG"),
    "HUN": ("Hungary", "hu", "HUF"), "IDN": ("Indonesia", "id", "IDR"),
    "IND": ("India", "in", "INR"), "IRL": ("Ireland", "ie", "EUR"),
    "IRN": ("Iran", "ir", "IRR"), "IRQ": ("Iraq", "iq", "IQD"),
    "ISL": ("Iceland", "is", "ISK"), "ISR": ("Israel", "il", "ILS"),
    "ITA": ("Italy", "it", "EUR"), "JAM": ("Jamaica", "jm", "JMD"),
    "JOR": ("Jordan", "jo", "JOD"), "JPN": ("Japan", "jp", "JPY"),
    "KAZ": ("Kazakhstan", "kz", "KZT"), "KEN": ("Kenya", "ke", "KES"),
    "KGZ": ("Kyrgyz Republic", "kg", "KGS"), "KHM": ("Cambodia", "kh", "KHR"),
    "KIR": ("Kiribati", "ki", "AUD"), "KNA": ("St. Kitts and Nevis", "kn", "XCD"),
    "KOR": ("Korea", "kr", "KRW"), "KOS": ("Kosovo", "xk", "EUR"),
    "KWT": ("Kuwait", "kw", "KWD"), "LAO": ("Lao PDR", "la", "LAK"),
    "LBN": ("Lebanon", "lb", "LBP"), "LBR": ("Liberia", "lr", "LRD"),
    "LBY": ("Libya", "ly", "LYD"), "LCA": ("St. Lucia", "lc", "XCD"),
    "LKA": ("Sri Lanka", "lk", "LKR"), "LSO": ("Lesotho", "ls", "LSL"),
    "LTU": ("Lithuania", "lt", "EUR"), "LUX": ("Luxembourg", "lu", "EUR"),
    "LVA": ("Latvia", "lv", "EUR"), "MAC": ("Macao SAR", "mo", "MOP"),
    "MAR": ("Morocco", "ma", "MAD"), "MDA": ("Moldova", "md", "MDL"),
    "MDG": ("Madagascar", "mg", "MGA"), "MDV": ("Maldives", "mv", "MVR"),
    "MEX": ("Mexico", "mx", "MXN"), "MKD": ("North Macedonia", "mk", "MKD"),
    "MLI": ("Mali", "ml", "XOF"), "MLT": ("Malta", "mt", "EUR"),
    "MMR": ("Myanmar", "mm", "MMK"), "MNE": ("Montenegro", "me", "EUR"),
    "MNG": ("Mongolia", "mn", "MNT"), "MOZ": ("Mozambique", "mz", "MZN"),
    "MRT": ("Mauritania", "mr", "MRU"), "MSR": ("Montserrat", "ms", "XCD"),
    "MTQ": ("Martinique", "mq", "EUR"), "MUS": ("Mauritius", "mu", "MUR"),
    "MWI": ("Malawi", "mw", "MWK"), "MYS": ("Malaysia", "my", "MYR"),
    "NAM": ("Namibia", "na", "NAD"), "NCL": ("New Caledonia", "nc", "XPF"),
    "NER": ("Niger", "ne", "XOF"), "NGA": ("Nigeria", "ng", "NGN"),
    "NIC": ("Nicaragua", "ni", "NIO"), "NLD": ("Netherlands", "nl", "EUR"),
    "NOR": ("Norway", "no", "NOK"), "NPL": ("Nepal", "np", "NPR"),
    "NRU": ("Nauru", "nr", "AUD"), "OMN": ("Oman", "om", "OMR"),
    "PAK": ("Pakistan", "pk", "PKR"), "PAN": ("Panama", "pa", "PAB"),
    "PER": ("Peru", "pe", "PEN"), "PHL": ("Philippines", "ph", "PHP"),
    "POL": ("Poland", "pl", "PLN"), "PRT": ("Portugal", "pt", "EUR"),
    "PRY": ("Paraguay", "py", "PYG"), "QAT": ("Qatar", "qa", "QAR"),
    "ROU": ("Romania", "ro", "RON"), "RUS": ("Russia", "ru", "RUB"),
    "RWA": ("Rwanda", "rw", "RWF"), "SAU": ("Saudi Arabia", "sa", "SAR"),
    "SDN": ("Sudan", "sd", "SDG"), "SEN": ("Senegal", "sn", "XOF"),
    "SGP": ("Singapore", "sg", "SGD"), "SLB": ("Solomon Islands", "sb", "SBD"),
    "SLE": ("Sierra Leone", "sl", "SLE"), "SLV": ("El Salvador", "sv", "USD"),
    "SMR": ("San Marino", "sm", "EUR"), "SOM": ("Somalia", "so", "SOS"),
    "SRB": ("Serbia", "rs", "RSD"), "SSD": ("South Sudan", "ss", "SSP"),
    "STP": ("São Tomé and Príncipe", "st", "STN"), "SUR": ("Suriname", "sr", "SRD"),
    "SVK": ("Slovak Republic", "sk", "EUR"), "SVN": ("Slovenia", "si", "EUR"),
    "SWE": ("Sweden", "se", "SEK"), "SWZ": ("Eswatini", "sz", "SZL"),
    "SXM": ("Sint Maarten", "sx", "XCG"), "SYC": ("Seychelles", "sc", "SCR"),
    "SYR": ("Syria", "sy", "SYP"), "TCD": ("Chad", "td", "XAF"),
    "TGO": ("Togo", "tg", "XOF"), "THA": ("Thailand", "th", "THB"),
    "TJK": ("Tajikistan", "tj", "TJS"), "TLS": ("Timor-Leste", "tl", "USD"),
    "TON": ("Tonga", "to", "TOP"), "TTO": ("Trinidad and Tobago", "tt", "TTD"),
    "TUN": ("Tunisia", "tn", "TND"), "TUR": ("Türkiye", "tr", "TRY"),
    "TZA": ("Tanzania", "tz", "TZS"), "UGA": ("Uganda", "ug", "UGX"),
    "UKR": ("Ukraine", "ua", "UAH"), "URY": ("Uruguay", "uy", "UYU"),
    "USA": ("United States", "us", "USD"), "UZB": ("Uzbekistan", "uz", "UZS"),
    "VCT": ("St. Vincent and the Grenadines", "vc", "XCD"), "VEN": ("Venezuela", "ve", "VES"),
    "VNM": ("Vietnam", "vn", "VND"), "WSM": ("Samoa", "ws", "WST"),
    "YEM": ("Yemen", "ye", "YER"), "ZAF": ("South Africa", "za", "ZAR"),
    "ZMB": ("Zambia", "zm", "ZMW"), "ZWE": ("Zimbabwe", "zw", "ZWG"),
}

# Euro members: IMF national FX series stop when the country adopts the euro.
# We splice: legacy currency / irrevocable conversion rate before adoption,
# Euro-area (G163) rate from adoption onward -> one continuous EUR series.
EURO_JOIN = {
    "AUT": ("1999-01", 13.7603), "BEL": ("1999-01", 40.3399),
    "FIN": ("1999-01", 5.94573), "FRA": ("1999-01", 6.55957),
    "DEU": ("1999-01", 1.95583), "IRL": ("1999-01", 0.787564),
    "ITA": ("1999-01", 1936.27), "LUX": ("1999-01", 40.3399),
    "NLD": ("1999-01", 2.20371), "PRT": ("1999-01", 200.482),
    "ESP": ("1999-01", 166.386), "GRC": ("2001-01", 340.750),
    "SVN": ("2007-01", 239.640), "CYP": ("2008-01", 0.585274),
    "MLT": ("2008-01", 0.429300), "SVK": ("2009-01", 30.1260),
    "EST": ("2011-01", 15.6466), "LVA": ("2014-01", 0.702804),
    "LTU": ("2015-01", 3.45280), "HRV": ("2023-01", 7.53450),
    "BGR": ("2026-01", 1.95583),
}

PRESETS = [
    ("GBR", "USA"), ("G163", "USA"), ("JPN", "USA"),
    ("CHN", "USA"), ("CHE", "G163"), ("MEX", "USA"),
]


# --------------------------------------------------------------------------
# IMF data access
# --------------------------------------------------------------------------
def _imf_get(flow, key, extra=None, retries=3):
    """GET one SDMX 3.0 data query. Returns parsed JSON or None if no data."""
    url = f"{IMF_BASE}/data/dataflow/IMF.STA/{flow}/+/{key}"
    params = {"dimensionAtObservation": "TIME_PERIOD", "attributes": "none",
              "measures": "OBS_VALUE"}
    if extra:
        params.update(extra)
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except (requests.RequestException, ValueError) as e:
            last_err = str(e)
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"IMF API request failed for {flow}/{key} ({last_err})")


def _periods(j):
    dims = j["data"]["structures"][0]["dimensions"].get("observation", [])
    if not dims:
        return []
    return [v.get("value", v.get("id")) for v in dims[0]["values"]]


def _parse_single_series(j):
    """Convert an SDMX-JSON response holding one series into a monthly pd.Series."""
    if not j:
        return pd.Series(dtype=float)
    series = j["data"]["dataSets"][0].get("series", {})
    if not series:
        return pd.Series(dtype=float)
    periods = _periods(j)
    obs = next(iter(series.values())).get("observations", {})
    vals = {}
    for idx, ob in obs.items():
        v = ob[0] if isinstance(ob, list) else ob
        try:
            vals[periods[int(idx)].replace("-M", "-")] = float(v)
        except (TypeError, ValueError, IndexError):
            continue
    if not vals:
        return pd.Series(dtype=float)
    s = pd.Series(vals)
    s.index = pd.PeriodIndex(s.index, freq="M")
    s = s[np.isfinite(s) & (s > 0)]
    return s.sort_index()


def _countries_with_series(flow, key):
    j = _imf_get(flow, key, {"lastNObservations": "1"})
    if not j:
        return set()
    codes = [v["id"] for v in j["data"]["structures"][0]["dimensions"]["series"][0]["values"]]
    series = j["data"]["dataSets"][0].get("series", {})
    return {codes[int(k.split(":")[0])] for k in series}


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def available_countries():
    """Live list of economies with monthly CPI (or HICP) and FX at the IMF."""
    try:
        cpi = _countries_with_series("CPI", CPI_KEY.format(iso="*"))
        cpi |= _countries_with_series("CPI", HICP_KEY.format(iso="*"))
        fx = _countries_with_series("ER", FX_KEY.format(iso="*"))
        codes = cpi & fx
        if len(codes) < 20:
            raise RuntimeError("unexpectedly short list")
        return sorted(codes, key=lambda c: (c != EURO_AREA, name(c))), True
    except Exception:
        return sorted(COUNTRIES, key=lambda c: (c != EURO_AREA, name(c))), False


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def fetch_cpi(iso):
    """Monthly CPI; falls back to HICP (used by the Euro area)."""
    for label, key in (("CPI", CPI_KEY), ("HICP", HICP_KEY)):
        s = _parse_single_series(_imf_get("CPI", key.format(iso=iso)))
        if not s.empty:
            return s, label
    return pd.Series(dtype=float), "n/a"


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def fetch_fx(iso):
    """Monthly local currency per USD; spliced into EUR for euro members."""
    nat = _parse_single_series(_imf_get("ER", FX_KEY.format(iso=iso)))
    if iso not in EURO_JOIN:
        return nat, False
    join, rate = EURO_JOIN[iso]
    join = pd.Period(join, freq="M")
    eur = _parse_single_series(_imf_get("ER", FX_KEY.format(iso=EURO_AREA)))
    spliced = pd.concat([nat[nat.index < join] / rate, eur[eur.index >= join]])
    return spliced.sort_index(), True


# --------------------------------------------------------------------------
# Calculations
# --------------------------------------------------------------------------
def name(iso):
    return COUNTRIES.get(iso, (iso, "", iso))[0]


def flag(iso):
    return COUNTRIES.get(iso, (iso, "", iso))[1]


def ccy(iso):
    return COUNTRIES.get(iso, (iso, "", iso))[2]


def build_panel(c1, c2):
    """Full monthly panel from Jan 1976: FX1, FX2, P1, P2, S, RER."""
    fx1, sp1 = fetch_fx(c1)
    fx2, sp2 = fetch_fx(c2)
    p1, l1 = fetch_cpi(c1)
    p2, l2 = fetch_cpi(c2)
    df = pd.DataFrame({"FX1": fx1, "FX2": fx2, "P1": p1, "P2": p2})
    df = df[df.index >= SAMPLE_START]
    if df.empty:
        return df, {}
    full = pd.period_range(df.index.min(), df.index.max(), freq="M")
    df = df.reindex(full)
    df["S"] = df["FX2"] / df["FX1"]
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    meta = {"cpi1": l1, "cpi2": l2, "splice1": sp1, "splice2": sp2}
    return df, meta


def apply_window(df, start, end):
    """Restrict to [start, end], compute RER*, Real Index and fair-value S."""
    w = df.loc[(df.index >= start) & (df.index <= end)].copy()
    w["Valid"] = w["RER"].notna()
    rer_star = w.loc[w["Valid"], "RER"].mean()
    w["RER_star"] = rer_star
    w["Real_Index"] = 100 * w["RER"] / rer_star
    w["Deviation_pct"] = w["Real_Index"] - 100
    # Nominal rate that would put the RER exactly at its sample average
    w["Fair_S"] = rer_star * w["P2"] / w["P1"]
    return w, rer_star


def fmt(x):
    if x is None or pd.isna(x):
        return "—"
    a = abs(x)
    if a >= 1000:
        return f"{x:,.0f}"
    if a >= 10:
        return f"{x:,.2f}"
    if a >= 0.01:
        return f"{x:.4f}"
    return f"{x:.3e}"


def mlabel(p):
    return pd.Period(p, freq="M").strftime("%b %Y")


def verdict(dev):
    if dev > FAIR_BAND:
        return "OVERVALUED", "🔥", C_OVER
    if dev < -FAIR_BAND:
        return "UNDERVALUED", "🧊", C_UNDER
    return "NEAR FAIR VALUE", "⚖️", C_FAIR


# --------------------------------------------------------------------------
# Styling
# --------------------------------------------------------------------------
st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="💱",
                   layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap');
h1, h2, h3, .hero h1, .verdict .big { font-family: 'Space Grotesk', sans-serif !important; }
.block-container { padding-top: 1.6rem; }
.hero {
  background: linear-gradient(120deg, #4F46E5 0%, #7C3AED 45%, #EC4899 100%);
  border-radius: 22px; padding: 26px 30px; color: #fff; margin-bottom: 18px;
  box-shadow: 0 12px 30px rgba(124,58,237,.30); position: relative; overflow: hidden;
}
.hero:after { content: "💱"; position: absolute; right: 24px; top: 6px;
  font-size: 110px; opacity: .14; }
.hero h1 { color: #fff; margin: 0 0 4px 0; font-size: 2.1rem; }
.hero p { margin: 0; opacity: .92; font-size: 1.02rem; }
.flags { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; flex-wrap: wrap; }
.flags img { height: 46px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,.30);
  border: 2px solid rgba(255,255,255,.85); }
.flags .pair { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.6rem; }
.flags .arrow { font-size: 1.6rem; opacity: .9; }
.verdict { border-radius: 20px; padding: 22px 24px; color: #fff; height: 100%;
  box-shadow: 0 10px 24px rgba(0,0,0,.18); }
.verdict .tag { display: inline-block; background: rgba(255,255,255,.22);
  padding: 4px 12px; border-radius: 999px; font-weight: 700; letter-spacing: .08em;
  font-size: .8rem; }
.verdict .big { font-size: 2.6rem; font-weight: 700; line-height: 1.1; margin: 10px 0 6px 0; }
.verdict .sub { font-size: 1.0rem; opacity: .95; line-height: 1.45; }
[class*="st-key-stat_"] { border-radius: 16px; padding: 14px 16px 4px 16px; gap: .2rem;
  border: 1px solid rgba(128,128,128,.25); background: rgba(124,58,237,.06); }
.tile .lab { font-size: .78rem; text-transform: uppercase; letter-spacing: .07em; opacity: .7; }
.tile .val { font-family: 'Space Grotesk', sans-serif; font-size: 1.45rem; font-weight: 700; }
.tile .note { font-size: .8rem; opacity: .7; }
.legend-chip { display: inline-block; padding: 2px 10px; border-radius: 999px; color: #fff;
  font-size: .8rem; font-weight: 600; margin-right: 6px; }
</style>
""",
    unsafe_allow_html=True,
)


def flag_img(iso):
    code = flag(iso)
    if not code:
        return '<span style="font-size:40px">🌐</span>'
    return f'<img src="https://flagcdn.com/w160/{code}.png" alt="{name(iso)} flag">'


def tile(label, value, note=""):
    st.markdown(
        f'<div class="tile"><div class="lab">{label}</div>'
        f'<div class="val">{value}</div><div class="note">{note}</div></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Sidebar controls
# --------------------------------------------------------------------------
codes, live_list = available_countries()
if "c1" not in st.session_state or st.session_state.c1 not in codes:
    st.session_state.c1 = "GBR" if "GBR" in codes else codes[0]
if "c2" not in st.session_state or st.session_state.c2 not in codes:
    st.session_state.c2 = "USA" if "USA" in codes else codes[1]


def _swap():
    st.session_state.c1, st.session_state.c2 = st.session_state.c2, st.session_state.c1


def _preset(a, b):
    st.session_state.c1, st.session_state.c2 = a, b


with st.sidebar:
    st.markdown("## 🌍 Pick your pair")
    label = lambda c: f"{name(c)} · {ccy(c)}"
    st.selectbox("Country 1 (base currency)", codes, key="c1", format_func=label)
    st.selectbox("Country 2 (quote currency)", codes, key="c2", format_func=label)
    st.button("🔄 Swap countries", on_click=_swap, width="stretch")

    st.markdown("**⚡ Quick pairs**")
    cols = st.columns(2)
    for i, (a, b) in enumerate(PRESETS):
        if a in codes and b in codes:
            cols[i % 2].button(f"{ccy(a)}/{ccy(b)}", key=f"preset_{a}_{b}",
                               on_click=_preset, args=(a, b), width="stretch")

    st.markdown("---")
    mode = st.radio("📈 Chart view", ["Real", "Nominal", "Both"], index=2,
                    horizontal=True)
    show_fair = st.toggle("Show fair-value nominal rate", value=True,
                          help="The S that would put the RER exactly at its sample average: RER* × P2 / P1")
    log_nom = st.toggle("Log scale for nominal S", value=False)
    if not live_list:
        st.caption("⚠️ Live IMF country list unavailable — using built-in list.")

c1, c2 = st.session_state.c1, st.session_state.c2
cur1, cur2 = ccy(c1), ccy(c2)

if c1 == c2:
    st.markdown(
        f'<div class="hero"><div class="flags">{flag_img(c1)}<span class="arrow">⇄</span>'
        f'{flag_img(c2)}</div><h1>Real Exchange Rate Explorer</h1>'
        f'<p>Pick two different countries to compare.</p></div>',
        unsafe_allow_html=True,
    )
    st.warning("Country 1 and Country 2 are the same — the RER would be 1 forever. Pick a different pair! 🙂")
    st.stop()

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
try:
    with st.spinner(f"Fetching CPI & FX for {name(c1)} and {name(c2)} from the IMF…"):
        panel, meta = build_panel(c1, c2)
except Exception as e:
    st.error(f"Couldn't download data from the IMF API.\n\n`{e}`")
    if st.button("🔁 Retry"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

valid_months = panel.index[panel["RER"].notna()] if not panel.empty else []
if len(valid_months) < 2:
    st.markdown(
        f'<div class="hero"><div class="flags">{flag_img(c1)}<span class="arrow">⇄</span>'
        f'{flag_img(c2)}</div><h1>Real Exchange Rate Explorer</h1>'
        f'<p>{name(c1)} vs {name(c2)}</p></div>',
        unsafe_allow_html=True,
    )
    st.error("Not enough overlapping monthly CPI and exchange-rate data at the IMF for this pair. Try another combination.")
    with st.expander("What data was found?"):
        st.write(panel[["FX1", "FX2", "P1", "P2"]].notna().sum().rename("months available") if not panel.empty else "No data returned.")
    st.stop()

month_opts = [str(p) for p in pd.period_range(valid_months.min(), valid_months.max(), freq="M")]
with st.sidebar:
    st.markdown("---")
    start_s, end_s = st.select_slider(
        "🗓️ Sample period (sets RER* average)", options=month_opts,
        value=(month_opts[0], month_opts[-1]), format_func=mlabel,
        key=f"win_{c1}_{c2}",
    )
start, end = pd.Period(start_s, freq="M"), pd.Period(end_s, freq="M")
win, rer_star = apply_window(panel, start, end)
vw = win[win["Valid"]]

if vw.empty:
    st.error("No valid months in this window — widen the sample period.")
    st.stop()

# --------------------------------------------------------------------------
# Hero
# --------------------------------------------------------------------------
st.markdown(
    f"""
<div class="hero">
  <div class="flags">{flag_img(c1)}<span class="pair">{cur1}</span>
    <span class="arrow">⇄</span>{flag_img(c2)}<span class="pair">{cur2}</span></div>
  <h1>Real Exchange Rate Explorer</h1>
  <p>{name(c1)} vs {name(c2)} · S = {cur2} per 1 {cur1} · sample {mlabel(start)} – {mlabel(end)}</p>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Verdict + gauge
# --------------------------------------------------------------------------
last_m = vw.index.max()
last = vw.loc[last_m]
dev = last["Deviation_pct"]
tag, emoji, color = verdict(dev)
grad = {C_OVER: "linear-gradient(135deg,#FF5A5F,#F97316)",
        C_UNDER: "linear-gradient(135deg,#3B82F6,#06B6D4)",
        C_FAIR: "linear-gradient(135deg,#10B981,#84CC16)"}[color]
direction = "stronger" if dev > 0 else "weaker"

v1, v2 = st.columns([1.35, 1])
with v1:
    st.markdown(
        f"""
<div class="verdict" style="background:{grad}">
  <span class="tag">{emoji} {tag}</span>
  <div class="big">{cur1} {dev:+.1f}%</div>
  <div class="sub">In <b>{mlabel(last_m)}</b>, the {name(c1)} {cur1} is <b>{abs(dev):.1f}% {direction}</b>
  in real terms against the {name(c2)} {cur2} than its {mlabel(start)}–{mlabel(end)} average.<br>
  Actual S: <b>{fmt(last['S'])} {cur2}</b> per {cur1} · Fair-value S: <b>{fmt(last['Fair_S'])} {cur2}</b></div>
</div>
""",
        unsafe_allow_html=True,
    )
with v2:
    idx_now = float(last["Real_Index"])
    lo = min(60.0, np.floor(vw["Real_Index"].min() / 10) * 10)
    hi = max(140.0, np.ceil(vw["Real_Index"].max() / 10) * 10)
    gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=idx_now,
        number={"suffix": "", "valueformat": ".1f"},
        delta={"reference": 100, "valueformat": ".1f",
               "increasing": {"color": C_OVER}, "decreasing": {"color": C_UNDER}},
        title={"text": "Real Index (100 = sample average)", "font": {"size": 14}},
        gauge={
            "axis": {"range": [lo, hi]},
            "bar": {"color": "#111827", "thickness": 0.25},
            "steps": [
                {"range": [lo, 100 - FAIR_BAND], "color": "rgba(59,130,246,.55)"},
                {"range": [100 - FAIR_BAND, 100 + FAIR_BAND], "color": "rgba(16,185,129,.55)"},
                {"range": [100 + FAIR_BAND, hi], "color": "rgba(255,90,95,.55)"},
            ],
            "threshold": {"line": {"color": "#111827", "width": 3}, "value": 100},
        },
    ))
    gauge.update_layout(height=230, margin=dict(l=25, r=25, t=50, b=10))
    st.plotly_chart(gauge, width="stretch", config={"displayModeBar": False})

# --------------------------------------------------------------------------
# Stat tiles
# --------------------------------------------------------------------------
peak_m, trough_m = vw["Real_Index"].idxmax(), vw["Real_Index"].idxmin()
share_over = (vw["Real_Index"] > 100).mean() * 100
yearly_over = (vw["Real_Index"] > 100).groupby(vw.index.year).mean() * 100
xs = win.index.to_timestamp()


def spark(traces, key, hline=None):
    """Mini history chart shown under each stat tile."""
    f = go.Figure(traces)
    if hline is not None:
        f.add_hline(y=hline, line=dict(color="#9CA3AF", dash="dot", width=1))
    f.update_layout(height=80, margin=dict(l=0, r=0, t=6, b=0), showlegend=False,
                    xaxis=dict(visible=False), yaxis=dict(visible=False),
                    hovermode="x unified")
    st.plotly_chart(f, width="stretch", config={"displayModeBar": False}, key=key)


def spark_line(y, color, hover):
    return go.Scatter(x=xs, y=y, mode="lines", line=dict(color=color, width=1.6),
                      hovertemplate=hover + "<extra></extra>")


def spark_zone(over):
    """Shaded band between 100 and the index, above (over=True) or below."""
    base = pd.Series(100.0, index=win.index)
    edge = (np.maximum(win["Real_Index"], 100) if over else np.minimum(win["Real_Index"], 100)).fillna(100)
    fill = "rgba(255,90,95,.35)" if over else "rgba(59,130,246,.35)"
    return [go.Scatter(x=xs, y=base, mode="lines", line=dict(width=0), hoverinfo="skip"),
            go.Scatter(x=xs, y=edge, mode="lines", line=dict(width=0), fill="tonexty",
                       fillcolor=fill, hoverinfo="skip")]


def spark_dot(m, y, col):
    return go.Scatter(x=[m.to_timestamp()], y=[y], mode="markers", marker=dict(size=7, color=col, line=dict(color="white", width=1.5)),
                      hoverinfo="skip")


t = st.columns(5)
with t[0], st.container(key="stat_s"):
    tile("Latest nominal S", f"{fmt(last['S'])}", f"{cur2} per {cur1} · {mlabel(last_m)}")
    spark([spark_line(win["S"], C_NOM, "%{x|%b %Y}: %{y:.4g}"),
           spark_dot(last_m, last["S"], C_NOM)], "spark_s")
with t[1], st.container(key="stat_star"):
    tile("RER* (sample avg)", fmt(rer_star), f"{len(vw)} valid months")
    spark([spark_line(win["RER"], C_REAL, "%{x|%b %Y}: RER %{y:.4g}")], "spark_star", hline=rer_star)
with t[2], st.container(key="stat_peak"):
    tile("🔥 Peak overvaluation", f"{vw.loc[peak_m, 'Deviation_pct']:+.1f}%", mlabel(peak_m))
    spark(spark_zone(True) + [spark_line(win["Real_Index"], C_REAL, "%{x|%b %Y}: %{y:.1f}"),
                              spark_dot(peak_m, vw.loc[peak_m, "Real_Index"], C_OVER)],
          "spark_peak", hline=100)
with t[3], st.container(key="stat_trough"):
    tile("🧊 Deepest undervaluation", f"{vw.loc[trough_m, 'Deviation_pct']:+.1f}%", mlabel(trough_m))
    spark(spark_zone(False) + [spark_line(win["Real_Index"], C_REAL, "%{x|%b %Y}: %{y:.1f}"),
                               spark_dot(trough_m, vw.loc[trough_m, "Real_Index"], C_UNDER)],
          "spark_trough", hline=100)
with t[4], st.container(key="stat_share"):
    tile("Time spent above 100", f"{share_over:.0f}%", "of valid months · by year below")
    spark([go.Bar(x=yearly_over.index, y=yearly_over.values,
                  marker_color=[C_OVER if v > 50 else C_UNDER for v in yearly_over.values],
                  hovertemplate="%{x}: %{y:.0f}% of months above 100<extra></extra>")],
          "spark_share", hline=50)

st.write("")

# --------------------------------------------------------------------------
# Main chart
# --------------------------------------------------------------------------
x = win.index.to_timestamp()
idx = win["Real_Index"]
fig = make_subplots(specs=[[{"secondary_y": mode == "Both"}]])


def add_real(fig):
    # Gaps are filled with 100 (zero-height band) so Plotly's tonexty fill stays aligned
    base = pd.Series(100.0, index=idx.index)
    over = np.maximum(idx, 100).fillna(100)
    under = np.minimum(idx, 100).fillna(100)
    for y_fill, col, nm in ((over, "rgba(255,90,95,.30)", "Overvalued zone"),
                            (under, "rgba(59,130,246,.30)", "Undervalued zone")):
        fig.add_trace(go.Scatter(x=x, y=base, mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False), secondary_y=False)
        fig.add_trace(go.Scatter(x=x, y=y_fill, mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=col, name=nm, showlegend=False,
                                 hoverinfo="skip"), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=x, y=idx, mode="lines", name="Real Index", line=dict(color=C_REAL, width=2.6),
        hovertemplate="%{x|%b %Y}<br>Real Index: %{y:.1f}<extra></extra>"),
        secondary_y=False)
    fig.add_hline(y=100, line=dict(color="#6B7280", dash="dot", width=1.5),
                  annotation_text="100 = average", annotation_position="top left")
    for m, sym, col in ((peak_m, "🔥", C_OVER), (trough_m, "🧊", C_UNDER)):
        fig.add_trace(go.Scatter(
            x=[m.to_timestamp()], y=[win.loc[m, "Real_Index"]], mode="markers+text",
            marker=dict(size=11, color=col, line=dict(color="white", width=2)),
            text=[sym], textposition="top center", textfont=dict(size=18),
            showlegend=False, hovertemplate=f"{mlabel(m)}<br>%{{y:.1f}}<extra></extra>"),
            secondary_y=False)


def add_nominal(fig, secondary):
    fig.add_trace(go.Scatter(
        x=x, y=win["S"], mode="lines", name=f"Nominal S ({cur2}/{cur1})",
        line=dict(color=C_NOM, width=2.2),
        hovertemplate="%{x|%b %Y}<br>S: %{y:.4g} " + f"{cur2} per {cur1}<extra></extra>"),
        secondary_y=secondary)
    if show_fair:
        fig.add_trace(go.Scatter(
            x=x, y=win["Fair_S"], mode="lines", name="Fair-value S (RER at avg)",
            line=dict(color="#9CA3AF", width=1.8, dash="dash"),
            hovertemplate="%{x|%b %Y}<br>Fair S: %{y:.4g}<extra></extra>"),
            secondary_y=secondary)


nom_axis_title = f"S: {cur2} per 1 {cur1}"
if mode == "Real":
    add_real(fig)
    fig.update_yaxes(title_text="Real Index (avg = 100)")
elif mode == "Nominal":
    add_nominal(fig, False)
    fig.update_yaxes(title_text=nom_axis_title, type="log" if log_nom else "linear")
else:
    add_real(fig)
    add_nominal(fig, True)
    fig.update_yaxes(title_text="Real Index (avg = 100)", secondary_y=False)
    fig.update_yaxes(title_text=nom_axis_title, secondary_y=True, showgrid=False,
                     type="log" if log_nom else "linear")

fig.update_layout(
    height=540, hovermode="x unified", margin=dict(l=10, r=10, t=90, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    title=dict(text=f"{'Real & nominal' if mode == 'Both' else mode} exchange rate · {cur1} vs {cur2}",
               font=dict(family="Space Grotesk", size=18)),
)
fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
st.plotly_chart(fig, width="stretch")

st.markdown(
    f'<span class="legend-chip" style="background:{C_OVER}">Above 100 🔥</span>'
    f"{cur1} is <b>overvalued</b> vs its average — {name(c1)} is pricey for {name(c2)} buyers. "
    f'&nbsp;&nbsp;<span class="legend-chip" style="background:{C_UNDER}">Below 100 🧊</span>'
    f"{cur1} is <b>undervalued</b> — {name(c1)} is a bargain.",
    unsafe_allow_html=True,
)
st.caption("Zooming the chart doesn't change RER*. Use the sample-period slider in the sidebar to re-base the average.")

# --------------------------------------------------------------------------
# Valuation calendar heatmap
# --------------------------------------------------------------------------
st.markdown("### 🗓️ Valuation calendar")
cal = win[["Deviation_pct"]].copy()
cal["Year"] = cal.index.year
cal["Month"] = cal.index.strftime("%b")
grid = cal.pivot_table(index="Year", columns="Month", values="Deviation_pct", aggfunc="mean")
month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
grid = grid.reindex(columns=month_order)
zmax = float(np.nanmax(np.abs(grid.values))) if grid.notna().any().any() else 1.0
heat = go.Figure(go.Heatmap(
    z=grid.values, x=month_order, y=grid.index.astype(str),
    colorscale=[[0, C_UNDER], [0.5, "#F3F4F6"], [1, C_OVER]], zmid=0, zmin=-zmax, zmax=zmax,
    colorbar=dict(title="% vs avg"), xgap=2, ygap=2,
    hovertemplate="%{x} %{y}<br>%{z:+.1f}% vs average<extra></extra>",
))
heat.update_layout(height=max(260, 17 * len(grid) + 90), margin=dict(l=10, r=10, t=10, b=10),
                   yaxis=dict(autorange="reversed", dtick=5 if len(grid) > 25 else 1))
st.plotly_chart(heat, width="stretch")

# --------------------------------------------------------------------------
# Data table, CSV, verification
# --------------------------------------------------------------------------
st.markdown("### 📦 Data & download")
out = pd.DataFrame({
    "Month": win.index.astype(str),
    f"FX1_{cur1}_per_USD": win["FX1"],
    f"FX2_{cur2}_per_USD": win["FX2"],
    f"S_{cur2}_per_{cur1}": win["S"],
    f"P1_{meta['cpi1']}_{c1}": win["P1"],
    f"P2_{meta['cpi2']}_{c2}": win["P2"],
    "RER": win["RER"],
    "Valid": win["Valid"],
    "RER_star": win["RER_star"],
    "Real_Index": win["Real_Index"],
    "Deviation_pct": win["Deviation_pct"],
    f"Fair_S_{cur2}_per_{cur1}": win["Fair_S"],
})
d1, d2 = st.columns([1, 2])
with d1:
    st.download_button(
        "⬇️ Download CSV (selected sample)",
        out.to_csv(index=False).encode("utf-8"),
        file_name=f"rer_{c1}_{c2}_{start.strftime('%Y%m')}_{end.strftime('%Y%m')}.csv",
        mime="text/csv", type="primary", width="stretch",
    )
with d2:
    st.caption(
        f"{len(win)} months in window · {len(vw)} valid · mean Real Index over valid months = "
        f"**{vw['Real_Index'].mean():.4f}**"
    )
with st.expander("👀 Peek at the data table"):
    st.dataframe(out, width="stretch", hide_index=True, height=360)

with st.expander("🧮 How it's calculated + check one month by hand"):
    st.latex(r"S_t=\frac{FX_{2,t}}{FX_{1,t}}\qquad RER_t=S_t\cdot\frac{P_{1,t}}{P_{2,t}}"
             r"\qquad RER^*=\frac{1}{N}\sum_{t\in\text{valid}}RER_t\qquad"
             r"\text{Index}_t=100\cdot\frac{RER_t}{RER^*}")
    st.markdown(
        f"- IMF FX series are **local currency per USD**, so S = FX2 / FX1 = {cur2} per 1 {cur1}.\n"
        f"- A rising RER means {name(c1)}'s goods are getting more expensive relative to {name(c2)}'s "
        f"(real appreciation of {cur1}).\n"
        f"- *Fair-value S* = RER* × P2 / P1 — the nominal rate at which the RER would equal its sample average."
    )
    vm = st.selectbox("Month to verify", [str(m) for m in vw.index][::-1], format_func=mlabel)
    r = win.loc[pd.Period(vm, freq="M")]
    st.markdown(
        f"""
| Step | Value |
|---|---|
| FX1 ({cur1} per USD) | {r['FX1']:.6f} |
| FX2 ({cur2} per USD) | {r['FX2']:.6f} |
| S = FX2 / FX1 | {r['FX2']:.6f} / {r['FX1']:.6f} = **{r['S']:.6f}** {cur2} per {cur1} |
| P1 ({meta['cpi1']}, {name(c1)}) | {r['P1']:.4f} |
| P2 ({meta['cpi2']}, {name(c2)}) | {r['P2']:.4f} |
| RER = S × P1 / P2 | {r['S']:.6f} × {r['P1']:.4f} / {r['P2']:.4f} = **{r['RER']:.6f}** |
| RER* (avg over {len(vw)} months) | {rer_star:.6f} |
| Real Index = 100 × RER / RER* | 100 × {r['RER']:.6f} / {rer_star:.6f} = **{r['Real_Index']:.4f}** |
"""
    )

# --------------------------------------------------------------------------
# Footer / data notes
# --------------------------------------------------------------------------
notes = [f"Source: IMF SDMX 3.0 API (`{IMF_BASE}`), dataflows IMF.STA/CPI and IMF.STA/ER, monthly, from Jan 1976 where available."]
for iso, lab in ((c1, meta["cpi1"]), (c2, meta["cpi2"])):
    if lab == "HICP":
        notes.append(f"{name(iso)} price index: HICP (the IMF does not publish a separate headline CPI series for it).")
for iso, sp in ((c1, meta["splice1"]), (c2, meta["splice2"])):
    if sp:
        j, rate = EURO_JOIN[iso]
        notes.append(f"{name(iso)} FX expressed in EUR throughout: legacy currency ÷ {rate} before {mlabel(j)}, Euro-area rate after.")
gaps = int((~win["Valid"]).sum())
if gaps:
    notes.append(f"{gaps} month(s) in the window lack CPI or FX data and are excluded from RER*.")
st.markdown("---")
st.caption("  \n".join(notes))
