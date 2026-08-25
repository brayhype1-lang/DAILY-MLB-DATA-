import json
import streamlit as st

st.set_page_config(
    page_title="MLB Quantitative Edge Model", page_icon="⚡", layout="wide"
)

st.title("⚡ MLB Algorithmic Edge & Prop Dashboard")

try:
  with open("daily_mlb_data.json", "r") as f:
    payload = json.load(f)

  st.caption(f"Last Model Sync: **{payload.get('last_updated')}**")
  slate = payload.get("slate", [])

  if slate:
    # ------------------ TOP SLATE HIGHLIGHTS ------------------
    st.markdown("## 🎯 Top High-Confidence Locks Today")

    high_conf_games = [
        g for g in slate if g.get("confidence") == "HIGH"
    ]

    if high_conf_games:
      c1, c2 = st.columns(2)
      for idx, game in enumerate(high_conf_games[:4]):
        col = c1 if idx % 2 == 0 else c2
        with col:
          st.success(
              f"🔥 **{game.get('recommended_bet', 'Pass')}**\n\nMatchup:"
              f" {game.get('away_team')} @ {game.get('home_team')}"
          )
    else:
      st.info(
          "No extreme pitch-mismatch locks found today. Standard slate model"
          " active below."
      )

    st.markdown("---")

    # ------------------ GAME BY GAME METRICS ------------------
    st.markdown("## 📊 Full Slate Model Projections")

    for game in slate:
      away_prob = game.get("away_prob", 50.0)
      home_prob = game.get("home_prob", 50.0)

      with st.expander(
          f"⚾ {game.get('away_team')} ({away_prob}%) @"
          f" {game.get('home_team')} ({home_prob}%)"
      ):

        col1, col2, col3 = st.columns(3)

        with col1:
          st.markdown(f"### 🔵 {game.get('away_team')}")
          st.write(f"**Pitcher:** {game.get('away_pitcher')}")
          st.write(
              f"**ERA:** {game.get('away_era')} | **WHIP:**"
              f" {game.get('away_whip')}"
          )
          st.progress(
              int(away_prob), text=f"Win Probability: {away_prob}%"
          )

        with col2:
          st.markdown(f"### 🔴 {game.get('home_team')}")
          st.write(f"**Pitcher:** {game.get('home_pitcher')}")
          st.write(
              f"**ERA:** {game.get('home_era')} | **WHIP:**"
              f" {game.get('home_whip')}"
          )
          st.progress(
              int(home_prob), text=f"Win Probability: {home_prob}%"
          )

        with col3:
          st.markdown("### 🎯 Model Outputs")
          st.write(
              f"**Primary Angle:** {game.get('recommended_bet', 'Pass')}"
          )
          st.write(
              f"**Model Confidence:** {game.get('confidence', 'MEDIUM')}"
          )

  else:
    st.warning("No games found on today's slate.")

except FileNotFoundError:
  st.error(
      "Data payload missing. Trigger the workflow in your GitHub Actions tab!"
  )
