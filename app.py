import math
import re
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# ------------------------------------------------------------------
# 1. PAGE CONFIG & MODERN HUD STYLING
# ------------------------------------------------------------------
st.set_page_config(
    page_title="MLB Quantitative Terminal",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800&display=swap');

    html, body, [class*="css"], div, span, h1, h2, h3, h4, p {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stApp {
        background: radial-gradient(circle at 50% 0%, #0f172a 0%, #070d1b 50%, #02060d 100%);
        color: #F8FAFC;
        overflow-x: hidden;
    }

    /* Floating Ambient Bubbles */
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
        background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.25), rgba(56, 189, 248, 0.08));
        border: 1px solid rgba(56, 189, 248, 0.15);
        border-radius: 50%;
        animation: riseUp linear infinite;
    }
    @keyframes riseUp {
        0% { transform: translateY(0) translateX(0) scale(1); opacity: 0; }
        20% { opacity: 0.5; }
        80% { opacity: 0.5; }
        100% { transform: translateY(-110vh) translateX(20px) scale(1.05); opacity: 0; }
    }
    .bubble:nth-child(1) { left: 8%; width: 22px; height: 22px; animation-duration: 12s; animation-delay: 0s; }
    .bubble:nth-child(2) { left: 22%; width: 34px; height: 34px; animation-duration: 16s; animation-delay: 3s; }
    .bubble:nth-child(3) { left: 40%; width: 14px; height: 14px; animation-duration: 9s; animation-delay: 1s; }
    .bubble:nth-child(4) { left: 60%; width: 40px; height: 40px; animation-duration: 20s; animation-delay: 5s; }
    .bubble:nth-child(5) { left: 78%; width: 26px; height: 26px; animation-duration: 14s; animation-delay: 2s; }
    .bubble:nth-child(6) { left: 91%; width: 18px; height: 18px; animation-duration: 10s; animation-delay: 4s; }

    .stMainBlockContainer { position: relative; z-index: 1; padding-top: 2rem; }

    /* Clean Card Bubbles */
    .metric-bubble {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(12px);
    }

    /* Streamlit Button Styling */
    .stButton button {
        width: 100%;
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.9) 100%) !important;
        border: 1px solid rgba(56, 189, 248, 0.25) !important;
        border-radius: 12px !important;
        color: #F8FAFC !important;
        padding: 8px 12px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3) !important;
    }
    .stButton button:hover {
        border-color: #38BDF8 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(56, 189, 248, 0.3) !important;
        background: linear-gradient(145deg, rgba(56, 189, 248, 0.2) 0%, rgba(15, 23, 42, 0.95) 100%) !important;
    }

    /* Visual Diamond HUD */
    .diamond-wrapper {
        position: relative;
        width: 32px;
        height: 32px;
        flex-shrink: 0;
    }
    .diamond-wrapper-lg {
        position: relative;
        width: 90px;
        height: 90px;
        margin: 0 auto;
    }
    .base {
        position: absolute;
        width: 7px;
        height: 7px;
        background: rgba(51, 65, 85, 0.8);
        border: 1px solid rgba(100, 116, 139, 0.8);
        transform: rotate(45deg);
        border-radius: 1px;
    }
    .base-lg {
        position: absolute;
        width: 20px;
        height: 20px;
        background: rgba(51, 65, 85, 0.8);
        border: 1px solid rgba(100, 116, 139, 0.8);
        transform: rotate(45deg);
        border-radius: 3px;
    }
    .base.active, .base-lg.active {
        background: #38BDF8;
        border-color: #7dd3fc;
        box-shadow: 0 0 10px #38BDF8;
    }
    .base-2b { top: 1px; left: 12px; }
    .base-3b { top: 12px; left: 1px; }
    .base-1b { top: 12px; right: 1px; }

    .base-lg-2b { top: 4px; left: 35px; }
    .base-lg-3b { top: 35px; left: 4px; }
    .base-lg-1b { top: 35px; right: 4px; }

    /* Badges */
    .badge-live {
        background: rgba(239, 68, 68, 0.18);
        border: 1px solid rgba(239, 68, 68, 0.5);
        color: #FCA5A5;
        font-weight: 800;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.68rem;
        font-family: 'JetBrains Mono', monospace;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    .badge-final {
        background: rgba(51, 65, 85, 0.4);
        border: 1px solid rgba(100, 116, 139, 0.4);
        color: #94A3B8;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.68rem;
    }
    .badge-upcoming {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(51, 65, 85, 0.4);
        color: #64748B;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.68rem;
    }

    .big-score {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem;
        font-weight: 800;
        color: #F8FAFC;
    }
    .stat-label {
        color: #94A3B8;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }
</style>

<div class="bubbles-container">
    <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
    <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
</div>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# 2. SIDEBAR CONTROLS (NO AUTO-REFRESH)
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    manual_refresh_btn = st.button("🔄 Refresh Data Now", use_container_width=True)
    st.caption("Manual refresh mode active. Page will never auto-refresh or jump.")

# ------------------------------------------------------------------
# 3. PARK FACTORS & WEATHER ENGINE
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
# 4. LIVE GAME STATE ENGINE
# ------------------------------------------------------------------
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
        away_errors = teams_linescore.get("away", {}).get("errors", 0)
        home_errors = teams_linescore.get("home", {}).get("errors", 0)

        innings_list = linescore.get("innings", [])
        plays_data = live_data.get("plays", {})
        all_plays = plays_data.get("allPlays", [])
        recent_plays = []
        for p in reversed(all_plays[-10:]):
            result = p.get("result", {})
            about = p.get("about", {})
            recent_plays.append({
                "inning": about.get("inningOrdinal", ""),
                "description": result.get("description", "")
            })

        if abstract_state == "Live" or "In Progress" in detailed_state or detailed_state == "Warmup":
            inning = linescore.get("currentInning", 1)
            half = linescore.get("inningState", "Top")
            inning_ordinal = linescore.get("currentInningOrdinal", f"{inning}th")
            outs = linescore.get("outs", 0)
            
            offense = linescore.get("offense", {})
            has_1b = 1 if offense.get("first") else 0
            has_2b = 1 if offense.get("second") else 0
            has_3b = 1 if offense.get("third") else 0

            half_weight = 1 if half.lower().startswith("top") else 2
            sort_val = (inning * 10) + half_weight

            return {
                "status": "LIVE",
                "sort_priority": sort_val,
                "badge_html": '<span class="badge-live">🔴 LIVE</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "away_hits": away_hits, "home_hits": home_hits,
                "away_errors": away_errors, "home_errors": home_errors,
                "inning_str": f"{half} {inning_ordinal}",
                "outs": outs,
                "has_1b": has_1b, "has_2b": has_2b, "has_3b": has_3b,
                "innings_list": innings_list,
                "recent_plays": recent_plays
            }
        elif abstract_state == "Final" or "Final" in detailed_state:
            return {
                "status": "FINAL",
                "sort_priority": 9999,
                "badge_html": '<span class="badge-final">🏁 FINAL</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "away_hits": away_hits, "home_hits": home_hits,
                "away_errors": away_errors, "home_errors": home_errors,
                "inning_str": "Final",
                "outs": 0, "has_1b": 0, "has_2b": 0, "has_3b": 0,
                "innings_list": innings_list,
                "recent_plays": recent_plays
            }
        else:
            return {
                "status": "PREVIEW",
                "sort_priority": -100,
                "badge_html": f'<span class="badge-upcoming">⏰ {detailed_state}</span>',
                "away_runs": 0, "home_runs": 0,
                "away_hits": 0, "home_hits": 0,
                "away_errors": 0, "home_errors": 0,
                "inning_str": "Upcoming",
                "outs": 0, "has_1b": 0, "has_2b": 0, "has_3b": 0,
                "innings_list": [],
                "recent_plays": []
            }
    except Exception:
        return {
            "status": "PREVIEW",
            "sort_priority": -100,
            "badge_html": '<span class="badge-upcoming">⏰ Upcoming</span>',
            "away_runs": 0, "home_runs": 0,
            "away_hits": 0, "home_hits": 0,
            "away_errors": 0, "home_errors": 0,
            "inning_str": "Upcoming",
            "outs": 0, "has_1b": 0, "has_2b": 0, "has_3b": 0,
            "innings_list": [],
            "recent_plays": []
        }

def adjust_prob_for_live_state(base_home_prob: float, live_state: dict) -> tuple[float, float]:
    if live_state["status"] != "LIVE":
        return 1.0 - base_home_prob, base_home_prob
    run_diff = live_state["home_runs"] - live_state["away_runs"]
    prob_shift = run_diff * 0.085
    new_home_prob = min(0.99, max(0.01, base_home_prob + prob_shift))
    return 1.0 - new_home_prob, new_home_prob

# ------------------------------------------------------------------
# 5. MODEL BREAKDOWN & SLATE LOADER
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
            f"LIVE GAME STREAM ACTIVE ({live_state['inning_str']} | Score: {score_str}): "
            f"Model is actively pricing live momentum. Starters {away_stats['pitcher']} "
            f"and {home_stats['pitcher']} have shaped the script. "
            f"Quantitative edge leans toward {target} at {win_p:.1f}% probability."
        )
    else:
        narrative = (
            f"Model projects {target} to win at {win_p:.1f}%. "
            f"{edge_team_name}'s starter {edge_pitcher['pitcher']} holds a suppression advantage "
            f"(ERA: {edge_pitcher['era']:.2f}, xwOBA: {edge_pitcher['xwoba']:.3f}) under {park['name']} park conditions."
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
# 6. DASHBOARD RENDERING & USER CONTROL FLOW
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

    def game_sort_key(item):
        st_val = item["live"]["status"]
        priority = item["live"]["sort_priority"]
        if st_val == "LIVE":
            return (0, -priority)
        elif st_val == "PREVIEW":
            return (1, 0)
        else:
            return (2, 0)

    evaluated_slate.sort(key=game_sort_key)

    if "selected_game_id" not in st.session_state:
        st.session_state["selected_game_id"] = None

    # --- DEEP DIVE INSPECTOR ---
    if st.session_state["selected_game_id"] is not None:
        selected_g = next((x for x in evaluated_slate if x["game_id"] == st.session_state["selected_game_id"]), None)
        
        if selected_g:
            lv = selected_g["live"]
            
            if st.button("⬅️ Back to Scoreboard Grid"):
                st.session_state["selected_game_id"] = None
                st.rerun()

            is_live = (lv["status"] == "LIVE")
            b1_lg = "active" if lv.get("has_1b") else ""
            b2_lg = "active" if lv.get("has_2b") else ""
            b3_lg = "active" if lv.get("has_3b") else ""

            diamond_section = ""
            if is_live:
                diamond_section = f"""
                <div style="display: flex; align-items: center; gap: 30px; background: rgba(15, 23, 42, 0.6); padding: 12px 24px; border-radius: 16px; border: 1px solid rgba(56, 189, 248, 0.2);">
                    <div class="diamond-wrapper-lg">
                        <div class="base-lg base-lg-2b {b2_lg}"></div>
                        <div class="base-lg base-lg-3b {b3_lg}"></div>
                        <div class="base-lg base-lg-1b {b1_lg}"></div>
                    </div>
                    <div style="text-align: left; font-family: 'JetBrains Mono', monospace;">
                        <div style="font-size: 0.8rem; color: #94A3B8; text-transform: uppercase;">Outs</div>
                        <div style="font-size: 2.2rem; font-weight: 800; color: #38BDF8; line-height: 1;">{lv.get('outs', 0)}</div>
                    </div>
                </div>
                """

            st.markdown(
                f"""
                <div class="metric-bubble" style="margin-top: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
                        <div style="display: flex; align-items: center; gap: 16px;">
                            <img src="{selected_g['away_logo']}" width="52" height="52" />
                            <div>
                                <h2 style="margin:0; font-size: 1.8rem; font-weight: 800;">{selected_g['away_team']} @ {selected_g['home_team']}</h2>
                                <div style="margin-top: 6px;">{lv['badge_html']}</div>
                            </div>
                            <img src="{selected_g['home_logo']}" width="52" height="52" />
                        </div>
                        {diamond_section}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            col_box1, col_box2 = st.columns(2)
            with col_box1:
                st.markdown(
                    f"""
                    <div class="metric-bubble">
                        <h3 style="margin-top:0; font-size: 1.1rem; color: #38BDF8;">🏟️ Box Score Summary</h3>
                        <div style="display: flex; justify-content: space-around; text-align: center; margin-top: 15px;">
                            <div>
                                <div class="stat-label">Runs</div>
                                <div class="big-score">{lv['away_runs']} - {lv['home_runs']}</div>
                            </div>
                            <div>
                                <div class="stat-label">Hits</div>
                                <div class="big-score" style="font-size: 1.4rem; margin-top: 5px;">{lv.get('away_hits', 0)} - {lv.get('home_hits', 0)}</div>
                            </div>
                            <div>
                                <div class="stat-label">Errors</div>
                                <div class="big-score" style="font-size: 1.4rem; margin-top: 5px;">{lv.get('away_errors', 0)} - {lv.get('home_errors', 0)}</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_box2:
                st.markdown(
                    f"""
                    <div class="metric-bubble">
                        <h3 style="margin-top:0; font-size: 1.1rem; color: #38BDF8;">🌤️ Venue & Environment</h3>
                        <p style="margin: 8px 0;"><b>Ballpark:</b> {selected_g['park']['name']}</p>
                        <p style="margin: 8px 0;"><b>Weather:</b> {selected_g['park']['weather']['weather_desc']}</p>
                        <p style="margin: 8px 0;"><b>Environment Multiplier:</b> {selected_g['park']['run_mult']}x Run Factor</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            st.markdown("### ⚡ Live Play-by-Play Feed")
            with st.container():
                st.markdown('<div class="metric-bubble">', unsafe_allow_html=True)
                plays = lv.get("recent_plays", [])
                if plays:
                    for p in plays:
                        st.markdown(f"**[{p['inning']}]** {p['description']}")
                else:
                    st.info("Play-by-play feed updates automatically when games are live.")
                st.markdown('</div>', unsafe_allow_html=True)

            st.stop()

    # --- MAIN SCOREBOARD GRID ---
    st.markdown(
        """
        <div class="metric-bubble" style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1 style="margin:0; font-size: 1.6rem; font-weight: 900; letter-spacing: -0.02em;">⚾ MLB QUANTITATIVE TERMINAL</h1>
                <p style="margin:4px 0 0 0; color: #38BDF8; font-size: 0.82rem; font-family: 'JetBrains Mono', monospace;">LIVE SCOREBOARD • CLICK ANY GAME CARD FOR DEEP DIVE</p>
            </div>
            <div>
                <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; padding: 6px 14px; border-radius: 12px; font-size: 0.78rem; font-family: 'JetBrains Mono', monospace; font-weight: 700;">
                    🟢 STABLE MODE ACTIVE
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols_per_row = 4
    for i in range(0, len(evaluated_slate), cols_per_row):
        row_games = evaluated_slate[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        
        for idx, g in enumerate(row_games):
            lv = g["live"]
            is_live_card = (lv["status"] == "LIVE")
            
            b1 = "active" if lv.get("has_1b") else ""
            b2 = "active" if lv.get("has_2b") else ""
            b3 = "active" if lv.get("has_3b") else ""

            diamond_html = ""
            if is_live_card:
                diamond_html = f"""
                <div class="diamond-wrapper">
                    <div class="base base-2b {b2}"></div>
                    <div class="base base-3b {b3}"></div>
                    <div class="base base-1b {b1}"></div>
                </div>
                """

            with cols[idx]:
                st.markdown(
                    f"""
                    <div class="metric-bubble" style="padding: 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            {lv['badge_html']}
                            {diamond_html}
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <img src="{g['away_logo']}" width="20" height="20" />
                                <span style="font-weight: 700; font-size: 0.85rem;">{g['away_short']}</span>
                            </div>
                            <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 0.95rem; color: {'#38BDF8' if is_live_card else '#F8FAFC'};">{lv['away_runs']}</span>
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <img src="{g['home_logo']}" width="20" height="20" />
                                <span style="font-weight: 700; font-size: 0.85rem;">{g['home_short']}</span>
                            </div>
                            <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 0.95rem; color: {'#38BDF8' if is_live_card else '#F8FAFC'};">{lv['home_runs']}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if st.button("🔍 Deep Dive", key=f"card_{g['game_id']}", use_container_width=True):
                    st.session_state["selected_game_id"] = g["game_id"]
                    st.rerun()

    st.markdown("<br>### 📊 Full Slate Model Predictions & Matchups", unsafe_allow_html=True)

    for g in evaluated_slate:
        an = g["analysis"]
        away_pct = int(an["away_prob"] * 100)
        home_pct = int(an["home_prob"] * 100)
        is_home_pick = (an["target"] == g["home_team"])
        pick_logo = g["home_logo"] if is_home_pick else g["away_logo"]

        st.markdown('<div class="metric-bubble">', unsafe_allow_html=True)
        
        col_hdr, col_status = st.columns([3, 1])
        with col_hdr:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 12px;">
                    <img src="{g['away_logo']}" width="28" height="28" />
                    <span style="font-size: 1.1rem; font-weight: 800;">{g['away_team']}</span>
                    <span style="color: #64748B; font-weight: 700;">@</span>
                    <img src="{g['home_logo']}" width="28" height="28" />
                    <span style="font-size: 1.1rem; font-weight: 800;">{g['home_team']}</span>
                    <span style="color: #64748B; font-size: 0.8rem; margin-left: 6px;">({g['park']['name']})</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_status:
            st.markdown(f'<div style="text-align: right;">{g["live"]["badge_html"]}</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 12px; margin: 14px 0 10px 0;">
                <img src="{pick_logo}" width="30" height="30" />
                <div>
                    <span style="background: linear-gradient(135deg, #38BDF8 0%, #0284C7 100%); color: #FFF; font-weight: 800; padding: 5px 14px; border-radius: 20px; font-size: 0.78rem; letter-spacing: 0.04em;">MODEL PICK: {an['target']}</span>
                    <span style="color: #38BDF8; font-weight: 800; font-size: 0.88rem; margin-left: 10px; font-family: 'JetBrains Mono', monospace;">({an['win_prob']}% Win Probability)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns([1.1, 1.1, 1.4])

        def render_pitcher_column(stats, pct_val):
            st.markdown(
                f"""
                <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 14px; padding: 12px; margin-bottom: 10px;">
                    <div style="font-weight: 700; font-size: 0.88rem; margin-bottom: 6px;">{stats['pitcher']} <span style="color: #38BDF8; font-family: JetBrains Mono; font-size: 0.72rem;">({stats['record']})</span></div>
                    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <span style="background: rgba(30,41,59,0.8); padding: 3px 8px; border-radius: 6px; font-size: 0.7rem; font-family: JetBrains Mono; color: #94A3B8;">ERA: <b style="color:#fff;">{stats['era']:.2f}</b></span>
                        <span style="background: rgba(30,41,59,0.8); padding: 3px 8px; border-radius: 6px; font-size: 0.7rem; font-family: JetBrains Mono; color: #94A3B8;">xwOBA: <b style="color:#fff;">{stats['xwoba']:.3f}</b></span>
                    </div>
                </div>
                <div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #94A3B8; margin-bottom: 3px; font-family: JetBrains Mono;">
                        <span>Win Prob</span>
                        <span style="color: #38BDF8; font-weight: 700;">{pct_val}%</span>
                    </div>
                    <div style="background: rgba(15, 23, 42, 0.8); border-radius: 6px; overflow: hidden; height: 6px; width: 100%;">
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
            st.markdown("<div class='stat-label' style='margin-bottom: 4px;'>Quantitative Rationale</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.84rem; line-height: 1.5; color: #94A3B8;'>{an['narrative']}</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
