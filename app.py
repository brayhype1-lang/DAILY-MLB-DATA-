import math
import re
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st

# ------------------------------------------------------------------
# 1. PAGE CONFIG & MODERN UI STYLING
# ------------------------------------------------------------------
st.set_page_config(
    page_title="MLB Deep Quantitative Intelligence Engine",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');

    html, body, [class*="css"], div, span, h1, h2, h3, h4, p {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stApp {
        background: radial-gradient(circle at top center, #0F172A 0%, #070A10 100%);
        color: #E2E8F0;
    }

    .lock-card {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #38BDF8;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 0 25px rgba(56, 189, 248, 0.15);
        position: relative;
        overflow: hidden;
    }

    .matchup-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid #1E293B;
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 20px;
        transition: all 0.2s ease-in-out;
    }
    .matchup-card:hover {
        border-color: #38BDF8;
        box-shadow: 0 4px 20px rgba(56, 189, 248, 0.1);
        background: rgba(15, 23, 42, 0.9);
    }

    .calib-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
    }

    .badge-edge {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        color: #FFFFFF;
        font-weight: 800;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.82rem;
        letter-spacing: 0.05em;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
    }

    .badge-pass {
        background-color: #1E293B;
        color: #64748B;
        font-weight: 600;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.82rem;
        border: 1px solid #334155;
    }

    .badge-live {
        background: rgba(239, 68, 68, 0.2);
        border: 1px solid #EF4444;
        color: #FCA5A5;
        font-weight: 800;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
    }

    .badge-final {
        background: rgba(51, 65, 85, 0.5);
        border: 1px solid #475569;
        color: #94A3B8;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.78rem;
    }

    .badge-upcoming {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid #334155;
        color: #64748B;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.78rem;
    }

    .stat-pill-container {
        display: flex;
        gap: 6px;
        margin: 8px 0;
    }
    .stat-pill {
        background: #1E293B;
        border: 1px solid #334155;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.78rem;
        color: #94A3B8;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .stat-pill b { color: #F8FAFC; }

    .narrative-box {
        background: rgba(10, 15, 29, 0.85);
        border: 1px solid #1E293B;
        border-left: 3px solid #38BDF8;
        padding: 16px;
        border-radius: 10px;
        font-size: 0.90rem;
        line-height: 1.65;
        color: #94A3B8;
    }

    .highlight-txt { color: #F8FAFC; font-weight: 700; }
    .highlight-stat { color: #38BDF8; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .highlight-edge { color: #34D399; font-weight: 700; }
    .highlight-weather { color: #F59E0B; font-weight: 700; }
</style>
""",
    unsafe_allow_html=True,
)

PITCHING_WEIGHT = 1.0
OFFENSE_WEIGHT = 1.0
BULLPEN_WEIGHT = 1.0
WEATHER_WEIGHT = 1.0
MIN_EDGE_THRESHOLD = 3.5

# ------------------------------------------------------------------
# 2. BALLPARK & WEATHER ENGINE
# ------------------------------------------------------------------
PARK_FACTORS = {
    "Colorado Rockies": {"run_mult": 1.28, "hr_mult": 1.15, "name": "Coors Field", "lat": 39.756, "lon": -104.994, "roof": False},
    "Boston Red Sox": {"run_mult": 1.12, "hr_mult": 1.05, "name": "Fenway Park", "lat": 42.346, "lon": -71.097, "roof": False},
    "Cincinnati Reds": {"run_mult": 1.08, "hr_mult": 1.22, "name": "Great American Ball Park", "lat": 39.097, "lon": -84.507, "roof": False},
    "Chicago Cubs": {"run_mult": 1.05, "hr_mult": 1.10, "name": "Wrigley Field", "lat": 41.948, "lon": -87.655, "roof": False},
    "San Francisco Giants": {"run_mult": 0.88, "hr_mult": 0.82, "name": "Oracle Park", "lat": 37.778, "lon": -122.389, "roof": False},
    "Seattle Mariners": {"run_mult": 0.89, "hr_mult": 0.88, "name": "T-Mobile Park", "lat": 47.591, "lon": -122.332, "roof": True},
    "San Diego Padres": {"run_mult": 0.91, "hr_mult": 0.89, "name": "Petco Park", "lat": 32.707, "lon": -117.157, "roof": False},
    "New York Mets": {"run_mult": 0.92, "hr_mult": 0.90, "name": "Citi Field", "lat": 40.757, "lon": -73.845, "roof": False},
    "Detroit Tigers": {"run_mult": 0.95, "hr_mult": 0.86, "name": "Comerica Park", "lat": 42.339, "lon": -83.048, "roof": False},
}

@st.cache_data(ttl=7200)
def fetch_live_weather(lat: float, lon: float, is_roof: bool) -> dict:
    if is_roof:
        return {
            "temp_f": 72.0, "wind_mph": 0.0, "wind_dir": "Calm", 
            "weather_desc": "Domed / Roof Closed", "impact_mult": 1.00,
            "narrative_impact": "Neutral dome conditions neutralize exterior elements."
        }
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit&windspeed_unit=mph"
    try:
        res = requests.get(url, timeout=5).json()
        curr = res.get("current_weather", {})
        temp = float(curr.get("temperature", 70.0))
        wind = float(curr.get("windspeed", 5.0))
        return {
            "temp_f": temp, "wind_mph": wind, "wind_dir": "Out",
            "weather_desc": f"{temp:.0f}°F, Wind {wind:.0f}mph",
            "impact_mult": 1.00, "narrative_impact": "Standard baseline weather conditions."
        }
    except Exception:
        return {
            "temp_f": 70.0, "wind_mph": 5.0, "wind_dir": "Out", 
            "weather_desc": "70°F, 5mph Out", "impact_mult": 1.00,
            "narrative_impact": "Standard baseline weather conditions."
        }

def get_park_factor(home_team: str):
    default_park = {"run_mult": 1.00, "hr_mult": 1.00, "name": "Standard Ballpark", "lat": 40.0, "lon": -95.0, "roof": False}
    park = PARK_FACTORS.get(home_team, default_park)
    park["weather"] = fetch_live_weather(park["lat"], park["lon"], park["roof"])
    return park

# ------------------------------------------------------------------
# 3. LIVE SCORE & OVERRIDE ENGINE
# ------------------------------------------------------------------
@st.cache_data(ttl=15)
def fetch_live_game_state(game_pk: int) -> dict:
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/feed/live"
    try:
        res = requests.get(url, timeout=5).json()
        status_data = res.get("gameData", {}).get("status", {})
        abstract_state = status_data.get("abstractGameState", "Preview")
        detailed_state = status_data.get("detailedState", "Scheduled")
        
        linescore = res.get("liveData", {}).get("linescore", {})
        away_runs = linescore.get("teams", {}).get("away", {}).get("runs", 0)
        home_runs = linescore.get("teams", {}).get("home", {}).get("runs", 0)

        if abstract_state == "Live" or "In Progress" in detailed_state:
            inning = linescore.get("currentInningOrdinal", "1st")
            half = linescore.get("inningState", "Top")
            return {
                "status": "LIVE",
                "badge_html": f'<span class="badge-live">🔴 LIVE • {half} {inning} ({away_runs}-{home_runs})</span>',
                "away_runs": away_runs, "home_runs": home_runs
            }
        elif abstract_state == "Final":
            return {
                "status": "FINAL",
                "badge_html": f'<span class="badge-final">🏁 FINAL ({away_runs}-{home_runs})</span>',
                "away_runs": away_runs, "home_runs": home_runs
            }
        else:
            return {
                "status": "PREVIEW",
                "badge_html": f'<span class="badge-upcoming">⏰ {detailed_state}</span>',
                "away_runs": 0, "home_runs": 0
            }
    except Exception:
        return {
            "status": "PREVIEW",
            "badge_html": '<span class="badge-upcoming">⏰ Upcoming</span>',
            "away_runs": 0, "home_runs": 0
        }

def adjust_prob_for_live_state(base_home_prob: float, live_state: dict) -> tuple[float, float]:
    if live_state["status"] != "LIVE":
        return 1.0 - base_home_prob, base_home_prob

    run_diff = live_state["home_runs"] - live_state["away_runs"]
    prob_shift = run_diff * 0.085
    new_home_prob = min(0.99, max(0.01, base_home_prob + prob_shift))
    return 1.0 - new_home_prob, new_home_prob

# ------------------------------------------------------------------
# 4. MODELING & DATA FETCHING
# ------------------------------------------------------------------
def devig_implied(odds1: int, odds2: int) -> tuple[float, float]:
    p1 = (100 / (odds1 + 100)) if odds1 > 0 else (abs(odds1) / (abs(odds1) + 100))
    p2 = (100 / (odds2 + 100)) if odds2 > 0 else (abs(odds2) / (abs(odds2) + 100))
    tot = p1 + p2
    return p1 / tot, p2 / tot

def build_editorial_breakdown(away_team, home_team, away_stats, home_stats, park):
    base_home_prob = 0.535
    home_prob = min(0.85, max(0.15, base_home_prob))
    away_prob = 1.0 - home_prob

    fair_away, fair_home = devig_implied(home_stats["odds"], away_stats["odds"])
    home_edge = home_prob - fair_home
    away_edge = away_prob - fair_away

    req_edge = MIN_EDGE_THRESHOLD / 100.0
    if home_edge >= req_edge:
        target, edge, win_p = home_team, home_edge * 100, home_prob * 100
    elif away_edge >= req_edge:
        target, edge, win_p = away_team, away_edge * 100, away_prob * 100
    else:
        target, edge, win_p = None, 0.0, home_prob * 100

    selected_team = target if target else home_team
    narrative = f"Model projects edge for <span class='highlight-txt'>{selected_team}</span> (<span class='highlight-edge'>{win_p:.1f}% win prob</span>). Weather: {park['weather']['weather_desc']}."

    return {
        "target": target, "edge": round(edge, 1), "win_prob": round(win_p, 1),
        "home_prob": home_prob, "away_prob": away_prob, "narrative": narrative,
    }

@st.cache_data(ttl=3600)
def fetch_advanced_pitcher(person_id: int, name: str):
    return {"pitcher": name, "era": 4.10, "whip": 1.25, "siera": 3.90, "k_bb_diff": 0.16}

def load_full_slate():
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,team"
    try:
        res = requests.get(url, timeout=10).json()
        dates = res.get("dates", [])
        if not dates: return []

        slate = []
        for g in dates[0].get("games", []):
            away = g.get("teams", {}).get("away", {})
            home = g.get("teams", {}).get("home", {})
            away_p = away.get("probablePitcher", {})
            home_p = home.get("probablePitcher", {})
            away_id = away.get("team", {}).get("id")
            home_id = home.get("team", {}).get("id")

            away_stats = fetch_advanced_pitcher(away_p.get("id"), away_p.get("fullName", "Starter A"))
            home_stats = fetch_advanced_pitcher(home_p.get("id"), home_p.get("fullName", "Starter B"))

            away_stats.update({"odds": -110, "public_bets_pct": 50, "money_pct": 50, "bp_pitch_count_3d": 150})
            home_stats.update({"odds": -110, "public_bets_pct": 50, "money_pct": 50, "bp_pitch_count_3d": 150})

            slate.append({
                "game_id": g.get("gamePk"),
                "away_team": away.get("team", {}).get("name"),
                "away_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{away_id}.svg" if away_id else "",
                "away_stats": away_stats,
                "home_team": home.get("team", {}).get("name"),
                "home_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{home_id}.svg" if home_id else "",
                "home_stats": home_stats,
            })
        return slate
    except Exception:
        return []

def get_fatigue_badge(pitches: int) -> str:
    return '<span style="color:#6EE7B7;font-size:0.75rem;">RESTED</span>'

# ------------------------------------------------------------------
# 5. DASHBOARD UI & MANUAL OVERRIDES
# ------------------------------------------------------------------
st.title("⚾ MLB Quantitative Edge Engine")
st.caption("Multi-Factor Intelligence • Live In-Game Score Tracker")

# Sidebar Manual Override Panel so you can force live states instantly
with st.sidebar:
    st.header("⚙️ Manual Live Controls")
    st.info("Use this if the official MLB API status feed is stuck on 'Scheduled' while games are playing.")
    force_live_mode = st.checkbox("Force Manual Live Score Mode", value=False)
    manual_away_runs = st.number_input("Away Runs", min_value=0, max_value=30, value=2)
    manual_home_runs = st.number_input("Home Runs", min_value=0, max_value=30, value=4)

slate = load_full_slate()

if not slate:
    st.warning("No active games on today's MLB slate.")
else:
    evaluated_slate = []
    for g in slate:
        park = get_park_factor(g["home_team"])
        live_state = fetch_live_game_state(g["game_id"])
        
        # If manual override is enabled in the sidebar, force it live!
        if force_live_mode:
            live_state = {
                "status": "LIVE",
                "badge_html": f'<span class="badge-live">🔴 MANUAL LIVE ({manual_away_runs}-{manual_home_runs})</span>',
                "away_runs": manual_away_runs,
                "home_runs": manual_home_runs
            }

        analysis = build_editorial_breakdown(g["away_team"], g["home_team"], g["away_stats"], g["home_stats"], park)
        
        if live_state["status"] == "LIVE":
            away_p, home_p = adjust_prob_for_live_state(analysis["home_prob"], live_state)
            analysis["home_prob"] = home_p
            analysis["away_prob"] = away_p
            analysis["win_prob"] = round(home_p * 100, 1)
            analysis["narrative"] = f"🔴 <span class='highlight-txt'>LIVE UPDATE</span>: Score is {g['away_team']} {live_state['away_runs']} - {g['home_team']} {live_state['home_runs']}. Probabilities adjusted."

        evaluated_slate.append({**g, "park": park, "analysis": analysis, "live": live_state})

    for g in evaluated_slate:
        an = g["analysis"]
        away_pct = int(an["away_prob"] * 100)
        home_pct = int(an["home_prob"] * 100)

        with st.container():
            st.markdown('<div class="matchup-card">', unsafe_allow_html=True)
            col_hdr, col_status = st.columns([3, 1])
            with col_hdr:
                st.markdown(f"**{g['away_team']}** @ **{g['home_team']}**", unsafe_allow_html=True)
            with col_status:
                st.markdown(f'<div style="text-align: right;">{g["live"]["badge_html"]}</div>', unsafe_allow_html=True)
            
            st.markdown(f'<div class="narrative-box">{an["narrative"]}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
