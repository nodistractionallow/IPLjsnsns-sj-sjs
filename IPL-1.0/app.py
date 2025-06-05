from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import mainconnect # Import the game logic from mainconnect.py
# from match_simulator import MatchSimulator # MatchSimulator is no longer actively used for new game initiation from UI
import os
import copy # For deepcopy if needed by process_batting_innings
import uuid # For unique match IDs
import logging # For logging errors

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Temporary directory for storing match logs
TMP_LOG_DIR = os.path.join(app.root_path, 'tmp_match_logs')
if not os.path.exists(TMP_LOG_DIR):
    try:
        os.makedirs(TMP_LOG_DIR)
    except OSError as e:
        logging.error(f"Error creating temporary log directory {TMP_LOG_DIR}: {e}")
        # Depending on the application's needs, you might want to exit or handle this more gracefully.


# --- Helper Functions ---
def load_teams():
    try:
        with open('teams/teams.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("teams/teams.json not found.")
        return {}
    except json.JSONDecodeError:
        logging.error("Could not decode JSON from teams/teams.json.")
        return {}

def process_batting_innings(bat_tracker_original):
    bat_tracker = copy.deepcopy(bat_tracker_original)
    wickets = 0
    for player, stats in bat_tracker.items():
        stats['how_out'] = "Not out"
        if not stats.get('ballLog'):
            stats['how_out'] = "DNB"
            stats['runs'] = stats.get('runs', '')
            stats['balls'] = stats.get('balls', '')
            continue
        wicket_found = False
        for log_entry in stats['ballLog']:
            parts = log_entry.split(':')
            if len(parts) > 1:
                event_details = parts[1]
                if event_details.startswith("W"):
                    wickets += 1
                    wicket_found = True
                    if "-CaughtBy-" in event_details:
                        try:
                            details = event_details.split('-')
                            catcher = details[details.index('CaughtBy') + 1]
                            bowler = details[details.index('Bowler') + 1]
                            stats['how_out'] = f"c {catcher} b {bowler}"
                        except (ValueError, IndexError): stats['how_out'] = "Caught"
                    elif "-runout" in event_details: stats['how_out'] = "Run out"
                    elif "-Bowler-" in event_details:
                        try:
                            details = event_details.split('-')
                            dismissal_type = details[0][1:]
                            bowler = details[details.index('Bowler') + 1]
                            stats['how_out'] = f"{dismissal_type} b {bowler}"
                        except (ValueError, IndexError): stats['how_out'] = "Wicket"
                    else: stats['how_out'] = "Wicket"
                    break
        if not wicket_found and stats.get('balls', 0) == 0 and stats.get('runs', 0) == 0:
            any_other_batted = False
            for p_stats_check in bat_tracker.values():
                if p_stats_check.get('balls',0) > 0 :
                    any_other_batted = True
                    break
            if any_other_batted :
                stats['how_out'] = "DNB"
    return bat_tracker, wickets
# --- End Helper Functions ---

# Ensure scores directory exists for mainconnect.py (original functionality)
scores_dir_path = os.path.join(os.getcwd(), "scores")
os.makedirs(scores_dir_path, exist_ok=True)
# Clean scores folder before starting (optional, based on doipl.py behavior)
for f_remove in os.listdir(scores_dir_path):
    if os.path.isfile(os.path.join(scores_dir_path, f_remove)):
        try: os.remove(os.path.join(scores_dir_path, f_remove))
        except OSError as e: logging.warning(f"Error removing file {f_remove} from scores dir: {e}")


@app.route('/', methods=['GET'])
def index():
    teams_data = load_teams()
    session.pop('full_match_data', None) # For old session storage method (if any)
    session.pop('sim_state', None)       # For MatchSimulator based session state (if any)
    session.pop('replay_match_id', None) # For file-based session state
    return render_template('index.html', teams=teams_data, scorecard_data=None)

@app.route('/generate_scorecard', methods=['POST'])
def generate_scorecard():
    teams_data = load_teams()
    team1_code = request.form.get('selectedTeam1')
    team2_code = request.form.get('selectedTeam2')
    simulation_type = request.form.get('simulation_type')

    if not team1_code or not team2_code: return redirect(url_for('index', error_message="Please select two teams."))
    if team1_code == team2_code: return redirect(url_for('index', error_message="Please select two different teams."))
    if not simulation_type: return redirect(url_for('index', error_message="Please select a simulation type."))

    if simulation_type == 'direct':
        match_results = mainconnect.game(manual=False, sentTeamOne=team1_code, sentTeamTwo=team2_code, switch="webapp")
        innings1_battracker_processed, wickets1_fallen = process_batting_innings(match_results.get("innings1Battracker", {}))
        innings2_battracker_processed, wickets2_fallen = process_batting_innings(match_results.get("innings2Battracker", {}))
        scorecard_data_for_template = {
            "team1": team1_code, "team2": team2_code, "tossMsg": match_results.get("tossMsg"),
            "innings1BatTeam": match_results.get("innings1BatTeam"), "innings1Runs": match_results.get("innings1Runs"),
            "innings1Wickets": wickets1_fallen, "innings1Balls": match_results.get("innings1Balls", 0),
            "innings1Battracker": innings1_battracker_processed, "innings1Bowltracker": match_results.get("innings1Bowltracker"),
            "innings2BatTeam": match_results.get("innings2BatTeam"), "innings2Runs": match_results.get("innings2Runs"),
            "innings2Wickets": wickets2_fallen, "innings2Balls": match_results.get("innings2Balls", 0),
            "innings2Battracker": innings2_battracker_processed, "innings2Bowltracker": match_results.get("innings2Bowltracker"),
            "winMsg": match_results.get("winMsg"), "winner": match_results.get("winner"),
            "innings1Log": match_results.get("innings1Log"), "innings2Log": match_results.get("innings2Log")
        }
        return render_template('index.html', teams=teams_data, scorecard_data=scorecard_data_for_template)

    elif simulation_type == 'ball_by_ball':
        match_results = mainconnect.game(manual=False, sentTeamOne=team1_code, sentTeamTwo=team2_code, switch="webapp_full_log")
        innings1_battracker_original = match_results.get("innings1Battracker", {})
        innings2_battracker_original = match_results.get("innings2Battracker", {})
        processed_bat_tracker1, wickets1_fallen = process_batting_innings(innings1_battracker_original)
        processed_bat_tracker2, wickets2_fallen = process_batting_innings(innings2_battracker_original)
        team1_full_data = teams_data.get(team1_code, {})
        team2_full_data = teams_data.get(team2_code, {})

        full_match_data_to_save = {
            "toss_msg": match_results.get("tossMsg"), "team1_code": team1_code, "team2_code": team2_code,
            "team1_data": team1_full_data, "team2_data": team2_full_data,
            "innings1_log": match_results.get("innings1Log", []), "innings2_log": match_results.get("innings2Log", []),
            "innings1_bat_team": match_results.get("innings1BatTeam"), "innings2_bat_team": match_results.get("innings2BatTeam"),
            "innings1_runs": match_results.get("innings1Runs"), "innings1_wickets": wickets1_fallen,
            "innings1_balls": match_results.get("innings1Balls", 0),
            "innings2_runs": match_results.get("innings2Runs"), "innings2_wickets": wickets2_fallen,
            "innings2_balls": match_results.get("innings2Balls", 0),
            "win_msg": match_results.get("winMsg"), "winner": match_results.get("winner"),
            "innings1_battracker": processed_bat_tracker1, "innings2_battracker": processed_bat_tracker2,
            "innings1_bowltracker": match_results.get("innings1Bowltracker", {}),
            "innings2_bowltracker": match_results.get("innings2Bowltracker", {})
        }

        match_id = str(uuid.uuid4())
        tmp_file_path = os.path.join(TMP_LOG_DIR, f"match_log_{match_id}.json")

        try:
            with open(tmp_file_path, 'w') as f:
                json.dump(full_match_data_to_save, f)
            session['replay_match_id'] = match_id
        except IOError as e:
            logging.error(f"Error saving match log to {tmp_file_path}: {e}")
            return redirect(url_for('index', error_message="Failed to save match data for replay."))

        return redirect(url_for('replay_match_view'))
    else:
        return redirect(url_for('index', error_message="Invalid simulation type selected."))

@app.route('/replay_match_view')
def replay_match_view():
    match_id = session.get('replay_match_id')
    if not match_id:
        return redirect(url_for('index', error_message="No match ID found for replay."))

    tmp_file_path = os.path.join(TMP_LOG_DIR, f"match_log_{match_id}.json")

    try:
        with open(tmp_file_path, 'r') as f:
            full_match_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"Match log file not found: {tmp_file_path}")
        session.pop('replay_match_id', None)
        return redirect(url_for('index', error_message="Match data not found. It might have expired or an error occurred."))
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding match log JSON from {tmp_file_path}: {e}")
        session.pop('replay_match_id', None)
        return redirect(url_for('index', error_message="Error reading match data."))

    return render_template('replay_ball_by_ball.html', full_match_data=full_match_data)

# Routes for MatchSimulator based interactive simulation (currently disconnected from main UI flow)
# @app.route('/ball_by_ball_game_view')
# def ball_by_ball_game_view():
#     # ... (code for MatchSimulator based view) ...
# @app.route('/simulate_next_ball', methods=['POST'])
# def simulate_next_ball():
#     # ... (code for MatchSimulator based simulation call) ...

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
