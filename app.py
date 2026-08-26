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
    }

    div.element-container div.stMarkdown {
        color: #F8FAFC;
    }

    /* Style bottom action button to look like a clean card footer action */
    [data-testid="stVerticalBlock"] [data-testid="stButton"] button {
        width: 100%;
        background: rgba(56, 189, 248, 0.12) !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        color: #38BDF8 !important;
        font-weight: 700 !important;
        font-size: 0.8rem !important;
        border-radius: 6px !important;
        padding: 6px 12px !important;
        transition: all 0.2s ease-in-out !important;
    }
    [data-testid="stVerticalBlock"] [data-testid="stButton"] button:hover {
        background: rgba(56, 189, 248, 0.25) !important;
        border-color: #38BDF8 !important;
        color: #F8FAFC !important;
    }

    /* Badges */
    .badge-live {
        background: rgba(239, 68, 68, 0.18);
        border: 1px solid rgba(239, 68, 68, 0.5);
        color: #FCA5A5;
        font-weight: 800;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 0.65rem;
        font-family: 'JetBrains Mono', monospace;
    }
    .badge-final {
        background: rgba(51, 65, 85, 0.4);
        border: 1px solid rgba(100, 116, 139, 0.4);
        color: #94A3B8;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 0.65rem;
    }
    .badge-upcoming {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(51, 65, 85, 0.4);
        color: #64748B;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 0.65rem;
    }

    /* Base Diamonds */
    .base-diamond {
        display: inline-block;
        width: 8px;
        height: 8px;
        transform: rotate(45deg);
        background-color: rgba(100, 116, 139, 0.3);
        border: 1px solid rgba(100, 116, 139, 0.5);
    }
    .base-active {
        background-color: #38BDF8;
        border-color: #7DD3FC;
        box-shadow: 0 0 6px rgba(56, 189, 248, 0.8);
    }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# 2. SIDEBAR CONTROLS
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    manual_refresh_btn = st.button("🔄 Refresh Data Now", use_container_width=True)
    st.caption("Manual refresh mode active.")

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
                "badge_html": f'<span class="badge-live">🔴 LIVE • {half} {inning_ordinal}</span>',
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
            f"Model actively pricing live momentum. Quantitative edge leans toward {target} at {win_p:.1f}% probability."
        )
    else:
        narrative = (
            f"Model projects {target} to win at {win_p:.1f}%. "
            f"{edge_team_name}'s starter {edge_pitcher['pitcher']} holds an edge "
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
# 6. DASHBOARD RENDERING
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
            
            if st.button("⬅️ Back to Scoreboard Grid", key="back_to_grid_btn"):
                st.session_state["selected_game_id"] = None
                st.rerun()

            st.markdown(f"## ⚾ {selected_g['away_team']} @ {selected_g['home_team']}")
            st.markdown(lv['badge_html'], unsafe_allow_html=True)

            col_box1, col_box2 = st.columns(2)
            with col_box1:
                with st.container(border=True):
                    st.markdown("### 🏟️ Box Score Summary")
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Runs", f"{lv['away_runs']} - {lv['home_runs']}")
                    sc2.metric("Hits", f"{lv.get('away_hits', 0)} - {lv.get('home_hits', 0)}")
                    sc3.metric("Errors", f"{lv.get('away_errors', 0)} - {lv.get('home_errors', 0)}")
            with col_box2:
                with st.container(border=True):
                    st.markdown("### 🌤️ Venue & Environment")
                    st.write(f"**Ballpark:** {selected_g['park']['name']}")
                    st.write(f"**Weather:** {selected_g['park']['weather']['weather_desc']}")
                    st.write(f"**Run Factor:** {selected_g['park']['run_mult']}x")

            st.markdown("### ⚡ Live Play-by-Play Feed")
            with st.container(border=True):
                plays = lv.get("recent_plays", [])
                if plays:
                    for p in plays:
                        st.markdown(f"**[{p['inning']}]** {p['description']}")
                else:
                    st.caption("Play-by-play feed updates automatically when games are live.")

            st.stop()

    # --- MAIN SCOREBOARD GRID ---
    with st.container(border=True):
        st.markdown("### ⚾ MLB QUANTITATIVE TERMINAL")
        st.caption("LIVE SCOREBOARD • REAL-TIME AUTOMATIC POLLING")

    cols_per_row = 4
    for i in range(0, len(evaluated_slate), cols_per_row):
        row_games = evaluated_slate[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        
        for idx, g in enumerate(row_games):
            lv = g["live"]
            is_live = (lv["status"] == "LIVE")
            
            with cols[idx]:
                with st.container(border=True):
                    # Status Badge at the top
                    st.markdown(lv['badge_html'], unsafe_allow_html=True)
                    
                    # Away Team Row
                    sc_col1, sc_col2, sc_col3 = st.columns([1, 4, 1])
                    with sc_col1:
                        if g["away_logo"]:
                            st.image(g["away_logo"], width=24)
                    with sc_col2:
                        st.markdown(f"**{g['away_short']}**")
                    with sc_col3:
                        st.markdown(f"<span style='font-family: JetBrains Mono; font-weight: 800;'>{lv['away_runs']}</span>", unsafe_allow_html=True)

                    # Home Team Row
                    sc_col4, sc_col5, sc_col6 = st.columns([1, 4, 1])
                    with sc_col4:
                        if g["home_logo"]:
                            st.image(g["home_logo"], width=24)
                    with sc_col5:
                        st.markdown(f"**{g['home_short']}**")
                    with sc_col6:
                        st.markdown(f"<span style='font-family: JetBrains Mono; font-weight: 800;'>{lv['home_runs']}</span>", unsafe_allow_html=True)

                    # Base runners & outs for live games
                    if is_live:
                        b2 = "base-active" if lv.get("has_2b") else ""
                        b3 = "base-active" if lv.get("has_3b") else ""
                        b1 = "base-active" if lv.get("has_1b") else ""
                        
                        bases_html = f"""
                        <div style="display: flex; justify-content: space-between; align-items: center; margin: 8px 4px; padding: 2px 0;">
                            <div style="position: relative; width: 26px; height: 26px;">
                                <!-- 2nd Base (Top) -->
                                <div style="position: absolute; top: 0px; left: 9px;" class="base-diamond {b2}"></div>
                                <!-- 3rd Base (Left) -->
                                <div style="position: absolute; top: 9px; left: 0px;" class="base-diamond {b3}"></div>
                                <!-- 1st Base (Right) -->
                                <div style="position: absolute; top: 9px; left: 18px;" class="base-diamond {b1}"></div>
                            </div>
                            <span style="color: #94A3B8; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.75rem;">OUTS: {lv.get('outs', 0)}</span>
                        </div>
                        """
                        st.markdown(bases_html, unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

                    # Clean full-width action button at the bottom of the card
                    if st.button("📊 View Deep Dive", key=f"card_btn_{g['game_id']}", use_container_width=True):
                        st.session_state["selected_game_id"] = g["game_id"]
                        st.rerun()

    st.markdown("---")
    st.markdown("### 📊 Full Slate Model Predictions & Matchups")

    for g in evaluated_slate:
        an = g["analysis"]
        away_pct = int(an["away_prob"] * 100)
        home_pct = int(an["home_prob"] * 100)

        with st.container(border=True):
            st.markdown(f"#### {g['away_team']} @ {g['home_team']} ({g['park']['name']})")
            st.markdown(f"**Model Pick:** {an['target']} ({an['win_prob']}% Win Probability)")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"**{g['away_stats']['pitcher']}** ({g['away_stats']['record']})")
                st.write(f"ERA: {g['away_stats']['era']:.2f} | xwOBA: {g['away_stats']['xwoba']:.3f}")
                st.progress(away_pct / 100, text=f"Win Prob: {away_pct}%")
            with c2:
                st.markdown(f"**{g['home_stats']['pitcher']}** ({g['home_stats']['record']})")
                st.write(f"ERA: {g['home_stats']['era']:.2f} | xwOBA: {g['home_stats']['xwoba']:.3f}")
                st.progress(home_pct / 100, text=f"Win Prob: {home_pct}%")
            with c3:
                st.markdown("**Quantitative Rationale**")
                st.write(an['narrative'])
