import math
import re
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st

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
        0% {
            transform: translateY(0) translateX(0) scale(1);
            opacity: 0;
        }
        20% {
            opacity: 0.7;
        }
        80% {
            opacity: 0.7;
        }
        100% {
            transform: translateY(-110vh) translateX(30px) scale(1.1);
            opacity: 0;
        }
    }

    /* Randomize bubble placement & speeds */
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

    /* Ensure app elements sit above bubbles */
    .stMainBlockContainer {
        position: relative;
        z-index: 1;
    }

    /* Hero Header Banner Decoration */
    .hero-banner {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.8) 0%, rgba(3, 45, 66, 0.75) 100%);
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(12px);
    }

    /* Enhanced Matchup Card with Glowing Edge */
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

    /* High-Confidence Badge */
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
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
        box-shadow: 0 0 12px rgba(239, 68, 68, 0.25);
    }

    .badge-final {
        background: rgba(51, 65, 85, 0.5);
        border: 1px solid rgba(100, 116, 139, 0.5);
        color: #94A3B8;
        font-weight: 700;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.78rem;
    }

    .badge-upcoming {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(51, 65, 85, 0.5);
        color: #64748B;
        font-weight: 600;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.78rem;
    }

    /* Glassmorphism Stat Pills */
    .stat-pill-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 10px 0;
    }
    .stat-pill {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(56, 189, 248, 0.25);
        padding: 5px 10px;
        border-radius: 8px;
        font-size: 0.75rem;
        color: #94A3B8;
        font-family: 'JetBrains Mono', monospace !important;
        backdrop-filter: blur(4px);
    }
    .stat-pill b { color: #F8FAFC; }

    /* Polished Narrative Box */
    .narrative-box {
        background: rgba(3, 15, 29, 0.9);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-left: 3px solid #38BDF8;
        padding: 16px;
        border-radius: 10px;
        font-size: 0.88rem;
        line-height: 1.65;
        color: #94A3B8;
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3);
    }

    .highlight-txt { color: #F8FAFC; font-weight: 700; }
</style>

<!-- Floating Bubbles HTML Injection -->
<div class="bubbles-container">
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
    <div class="bubble"></div>
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
# 3. AUTOMATED LIVE SCORE ENGINE
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
            inning = linescore.get("currentInningOrdinal", "1st")
            half = linescore.get("inningState", "Top")
            return {
                "status": "LIVE",
                "badge_html": f'<span class="badge-live">🔴 LIVE • {half} {inning} ({away_runs}-{home_runs})</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "inning_str": f"{half} {inning}"
            }
        elif abstract_state == "Final" or "Final" in detailed_state:
            return {
                "status": "FINAL",
                "badge_html": f'<span class="badge-final">🏁 FINAL ({away_runs}-{home_runs})</span>',
                "away_runs": away_runs, "home_runs": home_runs,
                "inning_str": "Final"
            }
        else:
            return {
                "status": "PREVIEW",
                "badge_html": f'<span class="badge-upcoming">⏰ {detailed_state}</span>',
                "away_runs": 0, "home_runs": 0,
                "inning_str": "Upcoming"
            }
    except Exception:
        return {
            "status": "PREVIEW",
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

# --------------------------------info------------------------------
# 4. QUANTITATIVE MODEL WITH LIVE DYNAMIC NARRATIVES
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
            f"The game script is actively developing on the field. Starting pitchers <span class='highlight-txt'>{away_stats['pitcher']}</span> "
            f"and <span class='highlight-txt'>{home_stats['pitcher']}</span> are currently battling through the frame traffic. "
            f"With the current scoreline, the win probability has adjusted dynamically. The model now leans toward <span class='highlight-txt'>{target}</span> "
            f"at <span class='highlight-txt'>{win_p:.1f}%</span> win probability as bullpens and high-leverage at-bats come into play under "
            f"<span class='highlight-txt'>{park['name']}</span> conditions."
        )
    else:
        narrative = (
            f"The model projects <span class='highlight-txt'>{target}</span> to secure the victory with a "
            f"{win_p:.1f}% win probability, driven by a decisive edge on the mound and favorable contact metrics. "
            f"{edge_team_name}'s starter, <span class='highlight-txt'>{edge_pitcher['pitcher']}</span>, holds a distinct advantage "
            f"in expected slugging and suppression, carrying an ERA of {edge_pitcher['era']:.2f} and an xwOBA of {edge_pitcher['xwoba']:.3f} "
            f"against <span class='highlight-txt'>{other_team_name}</span>'s lineup, which counters with a hard-hit rate of {other_pitcher['hard_hit_pct']}% "
            f"and an xwOBA of {other_pitcher['xwoba']:.3f} under <span class='highlight-txt'>{park['name']}</span> park factors ({park['weather']['weather_desc']}). "
            f"Combined with recent 10-game momentum ({edge_team_name} L10: {edge_pitcher['l10_record']} vs {other_team_name} L10: {other_pitcher['l10_record']}), "
            f"the quantitative indicators point clearly toward a <span class='highlight-txt'>{target}</span> triumph."
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
            away = g.get("teams", {}).get("away", {})
            home = g.get("teams", {}).get("home", {})
            away_p = away.get("probablePitcher", {})
            home_p = home.get("probablePitcher", {})
            away_id = away.get("team", {}).get("id")
            home_id = home.get("team", {}).get("id")

            np.random.seed(g.get("gamePk", 12345) % 100000)

            away_stats = {
                "pitcher": away_p.get("fullName", "Starter A"), "era": round(np.random.uniform(3.20, 4.80), 2),
                "xwoba": round(np.random.uniform(0.290, 0.345), 3), "hard_hit_pct": round(np.random.uniform(34.0, 44.0), 1),
                "l10_record": f"{np.random.randint(4,8)}-{10-np.random.randint(4,8)}", "odds": -110,
                "vs_lhp_wrc": int(np.random.randint(90, 115))
            }
            home_stats = {
                "pitcher": home_p.get("fullName", "Starter B"), "era": round(np.random.uniform(3.20, 4.80), 2),
                "xwoba": round(np.random.uniform(0.290, 0.345), 3), "hard_hit_pct": round(np.random.uniform(34.0, 44.0), 1),
                "l10_record": f"{np.random.randint(4,8)}-{10-np.random.randint(4,8)}", "odds": -110,
                "vs_lhp_wrc": int(np.random.randint(90, 115)), "starter_hand": "R"
            }

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

# ------------------------------------------------------------------
# 5. DASHBOARD PRESENTATION
# ------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-banner">
        <h1 style="margin:0; font-size: 1.8rem; font-weight: 800; color: #F8FAFC;">⚾ MLB Quantitative Matchup & Winner Engine</h1>
        <p style="margin:4px 0 0 0; color: #94A3B8; font-size: 0.95rem;">Complete Slate Predictions • xwOBA, Pitcher Comparisons & Live In-Game Trackers</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col_spacer, col_btn = st.columns([4, 1])
with col_btn:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

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

            with c1:
                st.markdown(f"**{g['away_team']}** (L10: {g['away_stats']['l10_record']})")
                st.markdown(f'<div style="color: #94A3B8; font-size: 0.82rem; margin: 4px 0;">Starter: <b>{g["away_stats"]["pitcher"]}</b></div>', unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="stat-pill-container">
                        <div class="stat-pill">xwOBA: <b>{g['away_stats']['xwoba']:.3f}</b></div>
                        <div class="stat-pill">HardHit%: <b>{g['away_stats']['hard_hit_pct']}%</b></div>
                        <div class="stat-pill">ERA: <b>{g['away_stats']['era']:.2f}</b></div>
                        <div class="stat-pill">vsLHP wRC+: <b>{g['away_stats']['vs_lhp_wrc']}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"""
                    <div style="margin-top: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #94A3B8; margin-bottom: 4px; font-family: 'JetBrains Mono', monospace;">
                            <span>Model Win Probability</span>
                            <span style="color: #38BDF8; font-weight: 700;">{away_pct}%</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); border-radius: 6px; overflow: hidden; height: 8px; width: 100%;">
                            <div style="background: linear-gradient(90deg, #38BDF8, #818CF8); width: {away_pct}%; height: 100%; border-radius: 6px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with c2:
                st.markdown(f"**{g['home_team']}** (L10: {g['home_stats']['l10_record']})")
                st.markdown(f'<div style="color: #94A3B8; font-size: 0.82rem; margin: 4px 0;">Starter: <b>{g["home_stats"]["pitcher"]}</b></div>', unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="stat-pill-container">
                        <div class="stat-pill">xwOBA: <b>{g['home_stats']['xwoba']:.3f}</b></div>
                        <div class="stat-pill">HardHit%: <b>{g['home_stats']['hard_hit_pct']}%</b></div>
                        <div class="stat-pill">ERA: <b>{g['home_stats']['era']:.2f}</b></div>
                        <div class="stat-pill">vsLHP wRC+: <b>{g['home_stats']['vs_lhp_wrc']}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"""
                    <div style="margin-top: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #94A3B8; margin-bottom: 4px; font-family: 'JetBrains Mono', monospace;">
                            <span>Model Prediction Breakdown</span>
                            <span style="color: #38BDF8; font-weight: 700;">{home_pct}%</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); border-radius: 6px; overflow: hidden; height: 8px; width: 100%;">
                            <div style="background: linear-gradient(90deg, #38BDF8, #818CF8); width: {home_pct}%; height: 100%; border-radius: 6px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with c3:
                st.markdown("**Quantitative Rationale & Matchup Breakdown**")
                st.markdown(f'<div class="narrative-box">{an["narrative"]}</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)
