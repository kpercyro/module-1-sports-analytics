import pandas as pd
from typing import Dict, List
import gurobipy as gp #uses gurobi for optimization as taught in MSE 434
from gurobipy import GRB

class LineupOptimizer:
    
    def calculate_strategy_weight(self, home_score: float, away_score: float) -> float:
        diff = home_score - away_score
        if diff < -2: #push team to take more offensive strategy since they are losing by 2+ points
            return 0.0
        elif -2 <= diff <= 2: #score difference is small enough to play balanced
            return 1.0
        else: #team is winning by more than 2 points so they can play more defensively
            return 2.0
    
    def update_fatigue_multiplier(self, t_j: float, stint_duration_minutes: float, on_court: bool) -> float:
        if on_court: #player on court loses energy at a rate of 0.02 per minute
            t_new = t_j - (0.02 * stint_duration_minutes)
        else: #player on bench gains energy at a rate of 0.01 per minute
            t_new = t_j + (0.01 * stint_duration_minutes)
        
        #ensure that no player can have more than 1.0 or 100% energy, or less than 0.3 or 30% energy for realism
        t_new = max(0.3, min(1.0, t_new))
        return t_new
    
    #collection of variables and constants needed for the optimization
    def optimize_lineup(
        self,
        team_df: pd.DataFrame,
        availability: Dict[str, bool],
        fatigue_levels: Dict[str, float],
        home_score: float,
        away_score: float,
        pre_selected: List[str] = None,
        disability_cap: float = 8.0,
        lineup_size: int = 4,
    ) -> Dict:
        
        if pre_selected is None: #if no players were pre-selected by coach for lineup, set to empty list
            pre_selected = []
        
        #calculate the strategy scoring weight alpha based on home-away score differential
        alpha = self.calculate_strategy_weight(home_score, away_score)

        #ensure that the total disability score of the lineup is capped at 8.0
        disability_cap = 8.0
        
        #convert fatigue_levels (0-100) from dashboard to t_j multipliers (0.3-1.0)
        t_j_dict = {}
        for pid, fatigue_level in fatigue_levels.items():
            #mapping: fatigue 0-100 => t_j 0.3-1.0
            t_j_dict[pid] = (fatigue_level / 100.0) * 0.7 + 0.3
            t_j_dict[pid] = max(0.3, min(1.0, t_j_dict[pid]))#ensuring we have realistic fatigue bounds
        
        #ensure that only available players are considered
        available_df = team_df[
            team_df["player_id"].map(lambda x: availability.get(x, True))
        ].copy()
        
        #check if enough players are available (at least 4) else return an empty lineup
        if len(available_df) < lineup_size:
            return {
                "lineup": [],
                "objective": 0.0,
                "disability_sum": 0.0,
                "breakdown": []
            }
        
        #add fatigue multipliers to dataframe
        available_df["t_j"] = available_df["player_id"].map(
            lambda x: t_j_dict.get(x, 1.0)
        )
        
        #calculate adjusted score with sign-aware fatigue
        if alpha <= 0:
            #no fatigue effect when alpha is 0
            available_df["score_adjusted"] = available_df["value_score"]
        else: #apply fatigue adjustment
            def _adj(beta: float, tj: float) -> float:
                tj = max(0.3, min(1.0, float(tj)))
                if beta >= 0:
                    return float(beta) * (tj ** alpha)
                else: #inverse fatigue effect for negative scores
                    return float(beta) * ((1.0 / max(tj, 1e-6)) ** alpha)
            available_df["score_adjusted"] = available_df.apply(
                lambda r: _adj(float(r["value_score"]), float(r["t_j"])), axis=1
            )
        
        #check if pre-selected players are available
        pre_selected_available = [p for p in pre_selected if p in available_df["player_id"].values]
        if len(pre_selected_available) < len(pre_selected):
            unavailable = [p for p in pre_selected if p not in pre_selected_available]
            return {
                "lineup": [],
                "objective": 0.0,
                "disability_sum": 0.0,
                "breakdown": []
            }
     
        df_idx = available_df.set_index("player_id")
        player_ids = available_df["player_id"].tolist()
        
        #use Gurobi for optimization
        return self._optimize_with_gurobi(
            available_df, df_idx, player_ids, pre_selected_available,
            disability_cap, lineup_size, alpha
        )
    
    #optimize using Gurobi
    def _optimize_with_gurobi(
        self,
        available_df: pd.DataFrame,
        df_idx,
        player_ids: List[str],
        pre_selected_available: List[str],
        disability_cap: float,
        lineup_size: int,
        alpha: float,
    ) -> Dict:
        try:
            #create Gurobi model
            model = gp.Model("LineupOptimization")
            model.setParam('OutputFlag', 0)
            
            #binary decision variable x_j for each player
            x = {}
            for player_id in player_ids:
                x[player_id] = model.addVar(vtype=GRB.BINARY, name=f"x_{player_id}")
            
            #objective function: maximize sum of adjusted player scores in the lineup
            obj = gp.quicksum(
                available_df.set_index("player_id").loc[pid, "score_adjusted"] * x[pid]
                for pid in player_ids
            )
            model.setObjective(obj, GRB.MAXIMIZE) #maximize objective
            
            #constraint 1: ensure 4 players are selected
            model.addConstr(
                gp.quicksum(x[pid] for pid in player_ids) == lineup_size,
                name="lineup_size"
            )
            
            #constraint 2: ensure that the sum of the disability scores <= 8
            model.addConstr(
                gp.quicksum(
                    available_df.set_index("player_id").loc[pid, "disability_score"] * x[pid]
                    for pid in player_ids
                ) <= disability_cap,
                name="disability_cap"
            )
            
            #constraint 3: ensure that pre-selected players are included in the lineup
            for pid in pre_selected_available:
                model.addConstr(x[pid] == 1, name=f"preselected_{pid}")
            
            #optimize the model
            model.optimize()
            
            #solution extraction
            if model.status == GRB.OPTIMAL or model.status == GRB.SUBOPTIMAL:
                best_combo = [pid for pid in player_ids if x[pid].X > 0.5]
                best_obj = model.ObjVal
                best_disability_sum = sum(
                    available_df.set_index("player_id").loc[pid, "disability_score"]
                    for pid in best_combo
                )
                
                #output breakdown of selected players
                breakdown = []
                for pid in best_combo:
                    player_row = df_idx.loc[pid]
                    breakdown.append({
                        "player_id": pid,
                        "value_score": float(player_row["value_score"]),
                        "t_j": float(player_row["t_j"]),
                        "alpha": float(alpha),
                        "adjusted_score": float(player_row["score_adjusted"]),
                        "disability_score": float(player_row["disability_score"]),
                        "is_pre_selected": pid in pre_selected_available
                    })
                
                #return results
                return {
                    "lineup": best_combo,
                    "objective": float(best_obj),
                    "disability_sum": float(best_disability_sum),
                    "strategy_weight_alpha": float(alpha),
                    "breakdown": breakdown
                }
            else: #no optimal solution found
                return {
                    "lineup": [],
                    "objective": 0.0,
                    "disability_sum": 0.0,
                    "breakdown": []
                }
        
        except Exception as e:
            #in case Gurobi fails, report error
            raise RuntimeError(f"Gurobi optimization failed: {str(e)}")

#send data to dashboard
def create_optimizer() -> LineupOptimizer:
    """Helper to create optimizer instance"""
    return LineupOptimizer()
