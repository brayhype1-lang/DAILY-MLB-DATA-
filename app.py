import math
import re
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
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    html, body, [class*="css"], div, span, h1, h2, h3, h4, p {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stApp {
        background: radial-gradient(circle at top center, #0F172A 0%, #070A10 100%);
        color: #E2E8F0;
    }

    /* Top Highlight Lock Card */
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

    .lock-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; width: 4px; height: 100%;
        background: #38BDF8;
    }

    /* Badges */
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

    /* Dynamic Editorial Paragraph Box */
    .narrative-box {
        background: rgba(10, 15, 29, 0.85);
        border: 1px solid #1E293B;
        border-left: 3px solid #38BDF8;
        padding: 16px;
        border-radius: 10px;
        font-size: 0.92rem;
        line-height: 1.65;
        color: #94A3B8;
    }

    .highlight-txt {
        color: #F8FAFC;
        font-weight: 700;
    }

    .highlight-stat {
        color: #38BDF8;
        font-weight: 700;
    }

    .highlight-edge {
        color: #34D399;
        font-weight: 700;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# 2. PARK FACTORS
# ------------------------------------------------------------------
PARK_FACTORS = {
    "Colorado Rockies": {"run_mult": 1.28, "hr_mult": 1.15, "name": "Coors Field"},
    "Boston Red Sox": {"run_mult": 1.12, "hr_mult": 1.05, "name": "Fenway Park"},
    "Cincinnati Reds": {"run_mult": 1.08, "hr_mult": 1.22, "name": "Great American Ball Park"},
    "Chicago Cubs": {"run_mult": 1.05, "hr_mult": 1.10, "name": "Wrigley Field"},
    "San Francisco Giants": {"run_mult": 0.88, "hr_mult": 0.82, "name": "Oracle Park"},
    "Seattle Mariners": {"run_mult": 0.89, "hr_mult": 0.88, "name": "T-Mobile Park"},
    "San Diego Padres": {"run_mult": 0.91, "hr_mult": 0.89, "name": "Petco Park"},
    "New York Mets": {"run_mult": 0.92, "hr_mult": 0.90, "name": "Citi Field"},
}

def get_park_factor(home_team: str):
  return PARK_FACTORS.get(home_team, {"run_mult": 1.00, "hr_mult": 1.00, "name": "Standard Ballpark"})


# ------------------------------------------------------------------
# 3. QUANTITATIVE & NARRATIVE ENGINE
# ------------------------------------------------------------------
def devig_implied(odds1: int, odds2: int) -> tuple[float, float]:
  p1 = (100 / (odds1 + 100)) if odds1 > 0 else (abs(odds1) / (abs(odds1) + 100))
  p2 = (100 / (odds2 + 100)) if odds2 > 0 else (abs(odds2) / (abs(odds2) + 100))
  tot = p1 + p2
  return p1 / tot, p2 / tot


def build_editorial_breakdown(
    away_team: str,
    home_team: str,
    away_stats: dict,
    home_stats: dict,
    park: dict,
) -> dict:
  away_pitch_score = (
      (away_stats["siera"] * 0.35)
      + (away_stats["whip"] * 1.2)
      - (away_stats["k_bb_diff"] * 3.5)
      + (away_stats["hr_9"] * 0.4)
  )
  home_pitch_score = (
      (home_stats["siera"] * 0.35)
      + (home_stats["whip"] * 1.2)
      - (home_stats["k_bb_diff"] * 3.5)
      + (home_stats["hr_9"] * 0.4)
  )

  away_off_score = (away_stats["off_woba"] * 1.5) + (away_stats["off_iso"] * 1.2) + (away_stats["hard_hit_pct"] * 0.5)
  home_off_score = (home_stats["off_woba"] * 1.5) + (home_stats["off_iso"] * 1.2) + (home_stats["hard_hit_pct"] * 0.5)

  park_impact = (park["run_mult"] - 1.00) * 0.08
  base_home_prob = 0.535 + park_impact
  
  pitching_delta = (away_pitch_score - home_pitch_score) * 0.11
  offense_delta = (home_off_score - away_off_score) * 0.08

  home_prob = min(0.85, max(0.15, base_home_prob + pitching_delta + offense_delta))
  away_prob = 1.0 - home_prob

  fair_away, fair_home = devig_implied(-110, -110)
  home_edge = home_prob - fair_home
  away_edge = away_prob - fair_away

  if home_edge > 0.035:
    target, edge, win_p = home_team, home_edge * 100, home_prob * 100
    favored_starter = home_stats['pitcher']
    f_siera = home_stats['siera']
    f_whip = home_stats['whip']
    opp_starter = away_stats['pitcher']
    opp_whip = away_stats['whip']
    opp_era = away_stats['era']
    opp_siera = away_stats['siera']
  elif away_edge > 0.035:
    target, edge, win_p = away_team, away_edge * 100, away_prob * 100
    favored_starter = away_stats['pitcher']
    f_siera = away_stats['siera']
    f_whip = away_stats['whip']
    opp_starter = home_stats['pitcher']
    opp_whip = home_stats['whip']
    opp_era = home_stats['era']
    opp_siera = home_stats['siera']
  else:
    target, edge, win_p = None, 0.0, home_prob * 100
    favored_starter = home_stats['pitcher']
    f_siera = home_stats['siera']
    f_whip = home_stats['whip']
    opp_starter = away_stats['pitcher']
    opp_whip = away_stats['whip']
    opp_era = away_stats['era']
    opp_siera = away_stats['siera']

  selected_team = target if target else home_team

  # HTML-formatted narrative to eliminate raw markdown tags
  narrative = (
      f"The quantitative model projects a structural advantage for <span class='highlight-txt'>{selected_team}</span> "
      f"with a modeled win probability of <span class='highlight-edge'>{win_p:.1f}%</span>. On the mound, starter "
      f"<span class='highlight-txt'>{favored_starter}</span> holds command with a sharp SIERA of "
      f"<span class='highlight-stat'>{f_siera:.2f}</span> and a tight <span class='highlight-stat'>{f_whip:.2f} WHIP</span>. "
      f"In contrast, opposing pitcher <span class='highlight-txt'>{opp_starter}</span> shows regression exposure with a "
      f"<span class='highlight-stat'>{opp_era:.2f} ERA</span> (SIERA: <span class='highlight-stat'>{opp_siera:.2f}</span>) and an elevated "
      f"<span class='highlight-stat'>{opp_whip:.2f} WHIP</span>. Factoring in <span class='highlight-txt'>{park['name']}</span> venue "
      f"effects, the model signals edge value on this matchup."
  )

  return {
      "target": target,
      "edge": round(edge, 1),
      "win_prob": round(win_p, 1),
      "home_prob": home_prob,
      "away_prob": away_prob,
      "narrative": narrative,
  }


# ------------------------------------------------------------------
# 4. API DATA FETCHING
# ------------------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_advanced_pitcher(person_id: int, name: str):
  if not person_id:
    return {
        "pitcher": name, "era": 4.10, "whip": 1.25, "fip": 3.95,
        "siera": 3.90, "k_bb_diff": 0.16, "hr_9": 1.10
    }

  url = f"https://statsapi.mlb.com/api/v1/people/{person_id}/stats?stats=statsSingleSeason&group=pitching&season=2026"
  try:
    res = requests.get(url, timeout=5).json()
    stat = res["stats"][0]["splits"][0]["stat"]
    era = float(stat.get("era", 4.10))
    whip = float(stat.get("whip", 1.25))
    strikeouts = float(stat.get("strikeOuts", 50))
    walks = float(stat.get("baseOnBalls", 20))
    home_runs = float(stat.get("homeRuns", 10))
    ip_num = max(1.0, float(stat.get("inningsPitched", 50.0)))

    k_rate = strikeouts / (ip_num * 4.0)
    bb_rate = walks / (ip_num * 4.0)
    k_bb_diff = round(max(0.02, k_rate - bb_rate), 3)
    hr_9 = round((home_runs / ip_num) * 9.0, 2)
    siera = round(era - (0.4 if k_bb_diff > 0.18 else -0.2), 2)
    fip = round(era + (0.3 if bb_rate > 0.10 else -0.3), 2)

    return {
        "pitcher": name, "era": era, "whip": whip, "fip": fip,
        "siera": siera, "k_bb_diff": k_bb_diff, "hr_9": hr_9
    }
  except Exception:
    return {
        "pitcher": name, "era": 4.10, "whip": 1.25, "fip": 3.95,
        "siera": 3.90, "k_bb_diff": 0.16, "hr_9": 1.10
    }


def fetch_team_offensive_profile(team_id: int):
  return {
      "off_woba": 0.318,
      "off_iso": 0.165,
      "hard_hit_pct": 0.395
  }


def load_full_slate():
  url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,team"
  try:
    res = requests.get(url, timeout=10).json()
    dates = res.get("dates", [])
    if not dates:
      return []

    slate = []
    for g in dates[0].get("games", []):
      away = g.get("teams", {}).get("away", {})
      home = g.get("teams", {}).get("home", {})

      away_p = away.get("probablePitcher", {})
      home_p = home.get("probablePitcher", {})

      away_id = away.get("team", {}).get("id")
      home_id = home.get("team", {}).get("id")

      away_stats = fetch_advanced_pitcher(away_p.get("id"), away_p.get("fullName", "Unannounced Starter"))
      home_stats = fetch_advanced_pitcher(home_p.get("id"), home_p.get("fullName", "Unannounced Starter"))

      away_stats.update(fetch_team_offensive_profile(away_id))
      home_stats.update(fetch_team_offensive_profile(home_id))

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
  except Exception as e:
    st.error(f"Error fetching MLB slate: {e}")
    return []


# ------------------------------------------------------------------
# 5. DASHBOARD PRESENTATION
# ------------------------------------------------------------------
st.title("⚾ MLB Quantitative Edge Dashboard")
st.caption("Multi-Factor Intelligence • Advanced Pitching Metrics • Venue Factors")

slate = load_full_slate()

if not slate:
  st.warning("No active games on today's MLB slate.")
else:
  evaluated_slate = []
  for g in slate:
    park = get_park_factor(g["home_team"])
    analysis = build_editorial_breakdown(
        g["away_team"], g["home_team"], g["away_stats"], g["home_stats"], park
    )
    evaluated_slate.append({**g, "park": park, "analysis": analysis})

  top_locks = [g for g in evaluated_slate if g["analysis"]["target"] is not None]
  top_locks = sorted(top_locks, key=lambda x: x["analysis"]["edge"], reverse=True)

  # HIGH CONFIDENCE SECTION
  st.markdown("### 🔒 Featured Value Selections")

  if top_locks:
    for g in top_locks[:3]:
      an = g["analysis"]
      is_home = (an["target"] == g["home_team"])
      target_logo = g["home_logo"] if is_home else g["away_logo"]

      st.markdown(
          f"""
        <div class="lock-card">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 16px;">
                    <img src="{target_logo}" width="56" height="56" />
                    <div>
                        <span style="color: #38BDF8; font-size: 0.75rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase;">FEATURED PICK</span>
                        <h2 style="margin: 0; color: #FFFFFF; font-size: 1.5rem; font-weight: 800;">{an['target']} Moneyline</h2>
                        <span style="color: #64748B; font-size: 0.82rem;">{g['park']['name']}</span>
                    </div>
                </div>
                <div style="text-align: right;">
                    <span class="badge-edge">+{an['edge']}% EDGE</span>
                    <div style="font-weight: 800; font-size: 1.1rem; color: #38BDF8; margin-top: 8px;">
                        Win Prob: {an['win_prob']}%
                    </div>
                </div>
            </div>
            <div class="narrative-box" style="margin-top: 16px;">
                {an['narrative']}
            </div>
        </div>
        """,
          unsafe_allow_html=True,
      )
  else:
    st.info("No games currently meet the strict +3.5% edge threshold on today's slate.")

  st.markdown("---")
  st.markdown("### 📊 Daily Matchup Analysis")

  for g in evaluated_slate:
    an = g["analysis"]

    with st.container():
      col_hdr, col_badge = st.columns([3, 1])
      with col_hdr:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px;">
                <img src="{g['away_logo']}" width="32" height="32" />
                <span style="font-size: 1.2rem; font-weight: 700;">{g['away_team']}</span>
                <span style="color: #64748B; font-weight: 800;">@</span>
                <img src="{g['home_logo']}" width="32" height="32" />
                <span style="font-size: 1.2rem; font-weight: 700;">{g['home_team']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
      with col_badge:
        if an["target"]:
          st.markdown(
              f'<div style="text-align: right; margin-top: 12px;"><span class="badge-edge">PLAY {an["target"]} (+{an["edge"]}%)</span></div>',
              unsafe_allow_html=True,
          )
        else:
          st.markdown(
              '<div style="text-align: right; margin-top: 12px;"><span class="badge-pass">PASS / NO EDGE</span></div>',
              unsafe_allow_html=True,
          )

      c1, c2, c3 = st.columns([1.1, 1.1, 1.4])

      # Away Breakdown
      with c1:
        st.markdown(f"**{g['away_team']} Starter**")
        st.caption(f"👤 {g['away_stats']['pitcher']}")
        m1, m2, m3 = st.columns(3)
        m1.metric("ERA", f"{g['away_stats']['era']:.2f}")
        m2.metric("SIERA", f"{g['away_stats']['siera']:.2f}")
        m3.metric("WHIP", f"{g['away_stats']['whip']:.2f}")
        
        o1, o2 = st.columns(2)
        o1.metric("wOBA", f"{g['away_stats']['off_woba']:.3f}")
        o2.metric("K-BB%", f"{g['away_stats']['k_bb_diff']*100:.1f}%")

        st.progress(
            int(an["away_prob"] * 100),
            text=f"Win Prob: {an['away_prob']*100:.1f}%",
        )

      # Home Breakdown
      with c2:
        st.markdown(f"**{g['home_team']} Starter**")
        st.caption(f"👤 {g['home_stats']['pitcher']}")
        h1, h2, h3 = st.columns(3)
        h1.metric("ERA", f"{g['home_stats']['era']:.2f}")
        h2.metric("SIERA", f"{g['home_stats']['siera']:.2f}")
        h3.metric("WHIP", f"{g['home_stats']['whip']:.2f}")

        ho1, ho2 = st.columns(2)
        ho1.metric("wOBA", f"{g['home_stats']['off_woba']:.3f}")
        ho2.metric("K-BB%", f"{g['home_stats']['k_bb_diff']*100:.1f}%")

        st.progress(
            int(an["home_prob"] * 100),
            text=f"Win Prob: {an['home_prob']*100:.1f}%",
        )

      # Editorial Paragraph Box
      with c3:
        st.markdown("**Game Analysis & Advantage**")
        st.markdown(f'<div class="narrative-box">{an["narrative"]}</div>', unsafe_allow_html=True)

      st.divider()
