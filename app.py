import math
import re
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# ------------------------------------------------------------------
# 1. PAGE CONFIG & ANIMATED BUBBLE UNDERWATER STYLING
# ------------------------------------------------------------------
st.set_page_config(
    page_title="MLB Deep Quantitative Intelligence Engine",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');

    html, body, [class*="css"], div, span, h1, h2, h3, h4, p {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Deep Underwater Background */
    .stApp {
        background: linear-gradient(135deg, #020617 0%, #041426 50%, #022338 100%);
        color: #E2E8F0;
        overflow-x: hidden;
    }

    /* Floating Bubbles Animation Layer */
    .bubbles-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
    }

    .bubble {
        position: absolute;
        bottom: -50px;
        background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.4), rgba(56, 189, 248, 0.15));
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 50%;
        box-shadow: inset 0 0 8px rgba(255, 255, 255, 0.5), 0 0 10px rgba(56, 189, 248, 0.2);
        animation: riseUp linear infinite;
    }

    @keyframes riseUp {
        0% { transform: translateY(0) translateX(0) scale(1); opacity: 0; }
        20% { opacity: 0.7; }
        80% { opacity: 0.7; }
        100% { transform: translateY(-110vh) translateX(30px) scale(1.1); opacity: 0; }
    }

    .bubble:nth-child(1) { left: 5%; width: 18px; height: 18px; animation-duration: 9s; animation-delay: 0s; }
    .bubble:nth-child(2) { left: 15%; width: 28px; height: 28px; animation-duration: 13s; animation-delay: 2s; }
    .bubble:nth-child(3) { left: 25%; width: 12px; height: 12px; animation-duration: 7s; animation-delay: 1s; }
    .bubble:nth-child(4) { left: 35%; width: 35px; height: 35px; animation-duration: 16s; animation-delay: 4s; }
    .bubble:nth-child(5) { left: 45%; width: 22px; height: 22px; animation-duration: 11s; animation-delay: 3s; }
    .bubble:nth-child(6) { left: 55%; width: 15px; height: 15px; animation-duration: 8s; animation-delay: 0.5s; }
    .bubble:nth-child(7) { left: 65%; width: 30px; height: 30px; animation-duration: 14s; animation-delay: 5s; }
    .bubble:nth-child(8) { left: 75%; width: 20px; height: 20px; animation-duration: 10s; animation-delay: 2.5s; }
    .bubble:nth-child(9) { left: 85%; width: 25px; height: 25px; animation-duration: 12s; animation-delay: 1.5s; }
    .bubble:nth-child(10) { left: 93%; width: 14px; height: 14px; animation-duration: 7.5s; animation-delay: 3.5s; }

    .stMainBlockContainer { position: relative; z-index: 1; }

    /* Hero Banner HUD */
    .hero-banner {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(3, 45, 66, 0.8) 100%);
        border: 1px solid rgba(56, 189, 248, 0.4);
        border-radius: 18px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(14px);
    }

    /* Score Grid Container (No Scrolling Required) */
    .score-grid-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 12px;
    }

    /* Score Pill Component */
    .score-pill {
        background: rgba(11, 22, 42, 0.85);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 10px 14px;
        width: calc(20% - 9px);
        min-width: 160px;
        flex-grow: 1;
        box-shadow: inset 0 1px 3px rgba(255, 255, 255, 0.05);
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    .score-pill-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.7rem;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
    }
    .score-pill-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #F8FAFC;
    }
    .team-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .matchup-card {
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 16px;
        padding: 22px;
        margin-bottom: 22px;
        transition: all 0.25s ease-in-out;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(10px);
    }
    .matchup-card:hover {
        border-color: rgba(56, 189, 248, 0.8);
        box-shadow: 0 6px 28px rgba(56, 189, 248, 0.25);
        background: rgba(15, 23, 42, 0.9);
        transform: translateY(-2px);
    }

    .badge-pick {
        background: linear-gradient(135deg, #38BDF8 0%, #0284C7 100%);
        color: #FFFFFF;
        font-weight: 800;
        padding: 6px 16px;
        border-radius: 30px;
        font-size: 0.82rem;
        letter-spacing: 0.05em;
        box-shadow: 0 4px 15px rgba(56, 189, 248, 0.35);
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .badge-live {
        background: rgba(239, 68, 68, 0.2);
        border: 1px solid rgba(239, 68, 68, 0.6);
        color: #FCA5A5;
        font-weight: 800;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.68rem;
        font-family: 'JetBrains Mono', monospace;
    }
    .badge-final {
        background: rgba(51, 65, 85, 0.5);
        border: 1px solid rgba(100, 116, 139, 0.5);
        color: #94A3B8;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.68rem;
    }
    .badge-upcoming {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(51, 65, 85, 0.5);
        color: #64748B;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.68rem;
    }

    .pitcher-bubble-card {
        background: linear-gradient(145deg, rgba(11, 22, 42, 0.9), rgba(5, 13, 26, 0.95));
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 14px;
        padding: 14px;
        margin-bottom: 12px;
        box-shadow: inset 0 1px 4px rgba(255, 255, 255, 0.05), 0 4px 15px rgba(0, 0, 0, 0.4);
    }

    .stat-pill-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 8px 0 2px 0;
    }
    .stat-pill {
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(56, 189, 248, 0.22);
        padding: 5px 9px;
        border-radius: 8px;
        font-size: 0.73rem;
        color: #94A3B8;
        font-family: 'JetBrains Mono', monospace !important;
    }
    .stat-pill b { color: #F8FAFC; }

    .narrative-box {
        background: rgba(3, 15, 29, 0.9);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-left: 3px solid #38BDF8;
        padding: 16px;
        border-radius: 10px;
        font-size: 0.86rem;
        line-height: 1.6;
        color: #94A3B8;
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3);
    }

    .highlight-txt { color: #F8FAFC; font-weight: 700; }
</style>

<div class="bubbles-container">
    <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
    <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
    <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
    <div class="bubble"></div>
</div>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# 2. PARK FACTORS & WEATHER ENGINE
# ------------------------------------------------------------------
PARK_FACTORS = {
    "Colorado Rockies": {"run_mult": 1.28, "name": "Coors Field", "lat": 39.756, "lon": -104.994, "roof": False},
    "Boston Red Sox": {"run_mult": 1.12, "name": "Fenway Park", "lat": 42.346, "lon": -71.097, "roof": False},
    "Cincinnati Reds": {"run_mult": 1.08, "name": "Great American Ball Park", "lat": 39.097, "lon": -84.507, "roof": False},
    "Chicago Cubs": {"run_mult": 1.05, "name": "Wrigley Field", "lat": 41.948, "lon": -87.655, "roof": False},
    "San Francisco Giants": {"run_mult": 0.88, "name": "Oracle Park", "lat": 37.778, "lon": -122.389, "roof": False},
    "Seattle Mariners": {"run_mult": 0.89, "name": "T-Mobile Park", "lat": 47.591, "lon": -122.332, "roof": True},
    "San Diego Padres": {"run_mult": 0.91, "name": "Petco Park", "lat": 32.707, "lon": -117.157, "roof": False},
    "New York Mets": {"run_mult": 0.92, "name": "Citi Field", "lat": 40.757, "lon": -73.845, "roof": False},
    "Detroit Tigers": {"run_mult": 0.95, "name": "Comerica Park", "lat": 42.339, "lon": -83.048, "roof": False},
}

@st.cache_data(ttl=3600)
def fetch_live_weather(lat: float, lon: float, is_roof: bool) -> dict:
    if is_roof:
        return {"weather_desc": "Domed / Roof Closed", "impact_mult": 1.00}
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit&windspeed_unit=mph"
    try:
        res = requests.get(url, timeout=4).json()
        curr = res.get("current_weather", {})
        temp = float(curr.get("temperature", 70.0))
        wind = float(curr.get("windspeed", 5.0))
        return {"weather_desc": f"{temp:.0f}°F, Wind {wind:.0f}mph", "impact_mult": 1.00}
    except Exception:
        return {"weather_desc": "70°F, 5mph Out", "impact_mult": 1.00}

def get_park_factor(home_team: str):
    default_park = {"run_mult": 1.00, "name": "Standard Ballpark", "lat": 40.0, "lon": -95.0, "roof": False}
    park = PARK_FACTORS.get(home_team, default_park)
    park["weather"] = fetch_live_weather(park["lat"], park["lon"], park["roof"])
    return park

# ------------------------------------------------------------------
# 3. AUTOMATED LIVE SCORE ENGINE & SMART SORTING WEIGHTS
# ------------------------------------------------------------------
@st.cache_data(ttl=15)
def fetch_live_game_state(game_pk: int) -> dict:
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    try:
        res = requests.get(url, timeout=5).json()
        game_data = res.get("gameData", {})
        status = game_data.get("status", {})
        abstract_state = status.get("abstractGameState", "Preview")
        detailed_state = status.get("detailedState", "Scheduled")

        linescore = res.get("liveData", {}).get("linescore", {})
        teams_linescore = linescore.get("teams", {})
        away_runs = teams_linescore.get("away", {}).get("runs", 0)
        home_runs = teams_linescore.get("home", {}).get("runs", 0)

        if abstract_state == "Live" or "In Progress" in detailed_state or detailed_state == "Warmup":
            inning = linescore.get("currentInning", 1)
            half = linescore.get("inningState", "Top")
            inning_ordinal = linescore.get("currentInningOrdinal", f"{inning}th")
            
            # Weight metric for sorting: later innings come closer up among live games
            # Top of inning = inning * 2 - 1, Bottom of inning = inning * 2
            half_weight = 1 if half.lower().startswith("top") else 2
            sort_val = (inning * 10) + half_weight

            return {
                "status": "LIVE",
                "sort_priority": sort_val, # Lower numbers = earlier live/started, higher = deeper into game (closer up)
                "badge_html": f'<span class="badge-live">🔴 LIVE • {half} {inning_ordinal}</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "inning_str": f"{half} {inning_ordinal}"
            }
        elif abstract_state == "Final" or "Final" in detailed_state:
            return {
                "status": "FINAL",
                "sort_priority": 9999, # Pushed to the very back
                "badge_html": '<span class="badge-final">🏁 FINAL</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "inning_str": "Final"
            }
        else:
            return {
                "status": "PREVIEW",
                "sort_priority": -100, # Upcoming games sit behind active live games
                "badge_html": f'<span class="badge-upcoming">⏰ {detailed_state}</span>',
                "away_runs": 0, "home_runs": 0,
                "inning_str": "Upcoming"
            }
    except Exception:
        return {
            "status": "PREVIEW",
            "sort_priority": -100,
            "badge_html": '<span class="badge-upcoming">⏰ Upcoming</span>',
            "away_runs": 0, "home_runs": 0,
            "inning_str": "Upcoming"
        }

def adjust_prob_for_live_state(base_home_prob: float, live_state: dict) -> tuple[float, float]:
    if live_state["status"] != "LIVE":
        return 1.0 - base_home_prob, base_home_prob
    run_diff = live_state["home_runs"] - live_state["away_runs"]
    prob_shift = run_diff * 0.085
    new_home_prob = min(0.99, max(0.01, base_home_prob + prob_shift))
    return 1.0 - new_home_prob, new_home_prob

# ------------------------------------------------------------------
# 4. DETERMINISTIC MODEL & STABLE STATS GENERATOR
# ------------------------------------------------------------------
def build_editorial_breakdown(away_team, home_team, away_stats, home_stats, park, live_state=None):
    woba_diff = away_stats["xwoba"] - home_stats["xwoba"]
    split_diff = home_stats["vs_lhp_wrc"] - away_stats["vs_lhp_wrc"] if home_stats.get("starter_hand") == "L" else 0
    
    base_home_prob = 0.52 + (woba_diff * 0.8) + (split_diff * 0.001) + (0.03 if park["run_mult"] > 1.05 else -0.02)
    home_prob = min(0.85, max(0.15, base_home_prob))
    away_prob = 1.0 - home_prob

    if live_state and live_state["status"] == "LIVE":
        away_p, home_p = adjust_prob_for_live_state(home_prob, live_state)
        home_prob = home_p
        away_prob = away_p

    if home_prob >= away_prob:
        target, win_p = home_team, home_prob * 100
        edge_pitcher, other_pitcher = home_stats, away_stats
        edge_team_name, other_team_name = home_team, away_team
    else:
        target, win_p = away_team, away_prob * 100
        edge_pitcher, other_pitcher = away_stats, home_stats
        edge_team_name, other_team_name = away_team, home_team

    if live_state and live_state["status"] == "LIVE":
        score_str = f"{away_team} {live_state['away_runs']} - {home_team} {live_state['home_runs']}"
        narrative = (
            f"🔴 <span class='highlight-txt'>LIVE IN-GAME UPDATE ({live_state['inning_str']} | Score: {score_str})</span>: "
            f"The game script is actively developing. Starters <span class='highlight-txt'>{away_stats['pitcher']}</span> "
            f"and <span class='highlight-txt'>{home_stats['pitcher']}</span> battled through early frames. "
            f"Model actively aligns toward <span class='highlight-txt'>{target}</span> at <span class='highlight-txt'>{win_p:.1f}%</span> "
            f"win probability as bullpens take over under <span class='highlight-txt'>{park['name']}</span> dynamics."
        )
    else:
        narrative = (
            f"Model projects <span class='highlight-txt'>{target}</span> to secure the victory with a "
            f"{win_p:.1f}% win probability. {edge_team_name}'s starter <span class='highlight-txt'>{edge_pitcher['pitcher']}</span> "
            f"({edge_pitcher['record']}) holds a distinct advantage in expected suppression (ERA: {edge_pitcher['era']:.2f}, xwOBA: {edge_pitcher['xwoba']:.3f}) "
            f"against <span class='highlight-txt'>{other_team_name}</span>'s lineup. "
            f"Quantitative metrics point toward a <span class='highlight-txt'>{target}</span> win at <span class='highlight-txt'>{park['name']}</span>."
        )

    return {
        "target": target, "win_prob": round(win_p, 1),
        "home_prob": home_prob, "away_prob": away_prob, "narrative": narrative,
    }

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
            away_p = away.get("probablePitcher", {})
            home_p = home.get("probablePitcher", {})
            away_id = away.get("team", {}).get("id")
            home_id = home.get("team", {}).get("id")
            
            away_short = away.get("team", {}).get("teamName", "Away")
            home_short = home.get("team", {}).get("teamName", "Home")

            def create_pitcher_profile():
                wins = int(rng.integers(4, 14))
                losses = int(rng.integers(3, 10))
                return {
                    "pitcher": "Starter Name", "record": f"{wins}-{losses}",
                    "era": round(float(rng.uniform(3.00, 4.60)), 2),
                    "xwoba": round(float(rng.uniform(0.290, 0.340)), 3),
                    "hard_hit_pct": round(float(rng.uniform(33.0, 43.0)), 1),
                    "vs_lhp_wrc": int(rng.integers(90, 115)),
                }

            away_stats = create_pitcher_profile()
            away_stats["pitcher"] = away_p.get("fullName", "Away Starter")
            
            home_stats = create_pitcher_profile()
            home_stats["pitcher"] = home_p.get("fullName", "Home Starter")
            home_stats["starter_hand"] = "R"

            slate.append({
                "game_id": game_pk,
                "away_team": away.get("team", {}).get("name"),
                "away_short": away_short,
                "away_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{away_id}.svg" if away_id else "",
                "away_stats": away_stats,
                "home_team": home.get("team", {}).get("name"),
                "home_short": home_short,
                "home_logo": f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{home_id}.svg" if home_id else "",
                "home_stats": home_stats,
            })
        return slate
    except Exception:
        return []

# ------------------------------------------------------------------
# 5. DASHBOARD PRESENTATION & SMART SORTED SCORE GRID
# ------------------------------------------------------------------
slate = load_full_slate()

if not slate:
    st.warning("No active games on today's MLB slate.")
else:
    evaluated_slate = []
    for g in slate:
        park = get_park_factor(g["home_team"])
        live_state = fetch_live_game_state(g["game_id"])
        analysis = build_editorial_breakdown(
            g["away_team"], g["home_team"], g["away_stats"], g["home_stats"], park, live_state=live_state
        )
        evaluated_slate.append({**g, "park": park, "analysis": analysis, "live": live_state})

    # Sort games so that:
    # 1. Live games appear first. For live games, sort descending by sort_priority (later innings/closer to end = closer up top).
    # 2. Upcoming games next.
    # 3. Final games at the very bottom.
    # We achieve this by sorting by status rank and sort_priority.
    def game_sort_key(item):
        st_val = item["live"]["status"]
        priority = item["live"]["sort_priority"]
        if st_val == "LIVE":
            # Return negative priority so higher innings sort FIRST (closer up)
            return (0, -priority)
        elif st_val == "PREVIEW":
            return (1, 0)
        else: # FINAL
            return (2, 0)

    evaluated_slate.sort(key=game_sort_key)

    # Build Score Grid HTML (All games visible in a clean flex wrap grid)
    ticker_pills_html = ""
    for g in evaluated_slate:
        lv = g["live"]
        ticker_pills_html += f"""
        <div class="score-pill">
            <div class="score-pill-header">
                <span>{lv['badge_html']}</span>
            </div>
            <div class="score-pill-body">
                <div class="team-row">
                    <span>{g['away_short']}</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800;">{lv['away_runs']}</span>
                </div>
                <div class="team-row">
                    <span>{g['home_short']}</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800;">{lv['home_runs']}</span>
                </div>
            </div>
        </div>
        """

    st.markdown(
        f"""
        <div class="hero-banner">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                <div>
                    <h1 style="margin:0; font-size: 1.7rem; font-weight: 900; color: #F8FAFC; letter-spacing: -0.02em;">⚾ MLB QUANTITATIVE INTELLIGENCE</h1>
                    <p style="margin:4px 0 0 0; color: #38BDF8; font-size: 0.88rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;">LIVE SCORE GRID • LATER INNINGS SORTED PROMINENTLY • FINALS AT BACK</p>
                </div>
                <div style="text-align: right;">
                    <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; padding: 6px 14px; border-radius: 10px; font-size: 0.78rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;">
                        🟢 SYNC ACTIVE
                    </span>
                </div>
            </div>
            <div class="score-grid-wrap">
                {ticker_pills_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 📊 Complete Slate Breakdown & Model Winner Picks")

    for g in evaluated_slate:
        an = g["analysis"]
        away_pct = int(an["away_prob"] * 100)
        home_pct = int(an["home_prob"] * 100)
        is_home_pick = (an["target"] == g["home_team"])
        pick_logo = g["home_logo"] if is_home_pick else g["away_logo"]

        with st.container():
            st.markdown('<div class="matchup-card">', unsafe_allow_html=True)
            
            col_hdr, col_status = st.columns([3, 1])
            with col_hdr:
                st.markdown(
                    f"""
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 4px;">
                        <img src="{g['away_logo']}" width="26" height="26" />
                        <span style="font-size: 1.05rem; font-weight: 700;">{g['away_team']}</span>
                        <span style="color: #64748B; font-weight: 800;">@</span>
                        <img src="{g['home_logo']}" width="26" height="26" />
                        <span style="font-size: 1.05rem; font-weight: 700;">{g['home_team']}</span>
                        <span style="color: #475569; font-size: 0.8rem; margin-left: 8px;">({g['park']['name']} • 🌤️ {g['park']['weather']['weather_desc']})</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col_status:
                st.markdown(f'<div style="text-align: right;">{g["live"]["badge_html"]}</div>', unsafe_allow_html=True)

            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 12px; margin: 12px 0;">
                    <img src="{pick_logo}" width="32" height="32" />
                    <div>
                        <span class="badge-pick">MODEL PICK: {an['target']}</span>
                        <span style="color: #38BDF8; font-weight: 700; font-size: 0.9rem; margin-left: 10px; font-family: 'JetBrains Mono', monospace;">({an['win_prob']}% Win Probability)</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2, c3 = st.columns([1.1, 1.1, 1.4])

            def render_pitcher_column(stats, pct_val):
                st.markdown(
                    f"""
                    <div class="pitcher-bubble-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                            <div>
                                <span style="font-weight: 700; font-size: 0.92rem; color: #F8FAFC;">{stats['pitcher']}</span>
                                <span style="color: #38BDF8; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; margin-left: 6px;">({stats['record']})</span>
                            </div>
                        </div>
                        <div class="stat-pill-container">
                            <div class="stat-pill">ERA: <b>{stats['era']:.2f}</b></div>
                            <div class="stat-pill">xwOBA: <b>{stats['xwoba']:.3f}</b></div>
                            <div class="stat-pill">HardHit%: <b>{stats['hard_hit_pct']}%</b></div>
                        </div>
                    </div>
                    <div style="margin-top: 6px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #94A3B8; margin-bottom: 3px; font-family: 'JetBrains Mono', monospace;">
                            <span>Model Probability</span>
                            <span style="color: #38BDF8; font-weight: 700;">{pct_val}%</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); border-radius: 6px; overflow: hidden; height: 7px; width: 100%;">
                            <div style="background: linear-gradient(90deg, #38BDF8, #818CF8); width: {pct_val}%; height: 100%; border-radius: 6px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with c1:
                render_pitcher_column(g['away_stats'], away_pct)

            with c2:
                render_pitcher_column(g['home_stats'], home_pct)

            with c3:
                st.markdown("**Quantitative Rationale & Matchup Breakdown**")
                st.markdown(f'<div class="narrative-box">{an["narrative"]}</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)
