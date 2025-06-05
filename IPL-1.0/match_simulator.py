import random
import json
import accessJSON
import copy

class MatchSimulator:
    def __init__(self, team1_code, team2_code, pitch_factors=None):
        self.team1_code = team1_code.lower()
        self.team2_code = team2_code.lower()

        if pitch_factors:
            self.pace_factor = pitch_factors.get('pace', 1.0)
            self.spin_factor = pitch_factors.get('spin', 1.0)
            self.outfield_factor = pitch_factors.get('outfield', 1.0)
        else:
            self.pace_factor = 1.0
            self.spin_factor = 1.0
            self.outfield_factor = 1.0

        self.team1_players_stats = {}
        self.team2_players_stats = {}
        self.all_teams_data = {}
        try:
            with open('teams/teams.json', 'r', encoding='utf-8') as f:
                self.all_teams_data = json.load(f)
        except FileNotFoundError:
            print(f"CRITICAL ERROR: teams/teams.json not found.")
            raise

        team1_player_initials_list = self.all_teams_data.get(self.team1_code, {}).get('players', [])
        team2_player_initials_list = self.all_teams_data.get(self.team2_code, {}).get('players', [])

        if not team1_player_initials_list: raise ValueError(f"Player list for {self.team1_code} is empty/missing.")
        if not team2_player_initials_list: raise ValueError(f"Player list for {self.team2_code} is empty/missing.")

        for initial in team1_player_initials_list:
            raw_stats = None
            try: raw_stats = accessJSON.getPlayerInfo(initial)
            except KeyError: print(f"Info: No raw stats entry for {initial} (Team {self.team1_code}).")
            self.team1_players_stats[initial] = self._preprocess_player_stats(initial, raw_stats)

        for initial in team2_player_initials_list:
            raw_stats = None
            try: raw_stats = accessJSON.getPlayerInfo(initial)
            except KeyError: print(f"Info: No raw stats entry for {initial} (Team {self.team2_code}).")
            self.team2_players_stats[initial] = self._preprocess_player_stats(initial, raw_stats)

        self.batting_team_code = None; self.bowling_team_code = None
        self.current_batsmen = {'on_strike': None, 'non_strike': None}
        self.current_bowler = None
        self.last_over_bowler_initial = None
        self.current_innings = 1
        self.innings = { 1: self._get_empty_innings_structure(), 2: self._get_empty_innings_structure() }
        self.target = 0; self.game_over = False; self.match_winner = None; self.win_message = ""
        self.toss_winner = None; self.toss_decision = None; self.toss_message = ""
        self.batting_order = {self.team1_code: [], self.team2_code: []}
        self.bowlers_list = {self.team1_code: [], self.team2_code: []} # General list of all available bowlers
        self.team_bowler_phases = { # Phase-specific sorted lists
            self.team1_code: {'powerplay': [], 'middle': [], 'death': []},
            self.team2_code: {'powerplay': [], 'middle': [], 'death': []}
        }
        self.next_batsman_index = {self.team1_code: 0, self.team2_code: 0}

    def _create_placeholder_player_stats(self, initial):
        placeholder = {
            "playerInitials": initial, "displayName": initial, "BowlingSkill": "Unknown", "batStyle": "Unknown",
            "batRunDenominations": {"0":10,"1":10,"2":2,"3":0,"4":1,"6":1},
            "batOutTypes": {"bowled":1,"caught":1,"runOut":0,"lbw":0,"stumped":0,"hitwicket":0},
            "batBallsTotal": 25, "batOutsTotal": 2, "runnedOut":0, "catches": 0, "matches":1,
            "bowlRunDenominations": {"0":10,"1":10,"2":2,"3":0,"4":1,"6":1},
            "bowlOutTypes": {"bowled":1,"caught":1,"lbw":0,"stumped":0},
            "bowlBallsTotal": 25, "bowlOutsTotal": 1, "bowlWides":1, "bowlNoballs":0,
            "position": ["7"], "runs": 0, "balls": 0, "fours":0, "sixes":0, "how_out": "Did Not Bat",
            "batRunDenominationsObject": {}, "batOutTypesObject": {}, "batOutsRate": 0.1,
            "bowlRunDenominationsObject": {}, "bowlOutTypesObject": {}, "bowlOutsRate": 0.1,
            "bowlWideRate": 0.01, "bowlNoballRate": 0.005, "catchRate": 0.1,
            "overNumbersObject": {str(i):0.05 for i in range(20)}
        }
        for field in ["batRunDenominations", "bowlRunDenominations", "batOutTypes", "bowlOutTypes"]:
            if field in placeholder: placeholder[field] = {str(k): v for k,v in placeholder[field].items()}
        return placeholder

    def _preprocess_player_stats(self, initial, raw_stats):
        processed = self._create_placeholder_player_stats(initial) if not raw_stats else copy.deepcopy(raw_stats)
        if raw_stats:
             for key, default_val in self._create_placeholder_player_stats(initial).items():
                processed.setdefault(key, default_val)
        bat_balls = processed.get('batBallsTotal', 0); bat_balls = 1 if bat_balls == 0 else bat_balls
        processed['batRunDenominationsObject'] = { str(k): v / bat_balls for k, v in processed.get('batRunDenominations', {}).items()}
        processed['batOutTypesObject'] = {str(k): v / bat_balls for k, v in processed.get('batOutTypes', {}).items()}
        processed['batOutsRate'] = processed.get('batOutsTotal', 0) / bat_balls
        bowl_balls = processed.get('bowlBallsTotal', 0); bowl_balls = 1 if bowl_balls == 0 else bowl_balls
        processed['bowlRunDenominationsObject'] = { str(k): v / bowl_balls for k, v in processed.get('bowlRunDenominations', {}).items()}
        processed['bowlOutTypesObject'] = { str(k): v / bowl_balls for k, v in processed.get('bowlOutTypes', {}).items()}
        processed['bowlOutsRate'] = processed.get('bowlOutsTotal', 0) / bowl_balls
        processed['bowlWideRate'] = processed.get('bowlWides', 0) / bowl_balls if bowl_balls > 0 else 0.01
        processed['bowlNoballRate'] = processed.get('bowlNoballs', 0) / bowl_balls if bowl_balls > 0 else 0.005
        matches = processed.get('matches', 1); matches = 1 if matches == 0 else matches
        processed['catchRate'] = processed.get('catches', 0) / matches
        # Ensure overNumbersObject sums proficiency for phases for sorting later
        over_obj_processed = {str(i): 0.0 for i in range(20)}
        if 'overNumbersObject' in processed and isinstance(processed['overNumbersObject'], dict): # from placeholder or previous processing
            for k,v in processed['overNumbersObject'].items(): over_obj_processed[k] = v
        else: # from raw stats (list of over numbers bowled)
            over_counts = {str(i): 0 for i in range(20)}
            for over_num_str in processed.get('overNumbers', []):
                valid_over_num_str = str(over_num_str)
                if valid_over_num_str in over_counts: over_counts[valid_over_num_str] +=1
            for k_over in over_obj_processed: over_obj_processed[k_over] = over_counts[k_over] / matches if matches > 0 else 0.0
        processed['overNumbersObject'] = over_obj_processed
        return processed

    def _get_empty_innings_structure(self):
        return {'score': 0, 'wickets': 0, 'balls_bowled': 0, 'legal_balls_bowled':0, 'overs_completed': 0,
                'log': [], 'batting_tracker': {}, 'bowling_tracker': {},
                'batting_team_code': None, 'bowling_team_code': None}

    def _initialize_player_trackers(self, batting_team_code_for_innings, bowling_team_code_for_innings):
        current_inn_data = self.innings[self.current_innings]
        current_inn_data['batting_tracker'] = {}
        current_inn_data['bowling_tracker'] = {}
        for i, initial_key in enumerate(self.batting_order[batting_team_code_for_innings]):
             current_inn_data['batting_tracker'][initial_key] = {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'bowler': None, 'fielder': None, 'order': i + 1}
        for initial_key in self.bowlers_list[bowling_team_code_for_innings]: # Use the general bowlers_list
            current_inn_data['bowling_tracker'][initial_key] = {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0}

    def _initialize_batting_order_and_bowlers(self):
        for team_code_iter, player_stats_pool in [(self.team1_code, self.team1_players_stats), (self.team2_code, self.team2_players_stats)]:
            ordered_initials = self.all_teams_data.get(team_code_iter, {}).get('players', [])
            self.batting_order[team_code_iter] = [p_initial for p_initial in ordered_initials if p_initial in player_stats_pool]
            if not self.batting_order[team_code_iter] and player_stats_pool: self.batting_order[team_code_iter] = list(player_stats_pool.keys())

            # General list of bowlers
            self.bowlers_list[team_code_iter] = [p_initial for p_initial, stats in player_stats_pool.items() if stats.get('BowlingSkill') and stats['BowlingSkill'] not in ["", "None", None, "NA", "unknown", "Unknown"]]
            if not self.bowlers_list[team_code_iter] and player_stats_pool: self.bowlers_list[team_code_iter] = list(player_stats_pool.keys())
            if not self.bowlers_list[team_code_iter]:
                dummy_bowler_initial = f"Dummy_{team_code_iter}"
                self.bowlers_list[team_code_iter] = [dummy_bowler_initial]
                if dummy_bowler_initial not in player_stats_pool: player_stats_pool[dummy_bowler_initial] = self._create_placeholder_player_stats(dummy_bowler_initial)

            # Create phase-specific sorted bowler lists
            # Sorting key: sum of proficiencies in relevant overs for the phase. Higher is better.
            # Powerplay: overs 0-5
            self.team_bowler_phases[team_code_iter]['powerplay'] = sorted(
                self.bowlers_list[team_code_iter],
                key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6)),
                reverse=True
            )
            # Middle overs: 6-16
            self.team_bowler_phases[team_code_iter]['middle'] = sorted(
                self.bowlers_list[team_code_iter],
                key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6, 17)),
                reverse=True
            )
            # Death overs: 17-19
            self.team_bowler_phases[team_code_iter]['death'] = sorted(
                self.bowlers_list[team_code_iter],
                key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(17, 20)),
                reverse=True
            )

    def _setup_innings(self, innings_num):
        self.current_innings = innings_num
        if innings_num == 1:
            self.innings[1]['batting_team_code'] = self.batting_team_code; self.innings[1]['bowling_team_code'] = self.bowling_team_code
            self.next_batsman_index[self.batting_team_code] = 0
        else:
            prev_bat_team = self.innings[1]['batting_team_code']; prev_bowl_team = self.innings[1]['bowling_team_code']
            self.batting_team_code = prev_bowl_team; self.bowling_team_code = prev_bat_team
            self.innings[2]['batting_team_code'] = self.batting_team_code; self.innings[2]['bowling_team_code'] = self.bowling_team_code
            self.target = self.innings[1]['score'] + 1
            if self.target <= 0: self.target = float('inf')
            self.next_batsman_index[self.batting_team_code] = 0
        self._initialize_player_trackers(self.batting_team_code, self.bowling_team_code)
        self.current_batsmen['on_strike'] = self._get_next_batsman(self.batting_team_code)
        if self.current_batsmen['on_strike']: self.innings[self.current_innings]['batting_tracker'][self.current_batsmen['on_strike']]['how_out'] = "Not out"
        self.current_batsmen['non_strike'] = self._get_next_batsman(self.batting_team_code)
        if self.current_batsmen['non_strike']: self.innings[self.current_innings]['batting_tracker'][self.current_batsmen['non_strike']]['how_out'] = "Not out"

        self.last_over_bowler_initial = None # Reset for new innings
        self.current_bowler = self._select_next_bowler() # Select first bowler

    def _get_next_batsman(self, team_code):
        order = self.batting_order[team_code]; idx = self.next_batsman_index[team_code]
        if idx < len(order): self.next_batsman_index[team_code] += 1; return order[idx]
        return None

    def perform_toss(self):
        self.toss_winner = random.choice([self.team1_code, self.team2_code]); self.toss_decision = random.choice(['bat', 'field'])
        if self.toss_decision == 'bat': self.batting_team_code = self.toss_winner; self.bowling_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        else: self.bowling_team_code = self.toss_winner; self.batting_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        self.toss_message = f"{self.toss_winner.upper()} won the toss and chose to {self.toss_decision}."
        self._initialize_batting_order_and_bowlers(); self._setup_innings(1) # Bowler selected in _setup_innings
        return self.toss_message, self.toss_winner.upper(), self.toss_decision

    def _calculate_dynamic_probabilities(self, batsman_obj, bowler_obj, inn_data, bt_current_ball_stats):
        denAvg = {str(r): (batsman_obj['batRunDenominationsObject'].get(str(r),0) + bowler_obj['bowlRunDenominationsObject'].get(str(r),0))/2 for r in range(7)}
        outAvg = (batsman_obj['batOutsRate'] + bowler_obj['bowlOutsRate']) / 2
        outTypeAvg = copy.deepcopy(bowler_obj['bowlOutTypesObject'])
        runout_chance_batsman = batsman_obj.get('runnedOut',0) / (batsman_obj.get('batBallsTotal',1) if batsman_obj.get('batBallsTotal',0) > 0 else 1)
        outTypeAvg['runOut'] = outTypeAvg.get('runOut', 0.005) + runout_chance_batsman / 2
        wideRate = bowler_obj['bowlWideRate']; noballRate = bowler_obj['bowlNoballRate']
        bowler_skill = bowler_obj.get('BowlingSkill', '').lower()
        if 'spin' in bowler_skill or 'break' in bowler_skill:
            effect = (1.0 - self.spin_factor) / 2
            outAvg += (effect * 0.1)
            for r in ['4','6']: denAvg[r] = max(0.001, denAvg.get(r,0.001) * (1 - effect*2))
            denAvg['0'] = denAvg.get('0',0) + (effect*0.1); denAvg['1'] = denAvg.get('1',0) + (effect*0.05)
        elif 'fast' in bowler_skill or 'medium' in bowler_skill:
            effect = (1.0 - self.pace_factor) / 2
            outAvg += (effect * 0.1)
            for r in ['4','6']: denAvg[r] = max(0.001, denAvg.get(r,0.001) * (1 - effect*2))
            denAvg['0'] = denAvg.get('0',0) + (effect*0.1); denAvg['1'] = denAvg.get('1',0) + (effect*0.05)
        for r in ['4','6']: denAvg[r] = denAvg.get(r,0) / self.outfield_factor
        balls_faced_batsman = bt_current_ball_stats['balls']; innings_balls_total = inn_data['legal_balls_bowled']
        innings_runs_total = inn_data['score']; innings_wickets_total = inn_data['wickets']
        if balls_faced_batsman < 8 and innings_balls_total < 80:
            adjust = random.uniform(-0.01, 0.03) * (1 if self.current_innings == 1 else 0.8)
            outAvg = max(0.01, outAvg - 0.015)
            denAvg['0'] = max(0.001, denAvg.get('0',0) + adjust * 0.5); denAvg['1'] = max(0.001, denAvg.get('1',0) + adjust * 0.33)
            denAvg['2'] = max(0.001, denAvg.get('2',0) + adjust * 0.17); denAvg['4'] = max(0.001, denAvg.get('4',0) - adjust * 0.17)
            denAvg['6'] = max(0.001, denAvg.get('6',0) - adjust * 0.5)
        if balls_faced_batsman > 15 and balls_faced_batsman < 30:
            adjust = random.uniform(0.03, 0.07)
            denAvg['0'] = max(0.001, denAvg.get('0',0) - adjust * 0.33); denAvg['4'] = max(0.001, denAvg.get('4',0) + adjust * 0.33)
        if balls_faced_batsman > 20 and (bt_current_ball_stats['runs'] / balls_faced_batsman if balls_faced_batsman > 0 else 0) < 1.1:
            adjust = random.uniform(0.05, 0.08)
            denAvg['0'] = max(0.001, denAvg.get('0',0) + adjust * 0.5); denAvg['1'] = max(0.001, denAvg.get('1',0) + adjust * 0.17)
            denAvg['6'] = max(0.001, denAvg.get('6',0) - adjust * 0.67); outAvg = min(0.9, outAvg + 0.05)
        if innings_balls_total < 36: # Powerplay
            outAvg = max(0.01, outAvg - (0.07 if innings_wickets_total == 0 else 0.03))
            adj = random.uniform(0.05, 0.11) if innings_wickets_total < 2 else random.uniform(0.02, 0.08)
            denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.67); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33)
            denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * (0.67 if innings_wickets_total < 2 else 0.83))
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * (0.33 if innings_wickets_total < 2 else 0.17))
        elif innings_balls_total >= 102: # Death (overs 17-19, i.e. after 16*6=96, or 17*6=102)
            adj = random.uniform(0.07, 0.1) if innings_wickets_total < 7 else random.uniform(0.07,0.09)
            denAvg['0'] = max(0.001, denAvg.get('0',0) + adj * (0.13 if innings_wickets_total < 7 else -0.13))
            denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.48)
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.62); outAvg = min(0.9, outAvg + (0.015 if innings_wickets_total < 7 else 0.025))
        # Middle overs (6-16) implicit if not powerplay or death
        elif innings_balls_total >= 36 and innings_balls_total < 102:
            if innings_wickets_total < 3: # Attacking middle phase
                adj = random.uniform(0.05, 0.11)
                denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.5); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.33)
                denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.5); denAvg['6'] = max(0.001, denAvg.get('6',0) + adj*0.33)
            else: # Consolidating middle phase
                adj = random.uniform(0.02, 0.07)
                denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.53); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.4)
                denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.7); denAvg['6'] = max(0.001, denAvg.get('6',0) + adj*0.3)
                outAvg = max(0.01, outAvg - 0.03)


        if self.current_innings == 2 and innings_balls_total < 120 and self.target > 0:
            balls_remaining = 120 - innings_balls_total; runs_needed = self.target - innings_runs_total
            if runs_needed > 0 :
                rrr = (runs_needed / balls_remaining) * 6 if balls_remaining > 0 else float('inf')
                if rrr < 8:
                    adj = random.uniform(0.05, 0.09) * (1 - (rrr/10)*0.5)
                    denAvg['6'] = max(0.001, denAvg.get('6',0) - adj * 0.67); denAvg['4'] = max(0.001, denAvg.get('4',0) - adj*0.33)
                    denAvg['1'] = max(0.001, denAvg.get('1',0) + adj); outAvg = max(0.01, outAvg - 0.04)
                elif rrr <= 10.4:
                    adj = random.uniform(0.04, 0.08)
                    denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.2); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj*0.33)
                    outAvg = min(0.9, outAvg - 0.01)
                elif rrr > 10.4:
                    adj = random.uniform(0.04,0.08) + (rrr*1.1)/1000
                    denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.5); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj*0.33)
                    denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.17); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.67)
                    outAvg = min(0.9, outAvg + (0.02 + (rrr*1.1)/1000))
        current_sum = sum(d for d in denAvg.values() if isinstance(d, (int, float)) and d > 0)
        if current_sum > 0 : denAvg = {k: max(0.0001, v/current_sum) for k,v in denAvg.items()}
        else: denAvg = {"0":0.5, "1":0.5}; print(f"Warning: denAvg sum zero for {batsman_obj['playerInitials']} vs {bowler_obj['playerInitials']}.")
        current_out_type_sum = sum(v for v in outTypeAvg.values() if isinstance(v, (int,float)) and v > 0)
        if current_out_type_sum > 0: outTypeAvg = {k: max(0.0001, v/current_out_type_sum) for k,v in outTypeAvg.items()}
        else: outTypeAvg = {"bowled": 1.0}
        return denAvg, outAvg, outTypeAvg, wideRate, noballRate

    def _select_next_bowler(self):
        current_over_to_be_bowled = self.innings[self.current_innings]['overs_completed'] # Next over number (0-indexed for 1st over)
        bowling_team_stat_pool = self.team1_players_stats if self.bowling_team_code == self.team1_code else self.team2_players_stats
        bowler_tracker_this_innings = self.innings[self.current_innings]['bowling_tracker']

        phase = 'powerplay' if current_over_to_be_bowled < 6 else ('death' if current_over_to_be_bowled >= 17 else 'middle')

        # Use phase-specific sorted list of bowlers
        phase_specific_bowler_list = self.team_bowler_phases[self.bowling_team_code][phase]

        eligible_bowlers = []
        for initial in phase_specific_bowler_list:
            if initial not in bowling_team_stat_pool: continue # Should not happen if lists are generated from pool

            tracker_stats = bowler_tracker_this_innings.get(initial, {'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0})

            # Max 4 overs (24 balls) per bowler
            if tracker_stats['balls_bowled'] >= 24: continue

            # Avoid bowling same bowler back-to-back if multiple options, unless it's early & they are good.
            # Or if it's a key bowler in a key phase.
            # This is a simplified check. mainconnect has more nuanced spell logic.
            if initial == self.last_over_bowler_initial and len(self.bowlers_list[self.bowling_team_code]) > 1:
                # Allow if bowler is very good and not bowled much, or it's a critical phase.
                # For now, simple rule: if more than 3 bowlers, try to change.
                if len(self.bowlers_list[self.bowling_team_code]) > 3 : continue


            # Basic score: current economy, wickets. Lower score is better.
            # This is a placeholder for more complex scoring from mainconnect
            economy = (tracker_stats['runs_conceded'] / (tracker_stats['balls_bowled'] / 6.0)) if tracker_stats['balls_bowled'] > 0 else 99.0
            score = economy - (tracker_stats['wickets'] * 10) # Heavily reward wickets

            # Prefer bowlers who haven't completed their quota
            score += tracker_stats['balls_bowled'] * 0.1

            eligible_bowlers.append({'initial': initial, 'score': score})

        if not eligible_bowlers: # Fallback: use general list, ignore phase/last bowler if no one fits criteria
            eligible_bowlers = [{'initial': b, 'score': random.random()} for b in self.bowlers_list[self.bowling_team_code] if bowler_tracker_this_innings.get(b,{}).get('balls_bowled',0) < 24]

        if not eligible_bowlers: # Absolute fallback: pick any bowler from master list, even if bowled out (should not happen)
             return random.choice(self.bowlers_list[self.bowling_team_code]) if self.bowlers_list[self.bowling_team_code] else self.last_over_bowler_initial


        eligible_bowlers.sort(key=lambda x: x['score'])

        return eligible_bowlers[0]['initial']


    def simulate_one_ball(self):
        if self.game_over: return {"summary": self.get_game_state(), "ball_event": {"commentary": f"Game is over. {self.win_message}"}}
        inn_data = self.innings[self.current_innings]; batsman_initial = self.current_batsmen['on_strike']; bowler_initial = self.current_bowler
        if not batsman_initial: self._end_innings(); return {"summary": self.get_game_state(), "ball_event": {"commentary": "Innings ended: No batsman available."}}
        if not bowler_initial:
            self.current_bowler = self._select_next_bowler(); bowler_initial = self.current_bowler
            if not bowler_initial: self._end_innings(); return {"summary": self.get_game_state(), "ball_event": {"commentary": "Innings ended: No bowler available for " + self.bowling_team_code}}

        batsman_obj = self.team1_players_stats.get(batsman_initial) if self.batting_team_code == self.team1_code else self.team2_players_stats.get(batsman_initial)
        bowler_obj = self.team1_players_stats.get(bowler_initial) if self.bowling_team_code == self.team1_code else self.team2_players_stats.get(bowler_initial)
        if not batsman_obj or not bowler_obj: self._end_innings(); return {"summary": self.get_game_state(), "ball_event": {"commentary": "Error: Player stats object not found."}}
        batsman_tracker = inn_data['batting_tracker'].setdefault(batsman_initial, self._create_placeholder_player_stats(batsman_initial))
        bowler_tracker = inn_data['bowling_tracker'].setdefault(bowler_initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})
        denAvg, outAvg, outTypeAvg, wideRate, noballRate = self._calculate_dynamic_probabilities(batsman_obj, bowler_obj, inn_data, batsman_tracker)
        runs_this_ball = 0; is_wicket_this_ball = False; extra_type_this_ball = None; extra_runs_this_ball = 0; is_legal_delivery = True; commentary_this_ball = ""
        if random.uniform(0,1) < wideRate:
            is_legal_delivery = False; extra_type_this_ball = 'Wide'; extra_runs_this_ball = 1
            inn_data['score'] += 1; bowler_tracker['runs_conceded'] += 1; commentary_this_ball = "Wide."
        else:
            if random.uniform(0,1) < outAvg :
                is_wicket_this_ball = True; inn_data['wickets'] += 1; wicket_type_chosen = "Bowled"
                out_type_total_prob = sum(v for v in outTypeAvg.values() if isinstance(v, (int,float)) and v > 0)
                if out_type_total_prob > 0:
                    out_type_rand = random.uniform(0, out_type_total_prob); current_prob_sum = 0
                    for w_type, w_prob in outTypeAvg.items():
                        current_prob_sum += w_prob
                        if out_type_rand <= current_prob_sum: wicket_type_chosen = w_type; break
                batsman_tracker['how_out'] = wicket_type_chosen.capitalize(); batsman_tracker['bowler'] = bowler_initial
                bowler_tracker['wickets'] += 1; commentary_this_ball = f"{batsman_initial} is {wicket_type_chosen} by {bowler_initial}!"
                if wicket_type_chosen.lower() == 'caught':
                    # Use pre-calculated general list of fielders (all players of bowling team not the bowler)
                    fielding_team_players = self.team1_players_stats.keys() if self.bowling_team_code == self.team1_code else self.team2_players_stats.keys()
                    possible_catchers_initials = [p_init for p_init in fielding_team_players if p_init != bowler_initial]
                    catcher_initial = random.choice(possible_catchers_initials) if possible_catchers_initials else bowler_initial
                    batsman_tracker['fielder'] = catcher_initial
                    commentary_this_ball = f"{batsman_initial} c {catcher_initial} b {bowler_initial} OUT!"
                self.current_batsmen['on_strike'] = self._get_next_batsman(self.batting_team_code)
                if self.current_batsmen['on_strike']: inn_data['batting_tracker'].setdefault(self.current_batsmen['on_strike'], self._create_placeholder_player_stats(self.current_batsmen['on_strike']))['how_out'] = "Not out"
            else:
                total_run_prob = sum(v for v in denAvg.values() if isinstance(v, (int,float)) and v > 0)
                runs_this_ball = 0
                if total_run_prob > 0 :
                    run_rand = random.uniform(0, total_run_prob); current_prob_sum = 0
                    for run_val_str, run_prob in denAvg.items():
                        current_prob_sum += run_prob
                        if run_rand <= current_prob_sum: runs_this_ball = int(run_val_str); break
                inn_data['score'] += runs_this_ball; batsman_tracker['runs'] += runs_this_ball
                if runs_this_ball == 4: batsman_tracker['fours'] = batsman_tracker.get('fours',0) + 1
                if runs_this_ball == 6: batsman_tracker['sixes'] = batsman_tracker.get('sixes',0) + 1
                bowler_tracker['runs_conceded'] += runs_this_ball; commentary_this_ball = f"{batsman_initial} scores {runs_this_ball}."
                if runs_this_ball == 0: bowler_tracker['dots'] = bowler_tracker.get('dots',0) + 1
        if is_legal_delivery:
            inn_data['balls_bowled'] += 1; inn_data['legal_balls_bowled'] +=1
            batsman_tracker['balls'] += 1; bowler_tracker['balls_bowled'] += 1
        ball_in_over_for_log = inn_data['legal_balls_bowled'] % 6 if is_legal_delivery else inn_data['balls_bowled'] % 6
        if is_legal_delivery and ball_in_over_for_log == 0 and inn_data['legal_balls_bowled'] > 0: ball_in_over_for_log = 6
        ball_log_entry = {'ball': inn_data['legal_balls_bowled'], 'over_str': f"{inn_data['overs_completed']}.{ball_in_over_for_log}",
            'batsman': batsman_initial, 'bowler': bowler_initial, 'runs': runs_this_ball, 'is_wicket': is_wicket_this_ball,
            'extra_type': extra_type_this_ball, 'extras': extra_runs_this_ball, 'total_runs_ball': runs_this_ball + extra_runs_this_ball,
            'commentary': commentary_this_ball, 'score_after_ball': inn_data['score'], 'wickets_after_ball': inn_data['wickets']}
        inn_data['log'].append(ball_log_entry)
        if is_legal_delivery and runs_this_ball % 2 == 1: self.current_batsmen['on_strike'], self.current_batsmen['non_strike'] = self.current_batsmen['non_strike'], self.current_batsmen['on_strike']
        max_balls = 120; max_wickets = 10; game_ending_condition = False
        if inn_data['wickets'] >= max_wickets or not self.current_batsmen['on_strike']: game_ending_condition = True
        if self.current_innings == 2 and inn_data['score'] >= self.target: game_ending_condition = True
        if inn_data['legal_balls_bowled'] >= max_balls: game_ending_condition = True
        if game_ending_condition: self._end_innings()
        elif is_legal_delivery and inn_data['legal_balls_bowled'] % 6 == 0 and inn_data['legal_balls_bowled'] > 0:
            inn_data['overs_completed'] += 1; self.last_over_bowler_initial = self.current_bowler
            self.current_batsmen['on_strike'], self.current_batsmen['non_strike'] = self.current_batsmen['non_strike'], self.current_batsmen['on_strike']
            self.current_bowler = self._select_next_bowler()
        return {"summary": self.get_game_state(), "ball_event": ball_log_entry}

    def _end_innings(self):
        inn_data = self.innings[self.current_innings]
        inn_data['overs_completed'] = inn_data['legal_balls_bowled'] // 6
        for b_stats in inn_data['bowling_tracker'].values():
            if b_stats['balls_bowled'] > 0:
                b_stats['overs_str'] = f"{b_stats['balls_bowled'] // 6}.{b_stats['balls_bowled'] % 6}"
                b_stats['economy'] = (b_stats['runs_conceded'] / b_stats['balls_bowled']) * 6 if b_stats['balls_bowled'] > 0 else 0.0
        if self.current_innings == 1: self._setup_innings(2)
        else:
            self.game_over = True; s1 = self.innings[1]['score']; s2 = self.innings[2]['score']
            inn1_bat_team = self.innings[1]['batting_team_code']; inn2_bat_team = self.innings[2]['batting_team_code']
            if s2 >= self.target: self.match_winner = inn2_bat_team; self.win_message = f"{self.match_winner.upper()} won by {10 - self.innings[2]['wickets']} wickets."
            elif s1 > s2: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."
            elif s1 == s2: self.match_winner = "Tie"; self.win_message = "Match Tied."
            else: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."

    def get_game_state(self):
        return {"team1_code": self.team1_code.upper(), "team2_code": self.team2_code.upper(),
            "current_innings_num": self.current_innings, "innings_data": self.innings,
            "on_strike": self.current_batsmen['on_strike'], "non_strike": self.current_batsmen['non_strike'],
            "current_bowler": self.current_bowler, "target_score": self.target, "game_over": self.game_over,
            "match_winner": self.match_winner.upper() if self.match_winner and self.match_winner != "Tie" else self.match_winner,
            "win_message": self.win_message, "toss_message": self.toss_message,
            "current_batting_team": self.batting_team_code.upper() if self.batting_team_code else None,
            "current_bowling_team": self.bowling_team_code.upper() if self.bowling_team_code else None}
# --- New MatchSimulator Class END ---
