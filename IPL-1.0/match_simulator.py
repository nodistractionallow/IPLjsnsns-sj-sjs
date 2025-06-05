import random
import json
import accessJSON
import copy

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

        self.team1_players_stats = {}
        self.team2_players_stats = {}
        self.all_teams_data = {}
        try:
            with open('teams/teams.json', 'r', encoding='utf-8') as f:
                self.all_teams_data = json.load(f)
        except FileNotFoundError:
            print(f"CRITICAL ERROR: teams/teams.json not found.")
            raise

        # Store raw team data (for logo, colors etc.)
        self.team1_raw_data = self.all_teams_data.get(self.team1_code, {})
        self.team2_raw_data = self.all_teams_data.get(self.team2_code, {})

        team1_player_initials_list = self.team1_raw_data.get('players', [])
        team2_player_initials_list = self.team2_raw_data.get('players', [])

        if not team1_player_initials_list: raise ValueError(f"Player list for {self.team1_code} is empty/missing.")
        if not team2_player_initials_list: raise ValueError(f"Player list for {self.team2_code} is empty/missing.")

        # Call _initialize_fresh_game_state() early to set up default structures
        # It uses self.team1_code and self.team2_code which are set above.
        self._initialize_fresh_game_state()

        # Initialize player stats holders
        self.team1_players_stats = {}
        self.team2_players_stats = {}

        # Pre-process player stats for both teams
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

        # Initialize batting orders and bowler phase lists for BOTH teams (depends on processed stats)
        self._initialize_batting_order_and_bowlers()

        # If saved_state is provided, load it. This will overwrite parts of the fresh state.
        if saved_state and saved_state.get('toss_winner'):
            self.load_from_saved_state(saved_state)
        # Else (new game): _initialize_fresh_game_state already set current_innings_num = 0 etc.
        # app.py will call perform_toss() for a new game.


    def _initialize_fresh_game_state(self):
        # This method now correctly uses self.team1_code and self.team2_code for next_batsman_index keys
        self.batting_team_code = None; self.bowling_team_code = None
        self.current_batsmen = {'on_strike': None, 'non_strike': None}
        self.current_bowler = None
        self.last_over_bowler_initial = None
        self.current_innings_num = 0 # Will be 1 after toss
        self.innings = { 1: self._get_empty_innings_structure(), 2: self._get_empty_innings_structure() }
        self.target = 0; self.game_over = False; self.match_winner = None; self.win_message = ""
        self.toss_winner = None; self.toss_decision = None; self.toss_message = ""
        self.next_batsman_index = {self.team1_code: 0, self.team2_code: 0}
        # Player trackers will be initialized by _setup_innings when an innings starts


    def get_minimal_state_for_session(self):
        return {
            "team1_code": self.team1_code,
            "team2_code": self.team2_code,
            "toss_winner": self.toss_winner,
            "toss_decision": self.toss_decision,
            "toss_message": self.toss_message,
            "current_innings_num": self.current_innings_num,
            "game_over": self.game_over,
            "win_message": self.win_message,
            "match_winner": self.match_winner,
            "target": self.target,
            "innings1_log": self.innings[1]['log'],
            "innings2_log": self.innings[2]['log'],
            "next_batsman_index_team1": self.next_batsman_index.get(self.team1_code, 0),
            "next_batsman_index_team2": self.next_batsman_index.get(self.team2_code, 0),
            "last_over_bowler_initial": self.last_over_bowler_initial,
            # Include current score/wickets/overs for quick display if needed, though logs are source of truth
            "inning1_score": self.innings[1]['score'], "inning1_wickets": self.innings[1]['wickets'], "inning1_balls": self.innings[1]['legal_balls_bowled'],
            "inning2_score": self.innings[2]['score'], "inning2_wickets": self.innings[2]['wickets'], "inning2_balls": self.innings[2]['legal_balls_bowled'],
        }

    def load_from_saved_state(self, saved_state):
        # self.team1_code, self.team2_code already set by __init__
        # self.team1_players_stats, self.team2_players_stats already processed by __init__
        # self.batting_order, self.bowlers_list, self.team_bowler_phases already set by _initialize_batting_order_and_bowlers in __init__

        self.toss_winner = saved_state.get('toss_winner')
        self.toss_decision = saved_state.get('toss_decision')
        self.toss_message = saved_state.get('toss_message', "Toss information loaded.")

        if not self.toss_winner:
            print("Error: Saved state is missing toss winner. Cannot rehydrate properly.")
            self._initialize_fresh_game_state() # Fallback to a new game state
            return

        if self.toss_winner == self.team1_code:
            self.batting_team_code = self.team1_code if self.toss_decision == 'bat' else self.team2_code
            self.bowling_team_code = self.team2_code if self.toss_decision == 'bat' else self.team1_code
        else:
            self.batting_team_code = self.team2_code if self.toss_decision == 'bat' else self.team1_code
            self.bowling_team_code = self.team1_code if self.toss_decision == 'bat' else self.team2_code

        self.current_innings_num = saved_state.get('current_innings_num', 1)
        self.game_over = saved_state.get('game_over', False)
        self.win_message = saved_state.get('win_message', "")
        self.match_winner = saved_state.get('match_winner', None)
        self.target = saved_state.get('target', 0)

        self.next_batsman_index = {
            self.team1_code: saved_state.get('next_batsman_index_team1', 0),
            self.team2_code: saved_state.get('next_batsman_index_team2', 0)
        }
        self.last_over_bowler_initial = saved_state.get('last_over_bowler_initial')

        # Initialize innings structures (will be populated by replay)
        self.innings = { 1: self._get_empty_innings_structure(), 2: self._get_empty_innings_structure() }

        # Assign batting/bowling team codes to innings structures for clarity during replay/state access
        self.innings[1]['batting_team_code'] = self.batting_team_code if self.toss_decision == 'bat' and self.toss_winner == self.team1_code or \
                                               self.toss_decision == 'field' and self.toss_winner == self.team2_code else self.team2_code
        self.innings[1]['bowling_team_code'] = self.bowling_team_code if self.innings[1]['batting_team_code'] == self.team1_code else self.team1_code
        self.innings[2]['batting_team_code'] = self.innings[1]['bowling_team_code']
        self.innings[2]['bowling_team_code'] = self.innings[1]['batting_team_code']

        # Initialize trackers for ALL players on BOTH teams first
        # This ensures that even players who haven't batted/bowled yet have an entry if needed.
        # For team 1 (batting and bowling trackers)
        for initial in self.batting_order[self.team1_code]: self.innings[1]['batting_tracker'].setdefault(initial, {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': self.batting_order[self.team1_code].index(initial) +1})
        for initial in self.bowlers_list[self.team1_code]: self.innings[1]['bowling_tracker'].setdefault(initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})
        for initial in self.batting_order[self.team1_code]: self.innings[2]['batting_tracker'].setdefault(initial, {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': self.batting_order[self.team1_code].index(initial) +1})
        for initial in self.bowlers_list[self.team1_code]: self.innings[2]['bowling_tracker'].setdefault(initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})
        # For team 2
        for initial in self.batting_order[self.team2_code]: self.innings[1]['batting_tracker'].setdefault(initial, {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': self.batting_order[self.team2_code].index(initial) +1})
        for initial in self.bowlers_list[self.team2_code]: self.innings[1]['bowling_tracker'].setdefault(initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})
        for initial in self.batting_order[self.team2_code]: self.innings[2]['batting_tracker'].setdefault(initial, {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': self.batting_order[self.team2_code].index(initial) +1})
        for initial in self.bowlers_list[self.team2_code]: self.innings[2]['bowling_tracker'].setdefault(initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})

        self._replay_ball_log(saved_state.get('innings1_log', []), 1)
        self._replay_ball_log(saved_state.get('innings2_log', []), 2)

        self._update_current_players_after_replay()


    def _replay_ball_log(self, ball_log, innings_num_to_replay):
        inn_data = self.innings[innings_num_to_replay]
        # Determine batting/bowling team for the innings being replayed
        # This must be based on the initial toss, not current (potentially swapped) state
        if innings_num_to_replay == 1:
            batting_team_for_this_log = self.batting_team_code if self.current_innings_num == 1 else self.bowling_team_code
            bowling_team_for_this_log = self.bowling_team_code if self.current_innings_num == 1 else self.batting_team_code
        else: # Innings 2
            batting_team_for_this_log = self.bowling_team_code if self.current_innings_num == 1 else self.batting_team_code
            bowling_team_for_this_log = self.batting_team_code if self.current_innings_num == 1 else self.bowling_team_code

        inn_data['batting_team_code'] = batting_team_for_this_log
        inn_data['bowling_team_code'] = bowling_team_for_this_log


        for ball_event in ball_log:
            inn_data['log'].append(ball_event) # Add to internal log first

            batsman_initial = ball_event['batsman'] # Assuming log uses 'batsman'
            bowler_initial = ball_event['bowler']   # Assuming log uses 'bowler'

            runs_scored_on_ball = ball_event.get('runs', 0) # Runs off bat
            total_runs_this_delivery = ball_event.get('total_runs_ball', 0) # Includes extras

            inn_data['score'] += total_runs_this_delivery

            # Ensure trackers exist (should have been by _initialize_player_trackers in load_from_saved_state)
            batsman_tracker = inn_data['batting_tracker'].setdefault(batsman_initial, self._create_placeholder_player_stats(batsman_initial))
            bowler_tracker = inn_data['bowling_tracker'].setdefault(bowler_initial, {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0})


            is_legal_delivery_for_replay = not (ball_event.get('extra_type') == 'Wide' or ball_event.get('extra_type') == 'NoBall_TODO_ball_not_counted')

            if is_legal_delivery_for_replay:
                inn_data['legal_balls_bowled'] += 1
                batsman_tracker['balls'] += 1
                bowler_tracker['balls_bowled'] += 1

            inn_data['balls_bowled'] += 1 # Counts all deliveries including extras that are rebowled (not wides/noballs usually) - this might need refinement based on how extras are logged. For now, assume ball_event is one delivery.

            batsman_tracker['runs'] += runs_scored_on_ball
            if runs_scored_on_ball == 4: batsman_tracker['fours'] = batsman_tracker.get('fours',0) + 1
            if runs_scored_on_ball == 6: batsman_tracker['sixes'] = batsman_tracker.get('sixes',0) + 1
            if runs_scored_on_ball == 0 and is_legal_delivery_for_replay : bowler_tracker['dots'] = bowler_tracker.get('dots',0) + 1

            bowler_tracker['runs_conceded'] += total_runs_this_delivery

            if ball_event.get('is_wicket', False):
                inn_data['wickets'] += 1
                batsman_tracker['how_out'] = ball_event.get('wicket_details',{}).get('type', "Wicket")
                batsman_tracker['bowler'] = ball_event.get('wicket_details',{}).get('bowler', bowler_initial)
                batsman_tracker['fielder'] = ball_event.get('wicket_details',{}).get('fielder')
                if ball_event.get('wicket_details',{}).get('bowler_credit', True): # Default true
                     bowler_tracker['wickets'] += 1

        inn_data['overs_completed'] = inn_data['legal_balls_bowled'] // 6
        # Update bowler economy after replaying all logs for this innings
        for b_stats in inn_data['bowling_tracker'].values():
            if b_stats['balls_bowled'] > 0:
                b_stats['overs_str'] = f"{b_stats['balls_bowled'] // 6}.{b_stats['balls_bowled'] % 6}"
                b_stats['economy'] = (b_stats['runs_conceded'] / (b_stats['balls_bowled'] / 6.0)) if b_stats['balls_bowled'] > 0 else 0.0


    def _setup_initial_players_for_empty_innings(self, innings_num_to_setup):
        # Called by _update_current_players_after_replay if an innings log is empty
        # This means this innings is about to start.

        # Determine team batting in innings_num_to_setup
        if innings_num_to_setup == 1:
            current_batting_team = self.batting_team_code # As set by toss
            current_bowling_team = self.bowling_team_code
        else: # Innings 2
            current_batting_team = self.bowling_team_code # Teams would have swapped
            current_bowling_team = self.batting_team_code

        # Reset next_batsman_index for the team that is about to bat
        self.next_batsman_index[current_batting_team] = 0

        self.current_batsmen['on_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['on_strike']: self.innings[innings_num_to_setup]['batting_tracker'][self.current_batsmen['on_strike']]['how_out'] = "Not out"

        self.current_batsmen['non_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['non_strike']: self.innings[innings_num_to_setup]['batting_tracker'][self.current_batsmen['non_strike']]['how_out'] = "Not out"

        self.last_over_bowler_initial = None # Ensure fresh bowler selection for start of innings
        self.current_bowler = self._select_next_bowler() # Selects based on current_bowling_team and phase (likely 0th over)


    def _update_current_players_after_replay(self):
        active_innings_data = self.innings[self.current_innings_num]

        if self.game_over: return

        if active_innings_data['log']:
            last_event = active_innings_data['log'][-1]
            self.current_batsmen['on_strike'] = last_event.get('batsman') # Log should use 'batsman'
            self.current_batsmen['non_strike'] = last_event.get('non_striker_initial') # Ensure log has this
            self.current_bowler = last_event.get('bowler')

            # If an over was completed on the very last ball of the log
            if active_innings_data['legal_balls_bowled'] > 0 and active_innings_data['legal_balls_bowled'] % 6 == 0:
                self.last_over_bowler_initial = self.current_bowler
                self.current_bowler = self._select_next_bowler()
                # Strike rotation for new over
                self.current_batsmen['on_strike'], self.current_batsmen['non_strike'] = \
                    self.current_batsmen['non_strike'], self.current_batsmen['on_strike']
        else: # Active innings has no log, meaning it's the start of this innings
            self._setup_initial_players_for_empty_innings(self.current_innings_num)


    def _create_placeholder_player_stats(self, initial):
        # ... (as before)
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
        # ... (as before) ...
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
        over_obj_processed = {str(i): 0.0 for i in range(20)}
        if 'overNumbersObject' in processed and isinstance(processed['overNumbersObject'], dict):
            for k,v in processed['overNumbersObject'].items(): over_obj_processed[k] = v
        else:
            over_counts = {str(i): 0 for i in range(20)}
            for over_num_str in processed.get('overNumbers', []):
                valid_over_num_str = str(over_num_str)
                if valid_over_num_str in over_counts: over_counts[valid_over_num_str] +=1
            for k_over in over_obj_processed: over_obj_processed[k_over] = over_counts[k_over] / matches if matches > 0 else 0.0
        processed['overNumbersObject'] = over_obj_processed
        return processed

    def _get_empty_innings_structure(self):
        # ... (as before) ...
        return {'score': 0, 'wickets': 0, 'balls_bowled': 0, 'legal_balls_bowled':0, 'overs_completed': 0,
                'log': [], 'batting_tracker': {}, 'bowling_tracker': {},
                'batting_team_code': None, 'bowling_team_code': None}

    def _initialize_player_trackers(self, batting_team_code_for_innings, bowling_team_code_for_innings):
        # ... (as before) ...
        # This method might not be strictly needed if load_from_saved_state initializes trackers before replay
        # And _setup_innings initializes trackers for a new innings.
        # However, it can be a utility to ensure all players of a team have a tracker entry.
        # For rehydration, it's better to initialize all trackers for all players of both teams once in load_from_saved_state.
        pass # Logic moved to load_from_saved_state for rehydration, and _setup_innings for new


    def _initialize_batting_order_and_bowlers(self):
        # ... (as before, also creates self.team_bowler_phases) ...
        for team_code_iter, player_stats_pool in [(self.team1_code, self.team1_players_stats), (self.team2_code, self.team2_players_stats)]:
            ordered_initials = self.all_teams_data.get(team_code_iter, {}).get('players', [])
            self.batting_order[team_code_iter] = [p_initial for p_initial in ordered_initials if p_initial in player_stats_pool]
            if not self.batting_order[team_code_iter] and player_stats_pool: self.batting_order[team_code_iter] = list(player_stats_pool.keys())
            self.bowlers_list[team_code_iter] = [p_initial for p_initial, stats in player_stats_pool.items() if stats.get('BowlingSkill') and stats['BowlingSkill'] not in ["", "None", None, "NA", "unknown", "Unknown"]]
            if not self.bowlers_list[team_code_iter] and player_stats_pool: self.bowlers_list[team_code_iter] = list(player_stats_pool.keys())
            if not self.bowlers_list[team_code_iter]:
                dummy_bowler_initial = f"Dummy_{team_code_iter}"
                self.bowlers_list[team_code_iter] = [dummy_bowler_initial]
                if dummy_bowler_initial not in player_stats_pool: player_stats_pool[dummy_bowler_initial] = self._create_placeholder_player_stats(dummy_bowler_initial)
            self.team_bowler_phases[team_code_iter]['powerplay'] = sorted(self.bowlers_list[team_code_iter], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6)), reverse=True)
            self.team_bowler_phases[team_code_iter]['middle'] = sorted(self.bowlers_list[team_code_iter], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(6, 17)), reverse=True)
            self.team_bowler_phases[team_code_iter]['death'] = sorted(self.bowlers_list[team_code_iter], key=lambda p_init: sum(player_stats_pool[p_init]['overNumbersObject'].get(str(o), 0) for o in range(17, 20)), reverse=True)


    def _setup_innings(self, innings_num): # Called for NEW innings
        self.current_innings_num = innings_num # Corrected from self.current_innings

        # Initialize trackers for current batting/bowling team for this new innings
        # This assumes batting/bowling teams are already set for innings_num=1 (by perform_toss)
        # or swapped for innings_num=2
        current_batting_team = self.batting_team_code
        current_bowling_team = self.bowling_team_code
        if innings_num == 2: # If setting up for innings 2, roles would have swapped
            current_batting_team = self.bowling_team_code # Original bowler is now batter
            current_bowling_team = self.batting_team_code # Original batter is now bowler

        self.innings[innings_num]['batting_team_code'] = current_batting_team
        self.innings[innings_num]['bowling_team_code'] = current_bowling_team
        self.innings[innings_num]['batting_tracker'] = {
            initial_key: {'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'how_out': 'Did Not Bat', 'order': i + 1}
            for i, initial_key in enumerate(self.batting_order[current_batting_team])
        }
        self.innings[innings_num]['bowling_tracker'] = {
            initial_key: {'overs_str': "0.0", 'balls_bowled': 0, 'runs_conceded': 0, 'wickets': 0, 'maidens': 0, 'economy': 0.0, 'dots':0}
            for initial_key in self.bowlers_list[current_bowling_team]
        }

        self.next_batsman_index[current_batting_team] = 0 # Reset for this innings
        self.current_batsmen['on_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['on_strike']: self.innings[innings_num]['batting_tracker'][self.current_batsmen['on_strike']]['how_out'] = "Not out"
        self.current_batsmen['non_strike'] = self._get_next_batsman(current_batting_team, use_index_from_state=True)
        if self.current_batsmen['non_strike']: self.innings[innings_num]['batting_tracker'][self.current_batsmen['non_strike']]['how_out'] = "Not out"

        self.last_over_bowler_initial = None
        self.current_bowler = self._select_next_bowler()


    def _get_next_batsman(self, team_code, use_index_from_state=True): # Parameter added
        order = self.batting_order[team_code]
        # Determine which index to use
        current_idx = self.next_batsman_index[team_code] if use_index_from_state else 0 # Simplified: needs thought if not using state

        if current_idx < len(order):
            batsman_initial = order[current_idx]
            if use_index_from_state:
                self.next_batsman_index[team_code] += 1
            return batsman_initial
        return None

    def perform_toss(self): # Only for new games
        self.toss_winner = random.choice([self.team1_code, self.team2_code]); self.toss_decision = random.choice(['bat', 'field'])
        if self.toss_decision == 'bat': self.batting_team_code = self.toss_winner; self.bowling_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        else: self.bowling_team_code = self.toss_winner; self.batting_team_code = self.team1_code if self.toss_winner == self.team2_code else self.team2_code
        self.toss_message = f"{self.toss_winner.upper()} won the toss and chose to {self.toss_decision}."

        # _initialize_batting_order_and_bowlers() is already called in __init__
        self.current_innings_num = 1 # Set current innings to 1 after toss
        self._setup_innings(1) # Setup specifically for innings 1 with roles decided by toss
        return self.toss_message, self.toss_winner.upper(), self.toss_decision

    def _calculate_dynamic_probabilities(self, batsman_obj, bowler_obj, inn_data, bt_current_ball_stats):
        # ... (content as before) ...
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
            denAvg['6'] = max(0.001, denAvg.get('6',0) - adjust * 0.67); outAvg = min(0.9, outAvg + 0.05)
        if innings_balls_total < 36: # Powerplay
            outAvg = max(0.01, outAvg - (0.07 if innings_wickets_total == 0 else 0.03))
            adj = random.uniform(0.05, 0.11) if innings_wickets_total < 2 else random.uniform(0.02, 0.08)
            denAvg['0'] = max(0.001, denAvg.get('0',0) - adj * 0.67); denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33)
            denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * (0.67 if innings_wickets_total < 2 else 0.83))
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * (0.33 if innings_wickets_total < 2 else 0.17))
        elif innings_balls_total >= 102: # Death
            adj = random.uniform(0.07, 0.1) if innings_wickets_total < 7 else random.uniform(0.07,0.09)
            denAvg['0'] = max(0.001, denAvg.get('0',0) + adj * (0.13 if innings_wickets_total < 7 else -0.13))
            denAvg['1'] = max(0.001, denAvg.get('1',0) - adj * 0.33); denAvg['4'] = max(0.001, denAvg.get('4',0) + adj * 0.48)
            denAvg['6'] = max(0.001, denAvg.get('6',0) + adj * 0.62); outAvg = min(0.9, outAvg + (0.015 if innings_wickets_total < 7 else 0.025))
        elif innings_balls_total >= 36 and innings_balls_total < 102: # Middle
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
        # ... (content as before) ...
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
                if len(self.bowlers_list[self.bowling_team_code]) > 3 : continue
            economy = (tracker_stats['runs_conceded'] / (tracker_stats['balls_bowled'] / 6.0)) if tracker_stats['balls_bowled'] > 0 else 99.0
            score = economy - (tracker_stats['wickets'] * 10)
            score += tracker_stats['balls_bowled'] * 0.1
            eligible_bowlers.append({'initial': initial, 'score': score})
        if not eligible_bowlers:
            eligible_bowlers = [{'initial': b, 'score': random.random()} for b in self.bowlers_list[self.bowling_team_code] if bowler_tracker_this_innings.get(b,{}).get('balls_bowled',0) < 24]
        if not eligible_bowlers:
             return random.choice(self.bowlers_list[self.bowling_team_code]) if self.bowlers_list[self.bowling_team_code] else self.last_over_bowler_initial
        eligible_bowlers.sort(key=lambda x: x['score'])
        return eligible_bowlers[0]['initial']

    def simulate_one_ball(self):
        # ... (ensure ball_log_entry includes non_striker_initial and detailed wicket_details) ...
        if self.game_over: return {"summary": self.get_game_state(), "ball_event": {"commentary": f"Game is over. {self.win_message}"}}
        inn_data = self.innings[self.current_innings_num]; batsman_initial = self.current_batsmen['on_strike']; non_striker_initial = self.current_batsmen['non_strike']; bowler_initial = self.current_bowler
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
                wicket_details = {'type': wicket_type_chosen, 'bowler': bowler_initial, 'bowler_credit': True} # Default bowler credit
                batsman_tracker['how_out'] = wicket_type_chosen.capitalize(); batsman_tracker['bowler'] = bowler_initial
                bowler_tracker['wickets'] += 1; commentary_this_ball = f"{batsman_initial} is {wicket_type_chosen} by {bowler_initial}!"
                if wicket_type_chosen.lower() == 'caught':
                    fielding_team_players = self.team1_players_stats.keys() if self.bowling_team_code == self.team1_code else self.team2_players_stats.keys()
                    possible_catchers_initials = [p_init for p_init in fielding_team_players if p_init != bowler_initial]
                    catcher_initial = random.choice(possible_catchers_initials) if possible_catchers_initials else bowler_initial
                    batsman_tracker['fielder'] = catcher_initial; wicket_details['fielder'] = catcher_initial
                    commentary_this_ball = f"{batsman_initial} c {catcher_initial} b {bowler_initial} OUT!"
                elif wicket_type_chosen.lower() == 'runout': wicket_details['bowler_credit'] = False # Bowler doesn't get run out wicket
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
                if runs_this_ball == 0: bowler_tracker['dots'] = bowler_tracker.get('dots',0) + 1
        if is_legal_delivery:
            inn_data['balls_bowled'] += 1; inn_data['legal_balls_bowled'] +=1
            batsman_tracker['balls'] += 1; bowler_tracker['balls_bowled'] += 1
        ball_in_over_for_log = inn_data['legal_balls_bowled'] % 6 if is_legal_delivery else inn_data['balls_bowled'] % 6
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
        return {"summary": self.get_game_state(), "ball_event": ball_log_entry} # Ensure keys match what app.py expects

    def _end_innings(self):
        # ... (as before, but ensure current_innings_num is used) ...
        inn_data = self.innings[self.current_innings_num]
        inn_data['overs_completed'] = inn_data['legal_balls_bowled'] // 6
        for b_stats in inn_data['bowling_tracker'].values():
            if b_stats['balls_bowled'] > 0:
                b_stats['overs_str'] = f"{b_stats['balls_bowled'] // 6}.{b_stats['balls_bowled'] % 6}"
                b_stats['economy'] = (b_stats['runs_conceded'] / (b_stats['balls_bowled'] / 6.0)) if b_stats['balls_bowled'] > 0 else 0.0 # Corrected economy

        if self.current_innings_num == 1:
            # Before setting up innings 2, ensure current batting/bowling teams are correct for innings 1
            self.batting_team_code = self.innings[1]['batting_team_code']
            self.bowling_team_code = self.innings[1]['bowling_team_code']
            self._setup_innings(2)
        else:
            self.game_over = True; s1 = self.innings[1]['score']; s2 = self.innings[2]['score']
            # Ensure these are correctly assigned before this point based on toss
            inn1_bat_team = self.innings[1]['batting_team_code']
            inn2_bat_team = self.innings[2]['batting_team_code']
            if s2 >= self.target: self.match_winner = inn2_bat_team; self.win_message = f"{self.match_winner.upper()} won by {10 - self.innings[2]['wickets']} wickets."
            elif s1 > s2: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."
            elif s1 == s2: self.match_winner = "Tie"; self.win_message = "Match Tied."
            else: self.match_winner = inn1_bat_team; self.win_message = f"{self.match_winner.upper()} won by {s1 - s2} runs."

    def get_game_state(self):
        # ... (as before, ensure current_innings_num is used) ...
        return {"team1_code": self.team1_code.upper(), "team2_code": self.team2_code.upper(),
            "current_innings_num": self.current_innings_num, "innings_data": self.innings,
            "on_strike": self.current_batsmen['on_strike'], "non_strike": self.current_batsmen['non_strike'],
            "current_bowler": self.current_bowler, "target_score": self.target, "game_over": self.game_over,
            "match_winner": self.match_winner.upper() if self.match_winner and self.match_winner != "Tie" else self.match_winner,
            "win_message": self.win_message, "toss_message": self.toss_message,
            "current_batting_team": self.batting_team_code.upper() if self.batting_team_code else None, # This needs to reflect actual current batting team
            "current_bowling_team": self.bowling_team_code.upper() if self.bowling_team_code else None, # Same here
            "team1_logo": self.team1_raw_data.get('logo'), "team1_primary_color": self.team1_raw_data.get('colorPrimary'),
            "team2_logo": self.team2_raw_data.get('logo'), "team2_primary_color": self.team2_raw_data.get('colorPrimary'),
        }
# --- New MatchSimulator Class END ---
