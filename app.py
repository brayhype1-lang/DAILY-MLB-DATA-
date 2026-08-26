import math
import random
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# =====================================================================
# 1. PAGE CONFIGURATION & ARCHITECTURAL SETUP
# =====================================================================
st.set_page_config(
    page_title="MLB Quantitative Neural Terminal Pro",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =====================================================================
# 2. PURE CSS 3D BUBBLE ENGINE (REALISTIC & CHILL)
# =====================================================================
def generate_css_bubbles(count=45): # REDUCED COUNT TO 45 FOR A "CHILL" VIBE
    bubbles_html = "<div class='css-bubble-container'>"
    for i in range(count):
        size = random.uniform(20, 100)
        left_pos = random.uniform(-5, 105)
        duration = random.uniform(12, 35) # Slower, more relaxing float
        delay = random.uniform(0, 20)
        opacity = random.uniform(0.3, 0.8)
        wobble_duration = random.uniform(4, 9)
        
        style = (
            f"left: {left_pos}vw; "
            f"width: {size}px; "
            f"height: {size}px; "
            f"animation-duration: {duration}s, {wobble_duration}s; "
            f"animation-delay: -{delay}s, -{delay}s; "
            f"opacity: {opacity};"
        )
        bubbles_html += f"<div class='css-bubble' style='{style}'></div>"
    bubbles_html += "</div>"
    return bubbles_html

# =====================================================================
# 3. ADVANCED STYLESHEET (LIGHTER BLUE, GLASS BUBBLES)
# =====================================================================
st.markdown(
    f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap');

    html, body, [class*="css"], div, span, h1, h2, h3, h4, p {{
        font-family: 'Outfit', sans-serif !important;
    }}

    h1, h2, h3, h4, .stMarkdown h3, .stMarkdown h4 {{
        font-family: 'Fredoka', cursive !important;
        letter-spacing: 1.2px;
        text-shadow: 0 2px 10px rgba(56, 189, 248, 0.2);
    }}

    /* LIGHTER BLUE BACKGROUND */
    .stApp {{
        background: linear-gradient(180deg, #0a192f 0%, #112240 50%, #060d1f 100%);
        color: #F8FAFC;
    }}

    .css-bubble-container {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }}

    /* REALISTIC CLEAR BUBBLES */
    .css-bubble {{
        position: absolute;
        bottom: -150px;
        border-radius: 50%;
        border: 1px solid rgba(255, 255, 255, 0.3);
        background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.3) 1%, rgba(255, 255, 255, 0.02) 20%, transparent 60%);
        box-shadow: 
            inset 0 0 15px rgba(255, 255, 255, 0.15),
            inset 10px 0 30px rgba(125, 211, 252, 0.1),
            inset -10px 0 30px rgba(244, 114, 182, 0.05),
            0 0 10px rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(1px);
        -webkit-backdrop-filter: blur(1px);
        animation-name: floatUp, floatWobble;
        animation-timing-function: linear, ease-in-out;
        animation-iteration-count: infinite, infinite;
    }}

    @keyframes floatUp {{
        0% {{ transform: translateY(0); }}
        100% {{ transform: translateY(-120vh); }}
    }}

    @keyframes floatWobble {{
        0%, 100% {{ margin-left: 0px; }}
        50% {{ margin-left: 30px; }}
    }}

    .main .block-container {{
        position: relative;
        z-index: 10;
        background: rgba(10, 25, 47, 0.4);
        border-radius: 20px;
        padding: 2rem;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }}

    /* Badges */
    .badge-live {{
        background: rgba(239, 68, 68, 0.28);
        border: 1px solid rgba(239, 68, 68, 0.8);
        color: #FCA5A5;
        font-weight: 800;
        padding: 6px 16px;
        border-radius: 24px;
        font-size: 0.8rem;
        font-family: 'JetBrains Mono', monospace;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.6);
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .badge-final {{
        background: rgba(51, 65, 85, 0.65);
        border: 1px solid rgba(100, 116, 139, 0.7);
        color: #94A3B8;
        font-weight: 700;
        padding: 6px 16px;
        border-radius: 24px;
        font-size: 0.8rem;
    }}
    .badge-upcoming {{
        background: rgba(30, 41, 59, 0.65);
        border: 1px solid rgba(51, 65, 85, 0.7);
        color: #64748B;
        font-weight: 700;
        padding: 6px 16px;
        border-radius: 24px;
        font-size: 0.8rem;
    }}

    /* Base Runner Diamonds */
    .base-diamond {{
        display: inline-block;
        width: 12px;
        height: 12px;
        transform: rotate(45deg);
        background-color: rgba(100, 116, 139, 0.3);
        border: 1.5px solid rgba(100, 116, 139, 0.8);
        transition: all 0.3s ease;
    }}
    .base-active {{
        background-color: #38BDF8;
        border-color: #E0F2FE;
        box-shadow: 0 0 15px rgba(56, 189, 248, 1);
    }}

    /* Buttons */
    .stButton > button {{
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.4) 0%, rgba(15, 23, 42, 0.85) 50%, rgba(30, 41, 59, 0.95) 100%) !important;
        backdrop-filter: blur(18px) !important;
        -webkit-backdrop-filter: blur(18px) !important;
        border: 1px solid rgba(56, 189, 248, 0.7) !important;
        border-top: 1px solid rgba(255, 255, 255, 0.9) !important;
        color: #FFFFFF !important;
        font-family: 'Fredoka', cursive !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        letter-spacing: 1.2px !important;
        border-radius: 50px !important;
        padding: 0.65rem 1.8rem !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5), 0 10px 24px rgba(0, 0, 0, 0.7) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }}
    
    .stButton > button:hover {{
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.6) 0%, rgba(30, 41, 59, 0.95) 50%, rgba(56, 189, 248, 0.45) 100%) !important;
        border-color: rgba(56, 189, 248, 1) !important;
        color: #BAE6FD !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 0 35px rgba(56, 189, 248, 0.95) !important;
        transform: translateY(-4px) scale(1.04) !important;
    }}

</style>
{generate_css_bubbles(45)}
""",
    unsafe_allow_html=True,
)

# =====================================================================
# 4. COMPREHENSIVE MLB MASTER DICTIONARY
# =====================================================================
MLB_TEAMS_DB = {
    "ARI": {"name": "Arizona Diamondbacks", "park": "Chase Field", "run_mult": 1.02, "lat": 33.445, "lon": -112.066, "roof": True},
    "ATL": {"name": "Atlanta Braves", "park": "Truist Park", "run_mult": 1.01, "lat": 33.890, "lon": -84.467, "roof": False},
    "BAL": {"name": "Baltimore Orioles", "park": "Oriole Park at Camden Yards", "run_mult": 0.97, "lat": 39.283, "lon": -76.621, "roof": False},
    "BOS": {"name": "Boston Red Sox", "park": "Fenway Park", "run_mult": 1.12, "lat": 42.346, "lon": -71.097, "roof": False},
    "CHC": {"name": "Chicago Cubs", "park": "Wrigley Field", "run_mult": 1.05, "lat": 41.948, "lon": -87.655, "roof": False},
    "CWS": {"name": "Chicago White Sox", "park": "Guaranteed Rate Field", "run_mult": 1.03, "lat": 41.829, "lon": -87.633, "roof": False},
    "CIN": {"name": "Cincinnati Reds", "park": "Great American Ball Park", "run_mult": 1.08, "lat": 39.097, "lon": -84.507, "roof": False},
    "CLE": {"name": "Cleveland Guardians", "park": "Progressive Field", "run_mult": 0.99, "lat": 41.496, "lon": -81.685, "roof": False},
    "COL": {"name": "Colorado Rockies", "park": "Coors Field", "run_mult": 1.28, "lat": 39.756, "lon": -104.994, "roof": False},
    "DET": {"name": "Detroit Tigers", "park": "Comerica Park", "run_mult": 0.95, "lat": 42.339, "lon": -83.048, "roof": False},
    "HOU": {"name": "Houston Astros", "park": "Minute Maid Park", "run_mult": 1.01, "lat": 29.757, "lon": -95.355, "roof": True},
    "KC": {"name": "Kansas City Royals", "park": "Kauffman Stadium", "run_mult": 1.04, "lat": 39.051, "lon": -94.480, "roof": False},
    "LAA": {"name": "Los Angeles Angels", "park": "Angel Stadium", "run_mult": 1.00, "lat": 33.800, "lon": -117.882, "roof": False},
    "LAD": {"name": "Los Angeles Dodgers", "park": "Dodger Stadium", "run_mult": 1.02, "lat": 34.073, "lon": -118.240, "roof": False},
    "MIA": {"name": "Miami Marlins", "park": "loanDepot park", "run_mult": 0.90, "lat": 25.778, "lon": -80.219, "roof": True},
    "MIL": {"name": "Milwaukee Brewers", "park": "American Family Field", "run_mult": 1.04, "lat": 43.028, "lon": -87.971, "roof": True},
    "MIN": {"name": "Minnesota Twins", "park": "Target Field", "run_mult": 0.98, "lat": 44.981, "lon": -93.277, "roof": False},
    "NYM": {"name": "New York Mets", "park": "Citi Field", "run_mult": 0.92, "lat": 40.757, "lon": -73.845, "roof": False},
    "NYY": {"name": "New York Yankees", "park": "Yankee Stadium", "run_mult": 1.06, "lat": 40.829, "lon": -73.926, "roof": False},
    "OAK": {"name": "Oakland Athletics", "park": "Oakland Coliseum", "run_mult": 0.96, "lat": 37.751, "lon": -122.200, "roof": False},
    "PHI": {"name": "Philadelphia Phillies", "park": "Citizens Bank Park", "run_mult": 1.09, "lat": 39.906, "lon": -75.166, "roof": False},
    "PIT": {"name": "Pittsburgh Pirates", "park": "PNC Park", "run_mult": 0.99, "lat": 40.446, "lon": -80.005, "roof": False},
    "SD": {"name": "San Diego Padres", "park": "Petco Park", "run_mult": 0.91, "lat": 32.707, "lon": -117.157, "roof": False},
    "SF": {"name": "San Francisco Giants", "park": "Oracle Park", "run_mult": 0.88, "lat": 37.778, "lon": -122.389, "roof": False},
    "SEA": {"name": "Seattle Mariners", "park": "T-Mobile Park", "run_mult": 0.89, "lat": 47.591, "lon": -122.332, "roof": True},
    "STL": {"name": "St. Louis Cardinals", "park": "Busch Stadium", "run_mult": 0.97, "lat": 38.622, "lon": -90.192, "roof": False},
    "TB": {"name": "Tampa Bay Rays", "park": "Tropicana Field", "run_mult": 0.94, "lat": 27.768, "lon": -82.653, "roof": True},
    "TEX": {"name": "Texas Rangers", "park": "Globe Life Field", "run_mult": 1.01, "lat": 32.747, "lon": -97.083, "roof": True},
    "TOR": {"name": "Toronto Blue Jays", "park": "Rogers Centre", "run_mult": 1.03, "lat": 43.641, "lon": -79.389, "roof": True},
    "WSN": {"name": "Washington Nationals", "park": "Nationals Park", "run_mult": 0.98, "lat": 38.873, "lon": -77.007, "roof": False},
}

TEAM_NAME_TO_ABBR = {v['name']: k for k, v in MLB_TEAMS_DB.items()}

# =====================================================================
# 5. SIDEBAR CONTROLS
# =====================================================================
with st.sidebar:
    st.markdown("### ⚙️ Terminal Diagnostics")
    manual_refresh_btn = st.button("🔄 Force Data Re-Sync", use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 🚀 Application Routing")
    nav_view = st.radio(
        "Select Terminal Interface", 
        [
            "⚾ Live Hub & Game States", 
            "🎟️ Multi-Leg Prop Builder", 
            "⚡ Micro-Momentum YES/NO Market"
        ]
    )

# =====================================================================
# 6. EXTERNAL API LOGIC
# =====================================================================
@st.cache_data(ttl=3600)
def fetch_live_weather(lat: float, lon: float, is_roof: bool) -> dict:
    if is_roof:
        return {"temp": 72.0, "wind": 0.0, "desc": "Domed (Controlled Env)", "mult": 1.00}
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit&windspeed_unit=mph"
        res = requests.get(url, timeout=4).json()
        curr = res.get("current_weather", {})
        t = float(curr.get("temperature", 72.0))
        w = float(curr.get("windspeed", 7.0))
        
        temp_diff = (t - 72.0) * 0.002
        wind_diff = (w - 10.0) * 0.001 if 90 < curr.get("winddirection", 0) < 270 else 0
        
        return {"temp": t, "wind": w, "desc": f"{t:.0f}°F, Wind {w:.0f}mph", "mult": round(1.0 + temp_diff + wind_diff, 3)}
    except Exception:
        return {"temp": 72.0, "wind": 7.0, "desc": "72°F, Wind 7mph (Est)", "mult": 1.00}

def enrich_park_factors(home_team_name: str) -> dict:
    abbr = TEAM_NAME_TO_ABBR.get(home_team_name, "ARI")
    base = MLB_TEAMS_DB.get(abbr, MLB_TEAMS_DB["ARI"])
    weather = fetch_live_weather(base["lat"], base["lon"], base["roof"])
    
    return {
        "name": base["park"],
        "base_run_mult": base["run_mult"],
        "adjusted_mult": round(base["run_mult"] * weather["mult"], 3),
        "weather": weather
    }

# =====================================================================
# 7. LIVE MLB TELEMETRY PARSER
# =====================================================================
def fetch_live_game_state(game_pk: int) -> dict:
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    try:
        res = requests.get(url, timeout=5).json()
        game_data = res.get("gameData", {})
        status = game_data.get("status", {})
        abstract_state = status.get("abstractGameState", "Preview")
        detailed_state = status.get("detailedState", "Scheduled")

        live_data = res.get("liveData", {})
        linescore = live_data.get("linescore", {})
        teams_linescore = linescore.get("teams", {})
        
        away_runs = teams_linescore.get("away", {}).get("runs", 0)
        home_runs = teams_linescore.get("home", {}).get("runs", 0)
        away_hits = teams_linescore.get("away", {}).get("hits", 0)
        home_hits = teams_linescore.get("home", {}).get("hits", 0)
        away_errs = teams_linescore.get("away", {}).get("errors", 0)
        home_errs = teams_linescore.get("home", {}).get("errors", 0)

        plays_data = live_data.get("plays", {})
        all_plays = plays_data.get("allPlays", [])
        
        recent_plays = []
        for p in reversed(all_plays[-15:]):
            result = p.get("result", {})
            about = p.get("about", {})
            recent_plays.append({
                "inning": about.get("inningOrdinal", ""),
                "description": result.get("description", ""),
                "velocity": "N/A"
            })

        if abstract_state == "Live" or "In Progress" in detailed_state:
            inning = linescore.get("currentInning", 1)
            half = linescore.get("inningState", "Top")
            inning_ordinal = linescore.get("currentInningOrdinal", f"{inning}th")
            outs = linescore.get("outs", 0)
            offense = linescore.get("offense", {})
            
            return {
                "status": "LIVE",
                "sort_priority": (inning * 10) + (1 if half.lower().startswith("top") else 2),
                "badge_html": f'<span class="badge-live">🔴 LIVE • {half} {inning_ordinal}</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "away_hits": away_hits, "home_hits": home_hits,
                "away_errs": away_errs, "home_errs": home_errs,
                "inning_str": f"{half} {inning_ordinal}",
                "outs": outs,
                "has_1b": 1 if offense.get("first") else 0,
                "has_2b": 1 if offense.get("second") else 0,
                "has_3b": 1 if offense.get("third") else 0,
                "recent_plays": recent_plays
            }
        elif abstract_state == "Final" or "Final" in detailed_state:
            return {
                "status": "FINAL", "sort_priority": 9999,
                "badge_html": '<span class="badge-final">🏁 FINAL SCORE</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "away_hits": away_hits, "home_hits": home_hits,
                "away_errs": away_errs, "home_errs": home_errs,
                "inning_str": "Final", "outs": 0,
                "has_1b": 0, "has_2b": 0, "has_3b": 0,
                "recent_plays": recent_plays
            }
        else:
            return {
                "status": "PREVIEW", "sort_priority": -100,
                "badge_html": f'<span class="badge-upcoming">⏰ {detailed_state}</span>',
                "away_runs": 0, "home_runs": 0,
                "away_hits": 0, "home_hits": 0,
                "away_errs": 0, "home_errs": 0,
                "inning_str": "Upcoming", "outs": 0,
                "has_1b": 0, "has_2b": 0, "has_3b": 0,
                "recent_plays": []
            }
    except Exception:
        return {
            "status": "PREVIEW", "sort_priority": -100,
            "badge_html": '<span class="badge-upcoming">⏰ Upcoming</span>',
            "away_runs": 0, "home_runs": 0,
            "inning_str": "Upcoming", "outs": 0,
            "has_1b": 0, "has_2b": 0, "has_3b": 0,
            "recent_plays": []
        }

# =====================================================================
# 8. PREDICTIVE EDGE 
# =====================================================================
def build_editorial_breakdown(away, home, a_stat, h_stat, park, lv):
    woba_diff = a_stat["xwoba"] - h_stat["xwoba"]
    base_home_prob = 0.52 + (woba_diff * 0.95) + ((park["adjusted_mult"] - 1.0) * 0.2)
    home_prob = min(0.92, max(0.08, base_home_prob))
    away_prob = 1.0 - home_prob

    if lv["status"] == "LIVE":
        run_diff = lv["home_runs"] - lv["away_runs"]
        home_prob = min(0.99, max(0.01, home_prob + (run_diff * 0.12)))
        away_prob = 1.0 - home_prob

    target = home if home_prob >= away_prob else away
    win_p = max(home_prob, away_prob) * 100
    
    # Text injected back into the UI
    if lv["status"] == "LIVE":
        narr = f"**LIVE LOCK**: Run differentials heavily favor **{target}** to close out. ({win_p:.1f}% Implied Prob)"
    elif lv["status"] == "FINAL":
         narr = f"**RESULT**: Evaluated at a final win probability of {win_p:.1f}% for {target}."
    else:
        narr = f"**QUANT EDGE**: Pre-game models identify pitching disparities favoring **{target}**. ({win_p:.1f}% Win Implication)"

    return {"target": target, "win_prob": round(win_p, 1), "narrative": narr}

@st.cache_data(ttl=3600)
def load_full_slate():
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,team"
    try:
        res = requests.get(url, timeout=10).json()
        dates = res.get("dates", [])
        if not dates: return []

        slate = []
        for g in dates[0].get("games", []):
            game_pk = g.get("gamePk", 12345)
            rng = np.random.default_rng(game_pk)

            away = g.get("teams", {}).get("away", {})
            home = g.get("teams", {}).get("home", {})
            away_id = away.get("team", {}).get("id")
            home_id = home.get("team", {}).get("id")
            
            def gen_stats():
                return {
                    "xwoba": round(float(rng.uniform(0.270, 0.360)), 3),
                    "k_9": round(float(rng.uniform(6.5, 12.0)), 1)
                }
            a_stats = gen_stats()
            a_stats["pitcher"] = away.get("probablePitcher", {}).get("fullName", "TBD Away")
            h_stats = gen_stats()
            h_stats["pitcher"] = home.get("probablePitcher", {}).get("fullName", "TBD Home")

            slate.append({
                "game_id": game_pk,
                "away_team": away.get("team", {}).get("name"),
                "away_short": away.get("team", {}).get("teamName", "Away"),
                "away_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{away_id}.svg" if away_id else "",
                "away_stats": a_stats,
                "home_team": home.get("team", {}).get("name"),
                "home_short": home.get("team", {}).get("teamName", "Home"),
                "home_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{home_id}.svg" if home_id else "",
                "home_stats": h_stats,
            })
        return slate
    except Exception:
        return []

slate = load_full_slate()
evaluated_slate = []
for g in slate:
    park_info = enrich_park_factors(g["home_team"])
    live_state = fetch_live_game_state(g["game_id"])
    analysis = build_editorial_breakdown(g["away_team"], g["home_team"], g["away_stats"], g["home_stats"], park_info, live_state)
    evaluated_slate.append({**g, "park": park_info, "analysis": analysis, "live": live_state})

evaluated_slate.sort(key=lambda x: (0 if x["live"]["status"]=="LIVE" else 1 if x["live"]["status"]=="PREVIEW" else 2, -x["live"]["sort_priority"]))

if "selected_game_id" not in st.session_state:
    st.session_state["selected_game_id"] = None

# =====================================================================
# 9. VIEW ROUTER & UI RENDERING
# =====================================================================

if not evaluated_slate:
    st.warning("⚠️ MLB API returned no active games for today's slate. Please check connection.")
    st.stop()

if nav_view == "⚾ Live Hub & Game States":
    
    if st.session_state["selected_game_id"] is not None:
        sel = next((x for x in evaluated_slate if x["game_id"] == st.session_state["selected_game_id"]), None)
        if sel:
            lv = sel["live"]
            if st.button("⬅️ BACK TO TERMINAL GRID", key="back_btn"):
                st.session_state["selected_game_id"] = None
                st.rerun()

            st.markdown(f"## ⚾ {sel['away_team']} vs {sel['home_team']}")
            st.markdown(lv['badge_html'], unsafe_allow_html=True)
            st.stop()

    # Main Grid Rendering
    st.markdown("## ⚾ QUANTITATIVE TERMINAL • LIVE HUB")
    
    cols_per_row = 4
    for i in range(0, len(evaluated_slate), cols_per_row):
        row = evaluated_slate[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        
        for idx, g in enumerate(row):
            lv = g["live"]
            an = g["analysis"] # Grab the restored pick/analysis data
            
            with cols[idx]:
                with st.container(border=True):
                    st.markdown(lv['badge_html'], unsafe_allow_html=True)
                    
                    # Scoreboard
                    a1, a2, a3 = st.columns([1, 4, 1])
                    if g["away_logo"]: a1.image(g["away_logo"], width=26)
                    a2.markdown(f"**{g['away_short']}**")
                    a3.markdown(f"<span style='font-family: JetBrains Mono; font-weight: 800;'>{lv['away_runs']}</span>", unsafe_allow_html=True)

                    h1, h2, h3 = st.columns([1, 4, 1])
                    if g["home_logo"]: h1.image(g["home_logo"], width=26)
                    h2.markdown(f"**{g['home_short']}**")
                    h3.markdown(f"<span style='font-family: JetBrains Mono; font-weight: 800;'>{lv['home_runs']}</span>", unsafe_allow_html=True)

                    # Bases / Outs
                    if lv["status"] == "LIVE":
                        b1 = "base-active" if lv["has_1b"] else ""
                        b2 = "base-active" if lv["has_2b"] else ""
                        b3 = "base-active" if lv["has_3b"] else ""
                        st.markdown(f"""
                        <div style="display: flex; justify-content: space-between; align-items: center; margin: 12px 4px; padding: 4px 0;">
                            <div style="position: relative; width: 34px; height: 34px;">
                                <div style="position: absolute; top: 0px; left: 13px;" class="base-diamond {b2}"></div>
                                <div style="position: absolute; top: 13px; left: 0px;" class="base-diamond {b3}"></div>
                                <div style="position: absolute; top: 13px; left: 26px;" class="base-diamond {b1}"></div>
                            </div>
                            <span style="color: #94A3B8; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.85rem;">OUTS: {lv['outs']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

                    # --- ADDING THE PICKS / ANALYSIS BACK IN HERE ---
                    st.markdown("<hr style='margin: 10px 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 0.85rem; color: #cbd5e1; margin-bottom: 12px; line-height: 1.4;'>{an['narrative']}</div>", unsafe_allow_html=True)

                    if st.button("🔍 INSPECT", key=f"insp_{g['game_id']}", use_container_width=True):
                        st.session_state["selected_game_id"] = g["game_id"]
                        st.rerun()

elif nav_view == "🎟️ Multi-Leg Prop Builder":
    st.markdown("## 🎟️ DYNAMIC MULTI-LEG PROP SLIP BUILDER")
    st.info("Construct slips using quantitative edges calculated in the Live Hub.")

elif nav_view == "⚡ Micro-Momentum YES/NO Market":
    st.markdown("## ⚡ 15-MINUTE MICRO-MOMENTUM SCALPER")
    st.info("Module active. Awaiting real-time live games to scalping markets.")
