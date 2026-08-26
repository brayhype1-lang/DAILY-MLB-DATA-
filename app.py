# ------------------------------------------------------------------
# 5. DASHBOARD PRESENTATION & COMPACT SCORE CARDS
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

    st.markdown(
        """
        <div class="hero-banner">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <div>
                    <h1 style="margin:0; font-size: 1.5rem; font-weight: 900; color: #F8FAFC;">⚾ MLB QUANTITATIVE INTELLIGENCE</h1>
                    <p style="margin:2px 0 0 0; color: #38BDF8; font-size: 0.8rem; font-family: 'JetBrains Mono', monospace;">LIVE SCOREBOARD • SMART SORTED</p>
                </div>
                <div>
                    <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; padding: 4px 10px; border-radius: 8px; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace;">
                        🟢 LIVE
                    </span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Compact grid layout
    cols_per_row = 5
    for i in range(0, len(evaluated_slate), cols_per_row):
        row_games = evaluated_slate[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        
        for idx, g in enumerate(row_games):
            lv = g["live"]
            b1 = "background: #38BDF8; box-shadow: 0 0 4px #38BDF8;" if lv.get("has_1b") else "background: rgba(255,255,255,0.15);"
            b2 = "background: #38BDF8; box-shadow: 0 0 4px #38BDF8;" if lv.get("has_2b") else "background: rgba(255,255,255,0.15);"
            b3 = "background: #38BDF8; box-shadow: 0 0 4px #38BDF8;" if lv.get("has_3b") else "background: rgba(255,255,255,0.15);"

            # Clean, compact HTML card template
            card_html = f"""
            <div style="background: linear-gradient(145deg, rgba(11, 22, 42, 0.95), rgba(5, 13, 26, 0.98)); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 10px; padding: 8px 10px; margin-bottom: 10px; font-family: 'Inter', sans-serif;">
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.65rem; font-family: 'JetBrains Mono', monospace; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 4px; margin-bottom: 6px;">
                    <span style="color: #94A3B8;">{lv['inning_str']}</span>
                    <span style="color: #38BDF8;">{lv['status']}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; font-weight: 600; color: #F8FAFC; margin-bottom: 4px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <img src="{g['away_logo']}" width="15" height="15" style="object-fit: contain;" />
                        <span>{g['away_short']}</span>
                    </div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800;">{lv['away_runs']}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; font-weight: 600; color: #F8FAFC; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <img src="{g['home_logo']}" width="15" height="15" style="object-fit: contain;" />
                        <span>{g['home_short']}</span>
                    </div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800;">{lv['home_runs']}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.65rem; font-family: 'JetBrains Mono', monospace; background: rgba(15, 23, 42, 0.8); padding: 3px 6px; border-radius: 4px; color: #94A3B8;">
                    <div style="display: flex; align-items: center; gap: 3px;">
                        <span>BASES</span>
                        <span style="display: inline-flex; gap: 2px;">
                            <span style="width: 5px; height: 5px; transform: rotate(45deg); {b2}"></span>
                            <span style="width: 5px; height: 5px; transform: rotate(45deg); {b3}"></span>
                            <span style="width: 5px; height: 5px; transform: rotate(45deg); {b1}"></span>
                        </span>
                    </div>
                    <div>OUTS: <b style="color: #F8FAFC;">{lv['outs']}</b></div>
                </div>
            </div>
            """
            with cols[idx]:
                st.markdown(card_html, unsafe_allow_html=True)
