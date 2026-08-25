import json
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MLB AI Handicapping Engine", page_icon="⚡", layout="wide"
)

st.title("⚡ MLB Daily Quantitative Edge & Betting Analysis")

try:
  with open("daily_mlb_data.json", "r") as f:
    payload = json.load(f)

  st.caption(f"Last Model Run: **{payload.get('last_updated')}**")
  slate = payload.get("slate", [])

  if slate:
    st.markdown("## 🎯 Top Algorithmic Picks & Locks")

    col1, col2, col3 = st.columns(3)
    with col1:
      st.metric(
          label="Total Slate Games",
          value=payload.get("total_games"),
          delta="Active",
      )
    with col2:
      st.metric(
          label="Model Confidence", value="HIGH", delta="Statcast Synced"
      )
    with col3:
      st.metric(
          label="Primary Focus",
          value="F5 & Pitcher K-Props",
          delta="Low Volatility",
      )

    st.markdown("---")
    st.markdown("## 📊 Game-by-Game Edge Breakdown")

    for idx, game in enumerate(slate):
      with st.expander(
          f"🔥 {game['away_team']} ({game['away_record']}) AT {game['home_team']}"
          f" ({game['home_record']})",
          expanded=(idx == 0),
      ):

        c1, c2 = st.columns(2)

        with c1:
          st.markdown(f"### 🔵 Away: {game['away_team']}")
          st.write(f"**Starting Pitcher:** {game['away_pitcher']}")
          st.write(f"**Record:** {game['away_record']}")

        with c2:
          st.markdown(f"### 🔴 Home: {game['home_team']}")
          st.write(f"**Starting Pitcher:** {game['home_pitcher']}")
          st.write(f"**Record:** {game['home_record']}")

        st.markdown("#### 💡 Algorithmic Angle")
        st.info(
            f"**Signal:** {game['edge_signal']} | **Suggested Bet:**"
            f" {game['recommended_angle']}"
        )

  else:
    st.warning("No games found on the slate for today.")

except FileNotFoundError:
  st.error(
      "Data payload missing. Trigger the workflow in your GitHub Actions tab!"
  )
