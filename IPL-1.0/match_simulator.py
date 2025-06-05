import random
import json
import accessJSON
import copy
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MatchSimulator:
    def __init__(self, team1_code, team2_code, pitch_factors=None, saved_state=None):
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

        self.all_teams_data = {}
        try:
            with open('teams/teams.json', 'r', encoding='utf-8') as f:
                self.all_teams_data = json.load(f)
        except FileNotFoundError:
            logging.error(f"CRITICAL ERROR: teams/teams.json not found.")
            raise

        self.team1_raw_data = self.all_teams_data.get(self.team1_code, {})
        self.team2_raw_data = self.all_teams_data.get(self.team2_code, {})

        team1_player_initials_list = self.team1_raw_data.get('players', [])
        team2_player_initials_list = self.team2_raw_data.get('players', [])

        if not team1_player_initials_list: raise ValueError(f"Player list for {self.team1_code} is empty/missing.")
        if not team2_player_initials_list: raise ValueError(f"Player list for {self.team2_code} is empty/missing.")

        self._initialize_fresh_game_state()

        self.team1_players_stats = {}
        self.team2_players_stats = {}

        for initial in team1_player_initials_list:
            processed_initial_str = str(initial).strip()
            if not processed_initial_str:
                logging.warning(f"Skipping empty player initial for team {self.team1_code}.")
                continue
            raw_stats = None
            try:
                raw_stats = accessJSON.getPlayerInfo(processed_initial_str)
            except KeyError:
                logging.warning(f"Player initial '{processed_initial_str}' not found for team {self.team1_code}. Using placeholder.")
            except Exception as e:
                logging.error(f"Error fetching info for '{processed_initial_str}' (Team {self.team1_code}): {e}. Using placeholder.")
            self.team1_players_stats[processed_initial_str] = self._preprocess_player_stats(processed_initial_str, raw_stats)

        for initial in team2_player_initials_list:
            processed_initial_str = str(initial).strip()
            if not processed_initial_str:
                logging.warning(f"Skipping empty player initial for team {self.team2_code}.")
                continue
            raw_stats = None
            try:
                raw_stats = accessJSON.getPlayerInfo(processed_initial_str)
            except KeyError:
                logging.warning(f"Player initial '{processed_initial_str}' not found for team {self.team2_code}. Using placeholder.")
            except Exception as e:
                logging.error(f"Error fetching info for '{processed_initial_str}' (Team {self.team2_code}): {e}. Using placeholder.")
            self.team2_players_stats[processed_initial_str] = self._preprocess_player_stats(processed_initial_str, raw_stats)

        self._initialize_batting_order_and_bowlers()

        if saved_state and saved_state.get('toss_winner'):
            self.load_from_saved_state(saved_state)

    def _initialize_fresh_game_state(self):
        self.batting_team_code = None; self.bowling_team_code = None
        self.current_batsmen = {'on_strike': None, 'non_strike': None}
        self.current_bowler = None
        self.last_over_bowler_initial = None
        self.current_innings_num = 0
        self.innings = { 1: self._get_empty_innings_structure(), 2: self._get_empty_innings_structure() }
        self.target = 0; self.game_over = False; self.match_winner = None; self.win_message = ""
        self.toss_winner = None; self.toss_decision = None; self.toss_message = ""
        self.batting_order = {self.team1_code: [], self.team2_code: []}
        self.bowlers_list = {self.team1_code: [], self.team2_code: []}
        self.team_bowler_phases = {
            self.team1_code: {'powerplay': [], 'middle': [], 'death': []},
            self.team2_code: {'powerplay': [], 'middle': [], 'death': []}
        }
        self.next_batsman_index = {self.team1_code: 0, self.team2_code: 0}

    def _create_placeholder_player_stats(self, initial_str):
        return {
            "playerInitials": str(initial_str), "displayName": str(initial_str),
            "BowlingSkill": "Unknown", "batStyle": "Unknown","BattingHand": "Unknown",
            "batRunDenominations": {'0':10,'1':10,'2':2,'3':0,'4':1,'6':1},
            "batOutTypes": {'bowled':1,'caught':1,'runOut':0,'lbw':0,'stumped':0,'hitwicket':0},
            "batBallsTotal": 25, "batOutsTotal": 2, "runnedOut":0, "catches": 0, "matches":1,
            "bowlRunDenominations": {'0':10,'1':10,'2':2,'3':0,'4':1,'6':1},
            "bowlOutTypes": {'bowled':1,'caught':1,'lbw':0,'stumped':0},
            "bowlBallsTotal": 25, "bowlOutsTotal": 1,
            "bowlWides":1, "bowlNoballs":0,
            "position": ["7"], "runs": 0, "balls": 0, "fours":0, "sixes":0, "how_out": "Did Not Bat",
            "byBatsman": {}, "byBowler": {}, # Ensure these are present
            "batRunDenominationsObject": {}, "batOutTypesObject": {}, "batOutsRate": 0.08,
            "bowlRunDenominationsObject": {}, "bowlOutTypesObject": {}, "bowlOutsRate": 0.04,
            "bowlWideRate": 0.04, "bowlNoballRate": 0.0, "catchRate": 0.0,
            "overNumbersObject": {str(i):0.05 for i in range(20)}
        }

    def _preprocess_player_stats(self, initial, raw_stats_input):
        placeholder = self._create_placeholder_player_stats(initial)
        if raw_stats_input is None:
            processed = copy.deepcopy(placeholder)
            logging.warning(f"Using full placeholder for {initial} due to missing raw_stats_input.")
        else:
            processed = copy.deepcopy(raw_stats_input)
            for p_key, p_value in placeholder.items():
                if p_key not in processed: # Key missing from raw_stats
                    processed[p_key] = copy.deepcopy(p_value)
                # If key is present but should be a dict and isn't (e.g. data error from raw_stats)
                elif isinstance(p_value, dict) and not isinstance(processed.get(p_key), dict):
                     logging.warning(f"Correcting malformed dict for key '{p_key}' in player {initial}.")
                     processed[p_key] = copy.deepcopy(p_value)
                # Ensure nested dicts like byBatsman also get their structure if partially present
                elif isinstance(p_value, dict) and isinstance(processed.get(p_key), dict):
                    for inner_key, inner_default_value in p_value.items():
                        if inner_key not in processed[p_key]:
                             processed[p_key][inner_key] = copy.deepcopy(inner_default_value)


        processed['playerInitials'] = initial # Ensure this is always correct
        processed['displayName'] = initial  # Ensure this is always correct

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

        over_obj_processed = {str(i): 0.0 for i in range(20)}
        raw_over_numbers = processed.get('overNumbers', [])
        if isinstance(raw_over_numbers, list):
            over_counts = {str(i): 0 for i in range(20)}
            for over_num_val in raw_over_numbers:
                over_num_str = str(over_num_val)
                if over_num_str in over_counts: over_counts[over_num_str] +=1
            for k_over in over_obj_processed: over_obj_processed[k_over] = over_counts[k_over] / matches if matches > 0 else 0.0
        elif isinstance(raw_over_numbers, dict) :
             for k_over, v_over in raw_over_numbers.items():
                if str(k_over) in over_obj_processed: over_obj_processed[str(k_over)] = v_over
        processed['overNumbersObject'] = over_obj_processed

        # Ensure byBatsman and byBowler are dictionaries, even if empty
        if not isinstance(processed.get('byBatsman'), dict): processed['byBatsman'] = {}
        if not isinstance(processed.get('byBowler'), dict): processed['byBowler'] = {}

        return processed

    def _get_empty_innings_structure(self):
        return {'score': 0, 'wickets': 0, 'balls_bowled': 0, 'legal_balls_bowled':0, 'overs_completed': 0,
                'log': [], 'batting_tracker': {}, 'bowling_tracker': {},
                'batting_team_code': None, 'bowling_team_code': None}

    def _initialize_batting_order_and_bowlers(self):
        for team_code_iter, player_stats_pool in [(self.team1_code, self.team1_players_stats), (self.team2_code, self.team2_players_stats)]:
            ordered_initials = self.all_teams_data.get(team_code_iter, {}).get('players', [])
            self.batting_order[team_code_iter] = [p_initial for p_initial in ordered_initials if p_initial in player_stats_pool and player_stats_pool[p_initial]]
            if not self.batting_order[team_code_iter] and player_stats_pool:
                self.batting_order[team_code_iter] = [p_initial for p_initial in player_stats_pool.keys() if player_stats_pool[p_initial]]
            self.bowlers_list[team_code_iter] = [p_initial for p_initial, stats in player_stats_pool.items() if stats and stats.get('BowlingSkill') and stats['BowlingSkill'] not in ["", "None", None, "NA", "unknown", "Unknown"]]
            if not self.bowlers_list[team_code_iter] and player_stats_pool:
                self.bowlers_list[team_code_iter] = [p_initial for p_initial in player_stats_pool.keys() if player_stats_pool[p_initial]]
            if not self.bowlers_list[team_code_iter]:
                dummy_bowler_initial = f"Dummy_{team_code_iter}"
                self.bowlers_list[team_code_iter] = [dummy_bowler_initial]
                if dummy_bowler_initial not in player_stats_pool or not player_stats_pool[dummy_bowler_initial]:
                    player_stats_pool[dummy_bowler_initial] = self._create_placeholder_player_stats(dummy_bowler_initial)
            self.team_bowler_phases[team_code_iter]['powerplay'] = sorted([p for p in self.bowlers_list[team_code_iter] if p in player_stats_pool], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6)), reverse=True)
            self.team_bowler_phases[team_code_iter]['middle'] = sorted([p for p in self.bowlers_list[team_code_iter] if p in player_stats_pool], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6, 17)), reverse=True)
            self.team_bowler_phases[team_code_iter]['death'] = sorted([p for p in self.bowlers_list[team_code_iter] if p in player_stats_pool], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(17, 20)), reverse=True)

    def _setup_innings(self, innings_num):
        self.current_innings_num = innings_num
        current_batting_team = ""
        current_bowling_team = ""
        if innings_num == 1:
            current_batting_team = self.batting_team_code
            current_bowling_team = self.bowling_team_code
        else:
            current_batting_team = self.bowling_team_code
            current_bowling_team = self.batting_team_code
            self.target = self.innings[1]['score'] + 1
            if self.target <= 0: self.target = float('inf')
        self.innings[innings_num]['batting_team_code'] = current_batting_team
        self.innings[innings_num]['bowling_team_code'] = current_bowling_team
        self.innings[innings_num]['batting_tracker'] = { initial_key: {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': i + 1} for i, initial_key in enumerate(self.batting_order[current_batting_team])}
        self.innings[innings_num]['bowling_tracker'] = { initial_key: {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0} for initial_key in self.bowlers_list[current_bowling_team]}
        self.next_batsman_index[current_batting_team] = 0
        self.current_batsmen['on_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['on_strike']: self.innings[innings_num]['batting_tracker'].setdefault(self.current_batsmen['on_strike'], self._create_placeholder_player_stats(self.current_batsmen['on_strike']))['how_out'] = "Not out"
        self.current_batsmen['non_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['non_strike']: self.innings[innings_num]['batting_tracker'].setdefault(self.current_batsmen['non_strike'], self._create_placeholder_player_stats(self.current_batsmen['non_strike']))['how_out'] = "Not out"
        self.last_over_bowler_initial = None
        self.current_bowler = self._select_next_bowler()

    def _get_next_batsman(self, team_code, use_index_from_state=True):
        order = self.batting_order[team_code]; current_idx = self.next_batsman_index[team_code] if use_index_from_state else 0
        if current_idx < len(order):
            batsman_initial = order[current_idx]
            if use_index_from_state: self.next_batsman_index[team_code] += 1
            return batsman_initial
        return None

    def perform_toss(self):
        self.toss_winner = random.choice([self.team1_code, self.team2_code]); self.toss_decision = random.choice(['bat', 'field'])
        if self.toss_decision == 'bat': self.batting_team_code = self.toss_winner; self.bowling_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        else: self.bowling_team_code = self.toss_winner; self.batting_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        self.toss_message = f"{self.toss_winner.upper()} won the toss and chose to {self.toss_decision}."
        self.current_innings_num = 1
        self._setup_innings(1)
        return self.toss_message, self.toss_winner.upper(), self.toss_decision

    def _calculate_dynamic_probabilities(self, batsman_obj, bowler_obj, inn_data, bt_current_ball_stats):
        # ... (Copy of the existing _calculate_dynamic_probabilities method from the read_files output)
        denAvg = {str(r): (batsman_obj['batRunDenominationsObject'].get(str(r),0) + bowler_obj['bowlRunDenominationsObject'].get(str(r),0))/2 for r in range(7)}
        outAvg = (batsman_obj['batOutsRate'] + bowler_obj['bowlOutsRate']) / 2
        outTypeAvg = copy.deepcopy(bowler_obj['bowlOutTypesObject'])
        runout_chance_batsman = batsman_obj.get('runnedOut',0) / (batsman_obj.get('batBallsTotal',1) if batsman_obj.get('batBallsTotal',0) > 0 else 1)
        outTypeAvg['runOut'] = outTypeAvg.get('runOut', 0.005) + runout_chance_batsman / 2
        wideRate = bowler_obj['bowlWideRate']; noballRate = bowler_obj['bowlNoballRate']
        bowler_skill = bowler_obj.get('BowlingSkill', '').lower()
        if 'spin' in bowler_skill or 'break' in bowler_skill:
            effect = (1.0 - self.spin_factor) / 2
            outAvg += (effect * 0.1); outAvg = min(outAvg, 0.95) # Cap probability
            for r in ['4','6']: denAvg[r] = max(0.001, denAvg.get(r,0.001) * (1 - effect*2))
            denAvg['0'] = denAvg.get('0',0) + (effect*0.1); denAvg['1'] = denAvg.get('1',0) + (effect*0.05)
        elif 'fast' in bowler_skill or 'medium' in bowler_skill:
            effect = (1.0 - self.pace_factor) / 2
            outAvg += (effect * 0.1); outAvg = min(outAvg, 0.95)
            for r in ['4','6']: denAvg[r] = max(0.001, denAvg.get(r,0.001) * (1 - effect*2))
            denAvg['0'] = denAvg.get('0',0) + (effect*0.1); denAvg['1'] = denAvg.get('1',0) + (effect*0.05)
        for r in ['4','6']: denAvg[r] = denAvg.get(r,0) / self.outfield_factor
        balls_faced_batsman = bt_current_ball_stats['balls']; innings_balls_total = inn_data['legal_balls_bowled']
        innings_runs_total = inn_data['score']; innings_wickets_total = inn_data['wickets']
        if balls_faced_batsman < 8 and innings_balls_total < 80:
            adjust = random.uniform(-0.01, 0.03) * (1 if self.current_innings_num == 1 else 0.8)
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
            denAvg['6'] = max(0.001, denAvg.get('6',0) - adjust * 0.67); outAvg = min(0.95, outAvg + 0.05)
        if innings_balls_total < 36:
            outAvg = max(0.01, outAvg - (0.07 if innings_wickets_total == 0 else 0.03))
            adj = random.uniform(0.05, 0.11) if innings_wickets_total < 2 else random.uniform(0.02, 0.08)
            denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.67); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33)
            denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * (0.67 if innings_wickets_total < 2 else 0.83))
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * (0.33 if innings_wickets_total < 2 else 0.17))
        elif innings_balls_total >= 102:
            adj = random.uniform(0.07, 0.1) if innings_wickets_total < 7 else random.uniform(0.07,0.09)
            denAvg['0'] = max(0.001, denAvg.get('0',0) + adj * (0.13 if innings_wickets_total < 7 else -0.13))
            denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.48)
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.62); outAvg = min(0.95, outAvg + (0.015 if innings_wickets_total < 7 else 0.025))
        elif innings_balls_total >= 36 and innings_balls_total < 102:
            if innings_wickets_total < 3:
                adj = random.uniform(0.05, 0.11)
                denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.5); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.33)
                denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.5); denAvg['6'] = max(0.001, denAvg.get('6',0) + adj*0.33)
            else:
                adj = random.uniform(0.02, 0.07)
                denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.53); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.4)
                denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.7); denAvg['6'] = max(0.001, denAvg.get('6',0) + adj*0.3)
                outAvg = max(0.01, outAvg - 0.03)
        if self.current_innings_num == 2 and innings_balls_total < 120 and self.target > 0:
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
                    outAvg = min(0.95, outAvg - 0.01)
                elif rrr > 10.4:
                    adj = random.uniform(0.04,0.08) + (rrr*1.1)/1000
                    denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.5); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj*0.33)
                    denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.17); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj*0.67)
                    outAvg = min(0.95, outAvg + (0.02 + (rrr*1.1)/1000))
        current_sum = sum(d for d in denAvg.values() if isinstance(d, (int, float)) and d >= 0)
        if current_sum > 0 : denAvg = {k: max(0, v/current_sum) for k,v in denAvg.items()}
        else: denAvg = {"0":0.5, "1":0.5}; logging.warning(f"denAvg sum zero for {batsman_obj['playerInitials']} vs {bowler_obj['playerInitials']}. Using fallback.")
        current_out_type_sum = sum(v for v in outTypeAvg.values() if isinstance(v, (int,float)) and v > 0)
        if current_out_type_sum > 0: outTypeAvg = {k: max(0, v/current_out_type_sum) for k,v in outTypeAvg.items()}
        else: outTypeAvg = {"bowled": 1.0}; logging.warning(f"outTypeAvg sum zero for {batsman_obj['playerInitials']} vs {bowler_obj['playerInitials']}. Using fallback 'bowled'.")
        return denAvg, max(0.01, min(outAvg, 0.95)), outTypeAvg, max(0, wideRate), max(0, noballRate)

    def _select_next_bowler(self):
        current_over_to_be_bowled = self.innings[self.current_innings_num]['overs_completed']
        bowling_team_stat_pool = self.team1_players_stats if self.bowling_team_code == self.team1_code else self.team2_players_stats
        bowler_tracker_this_innings = self.innings[self.current_innings_num]['bowling_tracker']
        phase = 'powerplay' if current_over_to_be_bowled < 6 else ('death' if current_over_to_be_bowled >= 17 else 'middle')
        phase_specific_bowler_list = self.team_bowler_phases[self.bowling_team_code][phase]
        eligible_bowlers = []
        for initial in phase_specific_bowler_list:
            if initial not in bowling_team_stat_pool: continue
            tracker_stats = bowler_tracker_this_innings.get(initial, {'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0})
            if tracker_stats['balls_bowled'] >= 24: continue
            if initial == self.last_over_bowler_initial and len(self.bowlers_list[self.bowling_team_code]) > 1:
                if len(self.bowlers_list[self.bowling_team_code]) > 2 : continue
            economy = (tracker_stats['runs_conceded'] / (tracker_stats['balls_bowled'] / 6.0)) if tracker_stats['balls_bowled'] > 0 else 99.0
            score = economy - (tracker_stats['wickets'] * 10)
            score += tracker_stats['balls_bowled'] * 0.1
            eligible_bowlers.append({'initial': initial, 'score': score})
        if not eligible_bowlers:
            eligible_bowlers = [{'initial': b, 'score': random.random() + (100 if b == self.last_over_bowler_initial else 0) }
                                for b in self.bowlers_list[self.bowling_team_code]
                                if bowler_tracker_this_innings.get(b,{}).get('balls_bowled',0) < 24]
        if not eligible_bowlers:
             if self.bowlers_list[self.bowling_team_code]: return random.choice(self.bowlers_list[self.bowling_team_code])
             return self.last_over_bowler_initial
        eligible_bowlers.sort(key=lambda x: x['score'])
        return eligible_bowlers[0]['initial']

    def simulate_one_ball(self):
        if self.game_over: return {"summary": self.get_game_state(), "ball_event": {"commentary": f"Game is over. {self.win_message}"}}
        inn_data = self.innings[self.current_innings_num]; batsman_initial = self.current_batsmen['on_strike']; non_striker_initial = self.current_batsmen['non_strike']; bowler_initial = self.current_bowler
        if not batsman_initial: self._end_innings(); return {"summary": self.get_game_state(), "ball_event": {"commentary": "Innings ended: No batsman available."}}
        if not bowler_initial:
            self.current_bowler = self._select_next_bowler(); bowler_initial = self.current_bowler
            if not bowler_initial: self._end_innings(); return {"summary": self.get_game_state(), "ball_event": {"commentary": "Innings ended: No bowler available for " + self.bowling_team_code}}
        batsman_obj = self.team1_players_stats.get(batsman_initial) if self.batting_team_code == self.team1_code else self.team2_players_stats.get(batsman_initial)
        bowler_obj = self.team1_players_stats.get(bowler_initial) if self.bowling_team_code == self.team1_code else self.team2_players_stats.get(bowler_initial)
        if not batsman_obj: batsman_obj = self._create_placeholder_player_stats(batsman_initial)
        if not bowler_obj: bowler_obj = self._create_placeholder_player_stats(bowler_initial)
        batsman_tracker = inn_data['batting_tracker'].setdefault(batsman_initial, self._create_placeholder_player_stats(batsman_initial))
        bowler_tracker = inn_data['bowling_tracker'].setdefault(bowler_initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})
        denAvg, outAvg, outTypeAvg, wideRate, noballRate = self._calculate_dynamic_probabilities(batsman_obj, bowler_obj, inn_data, batsman_tracker)
        runs_this_ball = 0; is_wicket_this_ball = False; extra_type_this_ball = None; extra_runs_this_ball = 0; is_legal_delivery = True; commentary_this_ball = ""; wicket_details = {}
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
                wicket_details = {'type': wicket_type_chosen, 'bowler': bowler_initial, 'bowler_credit': True}
                batsman_tracker['how_out'] = wicket_type_chosen.capitalize(); batsman_tracker['bowler'] = bowler_initial
                bowler_tracker['wickets'] += 1; commentary_this_ball = f"{batsman_initial} is {wicket_type_chosen} by {bowler_initial}!"
                if wicket_type_chosen.lower() == 'caught':
                    fielding_team_pool = self.team1_players_stats if self.bowling_team_code == self.team1_code else self.team2_players_stats
                    possible_catchers_initials = [p_init for p_init in fielding_team_pool.keys() if p_init != bowler_initial]
                    catcher_initial = random.choice(possible_catchers_initials) if possible_catchers_initials else bowler_initial
                    batsman_tracker['fielder'] = catcher_initial; wicket_details['fielder'] = catcher_initial
                    commentary_this_ball = f"{batsman_initial} c {catcher_initial} b {bowler_initial} OUT!"
                elif wicket_type_chosen.lower() == 'runout': wicket_details['bowler_credit'] = False
                self.current_batsmen['on_strike'] = self._get_next_batsman(self.batting_team_code, use_index_from_state=True)
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
                if runs_this_ball == 0 and is_legal_delivery: bowler_tracker['dots'] = bowler_tracker.get('dots',0) + 1
        if is_legal_delivery:
            inn_data['balls_bowled'] += 1; inn_data['legal_balls_bowled'] +=1
            batsman_tracker['balls'] += 1; bowler_tracker['balls_bowled'] += 1
        ball_in_over_for_log = inn_data['legal_balls_bowled'] % 6
        if is_legal_delivery and ball_in_over_for_log == 0 and inn_data['legal_balls_bowled'] > 0: ball_in_over_for_log = 6
        ball_log_entry = {'ball_number': inn_data['legal_balls_bowled'], 'over_str': f"{inn_data['overs_completed']}.{ball_in_over_for_log}",
            'batsman_initial': batsman_initial, 'non_striker_initial': non_striker_initial, 'bowler_initial': bowler_initial,
            'runs_scored': runs_this_ball, 'is_wicket': is_wicket_this_ball, 'wicket_details': wicket_details,
            'is_extra': bool(extra_type_this_ball), 'extra_type': extra_type_this_ball, 'extra_runs': extra_runs_this_ball,
            'total_runs_ball': runs_this_ball + extra_runs_this_ball, 'commentary_text': commentary_this_ball,
            'score_after_ball': inn_data['score'], 'wickets_after_ball': inn_data['wickets']}
        inn_data['log'].append(ball_log_entry)
        if is_legal_delivery and runs_this_ball % 2 == 1: self.current_batsmen['on_strike'], self.current_batsmen['non_strike'] = self.current_batsmen['non_strike'], self.current_batsmen['on_strike']
        max_balls = 120; max_wickets = 10; game_ending_condition = False
        if inn_data['wickets'] >= max_wickets or not self.current_batsmen['on_strike']: game_ending_condition = True
        if self.current_innings_num == 2 and inn_data['score'] >= self.target: game_ending_condition = True
        if inn_data['legal_balls_bowled'] >= max_balls: game_ending_condition = True
        if game_ending_condition: self._end_innings()
        elif is_legal_delivery and inn_data['legal_balls_bowled'] % 6 == 0 and inn_data['legal_balls_bowled'] > 0:
            inn_data['overs_completed'] += 1; self.last_over_bowler_initial = self.current_bowler
            self.current_batsmen['on_strike'], self.current_batsmen['non_strike'] = self.current_batsmen['non_strike'], self.current_batsmen['on_strike']
            self.current_bowler = self._select_next_bowler()
        return {"summary": self.get_game_state(), "ball_event": ball_log_entry}

    def _end_innings(self):
        inn_data = self.innings[self.current_innings_num]
        inn_data['overs_completed'] = inn_data['legal_balls_bowled'] // 6
        for b_stats in inn_data['bowling_tracker'].values():
            if b_stats['balls_bowled'] > 0:
                b_stats['overs_str'] = f"{b_stats['balls_bowled'] // 6}.{b_stats['balls_bowled'] % 6}"
                b_stats['economy'] = (b_stats['runs_conceded'] / (b_stats['balls_bowled'] / 6.0)) if b_stats['balls_bowled'] > 0 else 0.0
        current_batting_team_of_ended_inning = inn_data['batting_team_code']
        current_bowling_team_of_ended_inning = inn_data['bowling_team_code']
        if self.current_innings_num == 1:
            self.batting_team_code = current_bowling_team_of_ended_inning
            self.bowling_team_code = current_batting_team_of_ended_inning
            self._setup_innings(2)
        else:
            self.game_over = True; s1 = self.innings[1]['score']; s2 = self.innings[2]['score']
            inn1_bat_team = self.innings[1]['batting_team_code']
            inn2_bat_team = self.innings[2]['batting_team_code']
            if s2 >= self.target: self.match_winner = inn2_bat_team; self.win_message = f"{self.match_winner.upper()} won by {10 - self.innings[2]['wickets']} wickets."
            elif s1 > s2: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."
            elif s1 == s2: self.match_winner = "Tie"; self.win_message = "Match Tied."
            else: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."

    def get_game_state(self):
        current_bat_team_code_for_state = None
        current_bowl_team_code_for_state = None
        if self.toss_winner:
            if self.current_innings_num == 1:
                current_bat_team_code_for_state = self.batting_team_code
                current_bowl_team_code_for_state = self.bowling_team_code
            elif self.current_innings_num == 2:
                current_bat_team_code_for_state = self.innings[2].get('batting_team_code', self.bowling_team_code)
                current_bowl_team_code_for_state = self.innings[2].get('bowling_team_code', self.batting_team_code)
            else:
                current_bat_team_code_for_state = self.batting_team_code
                current_bowl_team_code_for_state = self.bowling_team_code
        return {"team1_code": self.team1_code.upper(), "team2_code": self.team2_code.upper(),
            "current_innings_num": self.current_innings_num, "innings_data": self.innings,
            "on_strike": self.current_batsmen['on_strike'], "non_striker": self.current_batsmen['non_strike'],
            "current_bowler": self.current_bowler, "target_score": self.target, "game_over": self.game_over,
            "match_winner": self.match_winner.upper() if self.match_winner and self.match_winner != "Tie" else self.match_winner,
            "win_message": self.win_message, "toss_message": self.toss_message,
            "current_batting_team": current_bat_team_code_for_state.upper() if current_bat_team_code_for_state else None,
            "current_bowling_team": current_bowl_team_code_for_state.upper() if current_bowl_team_code_for_state else None,
            "team1_logo": self.team1_raw_data.get('logo'), "team1_primary_color": self.team1_raw_data.get('colorPrimary'),
            "team2_logo": self.team2_raw_data.get('logo'), "team2_primary_color": self.team2_raw_data.get('colorPrimary'),
        }
# --- New MatchSimulator Class END ---

[end of IPL-1.0/match_simulator.py]
