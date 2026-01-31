import time
from itertools import combinations
from typing import Dict, List, Optional, Tuple
 
import pandas as pd
import streamlit as st
from optimization_model import LineupOptimizer
 
 
# ----------------------------
# Page setup
# ----------------------------
st.set_page_config(page_title="Coach Dashboard", layout="wide")
 
 
# ----------------------------
# Load data (your real CSVs)
# ----------------------------
@st.cache_data
def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    players = pd.read_csv("Data/player_data.csv")
    stints = pd.read_csv("Data/stint_data.csv")
    return players, stints
 
 
players_raw, stints_df = load_data()
 
# Normalize player columns
# Expected in your file: player, rating
players_df = players_raw.rename(columns={"player": "player_id", "rating": "disability_score"}).copy()
players_df["country"] = players_df["player_id"].astype(str).str.split("_").str[0]
 
 
# ----------------------------
# Compute a baseline "value score" from stints
# value_score = (goal differential while on court) / minutes
# (we can replace later if you already have your own score)
# ----------------------------
@st.cache_data
def compute_value_scores(players_df: pd.DataFrame, stints_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in stints_df.iterrows():
        minutes = float(r.get("minutes", 0))
        if minutes <= 0:
            continue
 
        h_diff = float(r["h_goals"]) - float(r["a_goals"])
        a_diff = -h_diff
 
        home_players = [r["home1"], r["home2"], r["home3"], r["home4"]]
        away_players = [r["away1"], r["away2"], r["away3"], r["away4"]]
 
        for p in home_players:
            rows.append({"player_id": p, "diff": h_diff, "minutes": minutes})
        for p in away_players:
            rows.append({"player_id": p, "diff": a_diff, "minutes": minutes})
 
    long_df = pd.DataFrame(rows)
    out = players_df.copy()
 
    if long_df.empty:
        out["value_score"] = 0.0
        return out
 
    agg = long_df.groupby("player_id", as_index=False).agg(
        total_diff=("diff", "sum"),
        total_minutes=("minutes", "sum"),
    )
    agg["value_score"] = agg["total_diff"] / agg["total_minutes"].replace(0, 1)
 
    out = out.merge(agg[["player_id", "value_score"]], on="player_id", how="left")
    out["value_score"] = out["value_score"].fillna(0.0)
 
    # scale to -10..10 so it's readable
    mx = out["value_score"].abs().max()
    if mx and mx > 0:
        out["value_score"] = (out["value_score"] / mx) * 10
 
    return out
 
 
players_df = compute_value_scores(players_df, stints_df)

# Initialize the optimization model
@st.cache_resource
def load_optimizer():
    """Load optimizer (cached for performance)"""
    try:
        return LineupOptimizer()
    except Exception as e:
        st.subheader("Stint History (current game)") 
        game_hist = stints_df.copy() 
        if "game_id" in stints_df.columns: 
            game_hist = stints_df[stints_df["game_id"] == st.session_state.selected_game_id].copy() 
 
        def _norm_team(s: str) -> str: 
            s = str(s or "").strip().lower() 
            return s.replace(" ", "") 
 
        hist = game_hist 
        if {"h_team", "a_team"}.issubset(game_hist.columns): 
            country_norm = _norm_team(st.session_state.country) 
            game_hist["h_team_norm"] = game_hist["h_team"].apply(_norm_team) 
            game_hist["a_team_norm"] = game_hist["a_team"].apply(_norm_team) 
            hist = game_hist[(game_hist["h_team_norm"] == country_norm) | (game_hist["a_team_norm"] == country_norm)] 
            if hist.empty: 
                # Fallback: substring match (handles code vs full name differences) 
                hist = game_hist[ 
                    game_hist["h_team_norm"].str.contains(country_norm, na=False) | 
                    game_hist["a_team_norm"].str.contains(country_norm, na=False) 
                ] 
 
        if hist.empty: 
            st.info("No stints found for this country in the selected game.") 
# ----------------------------
def reset_all():
    # Clear all session keys
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    # Explicitly reset stint history and availability defaults
    try:
        all_ids = players_df["player_id"].tolist()
    except Exception:
        all_ids = []
    st.session_state.live_stints = []
    st.session_state.availability = {pid: True for pid in all_ids}
    st.session_state.fatigue = {pid: 100 for pid in all_ids}
 
 
def ensure_state(all_ids: List[str], countries: List[str], game_ids: List[int]):
    if "country" not in st.session_state:
        st.session_state.country = countries[0] if countries else ""
 
    if "selected_game_id" not in st.session_state:
        st.session_state.selected_game_id = game_ids[0] if game_ids else 0
 
    if "availability" not in st.session_state:
        st.session_state.availability = {pid: True for pid in all_ids}
 
    if "fatigue" not in st.session_state:
        st.session_state.fatigue = {pid: 100 for pid in all_ids}  # Start at 100 (fresh, t_j = 1.0)
    
    if "pre_selected" not in st.session_state:
        st.session_state.pre_selected = []  # Pre-selected players set S
    
    if "stint_duration" not in st.session_state:
        st.session_state.stint_duration = 0.0  # Duration in minutes
 
    if "lineup" not in st.session_state:
        st.session_state.lineup = []  # 4 ids
 
    # scoreboard + timers
    if "home_team" not in st.session_state:
        st.session_state.home_team = "H"
    if "away_team" not in st.session_state:
        st.session_state.away_team = "A"
    if "home_score" not in st.session_state:
        st.session_state.home_score = 0
    if "away_score" not in st.session_state:
        st.session_state.away_score = 0
 
    if "game_start" not in st.session_state:
        st.session_state.game_start = None
    if "stint_start" not in st.session_state:
        st.session_state.stint_start = None
 
    if "live_stints" not in st.session_state:
        st.session_state.live_stints = []
 
    if "last_opt" not in st.session_state:
        st.session_state.last_opt = None
 
 
def fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "00:00"
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
 
 
def elapsed(ts: Optional[float]) -> Optional[float]:
    if ts is None:
        return None
    return time.time() - ts


def update_fatigue_after_stint(stint_duration_seconds: float, lineup: List[str]) -> Dict[str, float]:
    """
    Update fatigue levels after a stint based on duration and player participation.
    Works with 0-100 scale where 100 = fresh, 0 = exhausted.
    
    Internally uses Module 1 433 update rules on t_j scale (per MINUTE), then converts back.
    
    For players on court (in lineup): t_new = t_old - (0.02 × D_minutes)
    For players on bench: t_new = t_old + (0.01 × D_minutes)
    
    Where D_minutes is duration in MINUTES.
    
    Bounds: 0.3 ≤ t_j ≤ 1.0 (which maps to 0 ≤ fatigue ≤ 100)
    
    Example: 5-minute stint
    - On court player: t_new = t_old - (0.02 × 5) = t_old - 0.1
    - Bench player: t_new = t_old + (0.01 × 5) = t_old + 0.05
    """
    # Convert seconds to minutes
    stint_duration_minutes = stint_duration_seconds / 60.0
    
    updated_fatigue = st.session_state.fatigue.copy()
    
    for player_id in st.session_state.fatigue.keys():
        # Convert 0-100 scale to t_j
        fatigue_level = st.session_state.fatigue[player_id]
        t_old = (fatigue_level / 100.0) * 0.7 + 0.3
        
        if player_id in lineup:
            # Player was on court: loses energy
            t_new = t_old - (0.02 * stint_duration_minutes)
        else:
            # Player was on bench: recovers energy
            t_new = t_old + (0.01 * stint_duration_minutes)
        
        # Enforce bounds
        t_new = max(0.3, min(1.0, t_new))
        
        # Convert back to 0-100 scale: (t_j - 0.3) / 0.7 * 100
        new_fatigue_level = ((t_new - 0.3) / 0.7) * 100
        new_fatigue_level = max(0, min(100, new_fatigue_level))
        updated_fatigue[player_id] = new_fatigue_level
    
    return updated_fatigue

 
 
# ----------------------------
# Placeholder optimizer (works now)
# - picks best feasible lineup by value_score - fatigue penalty
# - respects disability cap
# Later: replace this function call with your real optimizer file
# ----------------------------
def optimize_lineup(
    team_df: pd.DataFrame,
    availability: Dict[str, bool],
    fatigue_levels: Dict[str, float],
    home_score: float,
    away_score: float,
    pre_selected: List[str] = None,
) -> Dict:
    """
    Optimize lineup using the Gurobi-based Module 1 433 model.
    Uses current availability, fatigue (0-100), and scoreboard values.
    """
    if pre_selected is None:
        pre_selected = []
    opt = load_optimizer()
    if opt is None:
        return {
            "lineup": [],
            "objective": 0.0,
            "disability_sum": 0.0,
            "breakdown": []
        }

    try:
        result = opt.optimize_lineup(
            team_df=team_df,
            availability=availability,
            fatigue_levels=fatigue_levels,
            home_score=home_score,
            away_score=away_score,
            pre_selected=pre_selected,
            lineup_size=4,
        )
        return result
    except RuntimeError as e:
        st.error(f"Optimization failed: {e}")
        return {
            "lineup": [],
            "objective": 0.0,
            "disability_sum": 0.0,
            "breakdown": []
        }
 
 
# ----------------------------
# Init state
# ----------------------------
all_ids = players_df["player_id"].tolist()
countries = sorted(players_df["country"].unique().tolist())
game_ids = sorted(stints_df["game_id"].unique().tolist()) if len(stints_df) else []
ensure_state(all_ids, countries, game_ids)
 
 
# ----------------------------
# Header row: title left, controls right
# ----------------------------
header_left, header_right = st.columns([0.7, 0.3])
with header_left:
    st.title("🏉 Coach Dashboard")
    st.info(
        "Select the country you are coaching to scope players for the lineup. The optimizer will suggest the optimal 4-player lineup."
        "Start by toggling player availability and click Start Game. This will suggest your initial lineup. Feel free to pre-select players for the lineup and click 'Optimize' to re-optimize this lineup."
        "To enable fatigue tracking, start and end stints during the game. The optimizer will adjust player fatigue levels accordingly and suggest lineups based on current fatigue."
    )
with header_right:
    st.session_state.country = st.selectbox(
        "Country",
        countries,
        index=countries.index(st.session_state.country) if st.session_state.country in countries else 0,
    )
    if st.button("🧹 Clear / Reset", use_container_width=True):
        reset_all()
        st.rerun()

st.divider()

# ============================
# LINEUP SUGGESTION BANNER (AI-Recommended)
# ============================
if st.session_state.last_opt and st.session_state.last_opt.get("lineup"):
    rec_lineup = st.session_state.last_opt.get("lineup", [])
    rec_obj = st.session_state.last_opt.get("objective", 0.0)
    rec_alpha = st.session_state.last_opt.get("strategy_weight_alpha", 1.0)
    rec_notes = "This is the optimizer-recommended lineup based on current player availability and fatigue levels. A strategy scoring weight of 1 is the default but a score of 0 indicates the team is losing and must prioritize offence. A score of 2 indicates the team is winning comfortably and should prioritize defence."
    
    st.markdown("### 🎯 Optimizer-Recommended Lineup")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.info(f"**{' - '.join(rec_lineup)}**")
    with col2:
        st.metric("Optimal Lineup Score Value (Z)", f"{rec_obj:.2f}")
    with col3:
        st.metric("Strategy Scoring Weight (α)", f"{rec_alpha:.1f}")
    st.caption(rec_notes)
    st.divider()

# ============================
# MAIN LAYOUT
# ============================
left, right = st.columns([1.65, 1.0])
 
team_df = players_df[players_df["country"] == st.session_state.country].copy()
team_ids = team_df["player_id"].tolist()
 
 
# ----------------------------
# LEFT PANEL (country + players + stint history)
# ----------------------------
with left:
    st.subheader("Players")
 
    # Controls in expander to keep clean
    with st.expander("Set Player Availability", expanded=True):
        st.caption("Toggle availability for each player.")
        for pid in team_ids:
            cols = st.columns([1.2, 1.0])
            with cols[0]:
                st.session_state.availability[pid] = st.checkbox(
                    pid,
                    value=st.session_state.availability.get(pid, True),
                    key=f"avail_{pid}",
                )
            with cols[1]:
                st.session_state.fatigue[pid] = st.session_state.fatigue.get(pid, 100.0)
                f = float(st.session_state.fatigue[pid])
                pcols = st.columns([4, 1])
                with pcols[0]:
                    st.progress(f / 100.0)
                with pcols[1]:
                    color = "#16a34a" if f >= 80 else ("#f59e0b" if f >= 50 else "#dc2626")
                    st.markdown(f"<div style='color:{color}; font-weight:600; text-align:right'>{int(f)}/100</div>", unsafe_allow_html=True)
 
    # Player table
    table = team_df.copy()
    table["available"] = table["player_id"].map(lambda x: st.session_state.availability.get(x, True))
    table["fatigue"] = table["player_id"].map(lambda x: st.session_state.fatigue.get(x, 0.0))
 
    st.dataframe(
        table[["player_id", "value_score", "disability_score", "available"]]
        .sort_values(["available", "value_score"], ascending=[False, False]),
        use_container_width=True,
        hide_index=True,
    )
 
    st.divider()
        
    st.markdown("**Current Stint Runtime**")
    st.info("Step 3: Use the buttons below to start and end stints during the game. Ending a stint will save it and update player fatigue levels accordingly.")
    st.metric("Runtime", fmt_time(elapsed(st.session_state.stint_start)))
 
    s1, s2 = st.columns(2)
    with s1:
        if st.button("▶️ Start Stint", use_container_width=True):
            if st.session_state.stint_start is None:
                st.session_state.stint_start = time.time()
    with s2:
        if st.button("✅ End + Save", use_container_width=True):
            dur = elapsed(st.session_state.stint_start)
            elapsed_seconds = dur
            stint_duration_minutes = elapsed_seconds / 60.0 if dur else 0
            st.write(f"DEBUG: Elapsed seconds = {elapsed_seconds}")
            st.write(f"DEBUG: Stint duration minutes = {stint_duration_minutes}")
            if dur is None:
                st.warning("Start stint timer first.")
            elif len(st.session_state.lineup) < 4 or len(set(st.session_state.lineup)) < 4:
                st.warning("Need a valid 4-player lineup to save the stint. Click ⚙️ Optimize first.")
            else:
                st.session_state.live_stints.append({
                    "game_id": st.session_state.selected_game_id,
                    "end_time_game": fmt_time(elapsed(st.session_state.game_start)),
                    "stint_duration": fmt_time(dur),
                    "home_score": st.session_state.home_score,
                    "away_score": st.session_state.away_score,
                    "lineup": ", ".join(st.session_state.lineup),
                })
                
                # Update fatigue multipliers based on stint
                st.session_state.fatigue = update_fatigue_after_stint(dur, st.session_state.lineup)
                st.session_state.stint_start = None
                st.success("✅ Stint saved. Updating fatigue multipliers...")
                
                # Auto-suggest next lineup
                res = optimize_lineup(
                    team_df=team_df,
                    availability=st.session_state.availability,
                    fatigue_levels=st.session_state.fatigue,
                    home_score=float(st.session_state.home_score),
                    away_score=float(st.session_state.away_score),
                    pre_selected=st.session_state.pre_selected,
                )
                st.session_state.last_opt = res
                if res["lineup"]:
                    st.session_state.lineup = res["lineup"]
                    st.info("🎯 Suggested next lineup (based on updated fatigue)!")
                st.rerun()
    st.subheader("Stint History")
    if st.session_state.live_stints:
        st.caption("Session stints saved (this run)")
        st.dataframe(pd.DataFrame(st.session_state.live_stints), use_container_width=True, hide_index=True)
    else: 
        st.info("No stints saved yet. Use the right panel to start a game and save stints.")
 
# ----------------------------
# RIGHT PANEL (scoreboard + game time + lineup + buttons + totals + stint time)
# ----------------------------
with right:
    st.subheader("Scoreboard")
    st.info("Step 1: Use the controls below to update the score and manage the game timer.")
    sb1, sb2 = st.columns([1.0, 1.0])
    with sb1:
        st.session_state.home_score = st.number_input("Home", min_value=0, value=int(st.session_state.home_score), step=1)
    with sb2:
        st.session_state.away_score = st.number_input("Away", min_value=0, value=int(st.session_state.away_score), step=1)
 
    st.metric("Overall Game Runtime", fmt_time(elapsed(st.session_state.game_start)))
 
    g1, g2 = st.columns(2)
    with g1:
        if st.button("▶️ Start Game", use_container_width=True):
            if st.session_state.game_start is None:
                st.session_state.game_start = time.time()
                # Auto-suggest initial lineup
                res = optimize_lineup(
                    team_df=team_df,
                    availability=st.session_state.availability,
                    fatigue_levels=st.session_state.fatigue,
                    home_score=float(st.session_state.home_score),
                    away_score=float(st.session_state.away_score),
                    pre_selected=st.session_state.pre_selected,
                )
                st.session_state.last_opt = res
                if res["lineup"]:
                    st.session_state.lineup = res["lineup"]
                st.success("🎯 Suggested initial lineup!")
                st.rerun()
    with g2:
        if st.button("⏹ Stop Game", use_container_width=True):
            st.session_state.game_start = None
 
    st.divider()
 
    st.subheader("Current Stint Lineup")
    st.info("Step 2: Pre-select up to 4 players for the lineup (optional), then click Optimize.")
 
    # 4 slots for pre-selection (optional)
    st.markdown("**Pre-Select Players (optional, up to 4)**")
    st.caption("Leave blank to let the optimizer suggest. Select multiple to lock them in.")
    
    l1, l2, l3, l4 = st.columns(4)
    empty_option = "—"
    opts_with_empty = [empty_option] + team_ids
    
    def get_default_index(slot: int) -> int:
        """Get default index for selectbox based on pre_selected list"""
        if slot < len(st.session_state.pre_selected):
            player = st.session_state.pre_selected[slot]
            if player in opts_with_empty:
                return opts_with_empty.index(player)
        return 0  # Default to empty
    
    p1 = l1.selectbox("Slot 1", options=opts_with_empty, index=get_default_index(0), key="slot_1")
    p2 = l2.selectbox("Slot 2", options=opts_with_empty, index=get_default_index(1), key="slot_2")
    p3 = l3.selectbox("Slot 3", options=opts_with_empty, index=get_default_index(2), key="slot_3")
    p4 = l4.selectbox("Slot 4", options=opts_with_empty, index=get_default_index(3), key="slot_4")
    
    # Collect pre-selected players (remove empty placeholders)
    pre_selected_slots = [p for p in [p1, p2, p3, p4] if p != empty_option]
    
    # Update session state with pre-selected players
    st.session_state.pre_selected = pre_selected_slots
    
    # Show pre-selected status
    if pre_selected_slots:
        st.info(f"🔒 Pre-selected: {', '.join(pre_selected_slots)}")
    else:
        st.info("ℹ️ No pre-selected players. Optimizer will suggest all 4.")
    
    # Buttons
    b1, b2 = st.columns(2)
    with b1:
        if st.button("⚙️ Optimize", use_container_width=True):
            res = optimize_lineup(
                team_df=team_df,
                availability=st.session_state.availability,
                fatigue_levels=st.session_state.fatigue,
                home_score=float(st.session_state.home_score),
                away_score=float(st.session_state.away_score),
                pre_selected=st.session_state.pre_selected,
            )
            st.session_state.last_opt = res
            if res["lineup"]:
                st.session_state.lineup = res["lineup"]
                st.rerun()
    with b2:
        if st.button("🧼 Clear Selection", use_container_width=True):
            st.session_state.pre_selected = []
            st.session_state.lineup = []
            st.session_state.last_opt = None
            st.rerun()
 
    # Current lineup display
    st.title("**Optimized Lineup**")
    st.info("The lineup below shows the currently selected 4 players for the stint.")
    if len(st.session_state.lineup) == 4:
        # Display lineup in 2x2 grid
        row1 = st.columns(2)
        row2 = st.columns(2)
        with row1[0]:
            st.metric("Slot 1", st.session_state.lineup[0])
        with row1[1]:
            st.metric("Slot 2", st.session_state.lineup[1])
        with row2[0]:
            st.metric("Slot 3", st.session_state.lineup[2])
        with row2[1]:
            st.metric("Slot 4", st.session_state.lineup[3])
        
        # Lineup totals
        ldf = team_df[team_df["player_id"].isin(st.session_state.lineup)].copy()
        total_dis = float(ldf["disability_score"].sum())
        
        col1, col2 = st.columns(2)
        with col1:
            cap = 8.0
            if total_dis > cap:
                st.error(f"Disability: {total_dis:.1f} (OVER cap {cap:.1f})")
            else:
                st.success(f"Disability: {total_dis:.1f} / {cap:.1f}")
        
        with col2:
            avg_fatigue = sum(st.session_state.fatigue.get(pid, 100.0) for pid in st.session_state.lineup) / 4
            st.metric("Avg Lineup Fatigue", f"{avg_fatigue:.0f}/100")
        
        st.markdown("**Fatigue of Current Lineup**")
        for pid in st.session_state.lineup:
            f = float(st.session_state.fatigue.get(pid, 100.0))
            st.progress(int(f) / 100, text=f"{pid} — {f:.0f}/100")
    else:
        st.info("Click '⚙️ Optimize' to generate lineup.")
 
    st.divider()
 
    if st.session_state.last_opt:
        st.subheader("Current Lineup Player Breakdown")
        if st.session_state.last_opt.get("breakdown"):
            for player_info in st.session_state.last_opt["breakdown"]:
                pre_sel = " (Pre-Selected)" if player_info.get("is_pre_selected", False) else ""
                st.write(
                    f"  • {player_info['player_id']}{pre_sel}: "
                    f"Player Score = {player_info['value_score']:.2f}, "
                    f"% Energy Remaining = {player_info['t_j']*100:.0f}%, "
                    f"Fatigue-Adjusted Score = {player_info['adjusted_score']:.3f}"
                )