from flask import Flask, render_template, request, redirect, url_for, session, jsonify # Ensure jsonify is here
import json
import mainconnect # Import the game logic from mainconnect.py
# from match_simulator import MatchSimulator # MatchSimulator is no longer actively used for new game initiation from UI
import os
import copy # For deepcopy if needed by process_batting_innings
import uuid # For unique match IDs
import logging # For logging errors
import sqlite3
from datetime import datetime, timedelta # Ensure timedelta is here
# from flask import g # g can be imported if request-bound DB connections are planned later

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Points System Constants
NEW_USER_DEFAULT_COINS = 500
RATE_LIMIT_NEW_USERS_PER_IP = 2 # Max new users from one IP
RATE_LIMIT_WINDOW_HOURS = 24    # Within this many hours

ACTION_COSTS = {
    'direct_scorecard': 30,
    'ball_by_ball': 50
}

# Database Configuration
DATABASE_FILE = os.path.join(app.root_path, 'ipl_points.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # To access columns by name
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_points (
            client_id TEXT PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0,
            last_seen_ip TEXT,
            first_seen_timestamp TEXT NOT NULL,
            last_updated_timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.") # Optional: for logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Temporary directory for storing match logs
TMP_LOG_DIR = os.path.join(app.root_path, 'tmp_match_logs')
if not os.path.exists(TMP_LOG_DIR):
    try:
        os.makedirs(TMP_LOG_DIR)
    except OSError as e:
        logging.error(f"Error creating temporary log directory {TMP_LOG_DIR}: {e}")

# Initialize Database on startup
# This should be after all app config but before routes
with app.app_context():
    init_db()

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

scores_dir_path = os.path.join(os.getcwd(), "scores")
os.makedirs(scores_dir_path, exist_ok=True)
for f_remove in os.listdir(scores_dir_path):
    if os.path.isfile(os.path.join(scores_dir_path, f_remove)):
        try: os.remove(os.path.join(scores_dir_path, f_remove))
        except OSError as e: logging.warning(f"Error removing file {f_remove} from scores dir: {e}")


@app.route('/', methods=['GET'])
def index():
    teams_data = load_teams()
    session.pop('full_match_data', None)
    session.pop('sim_state', None)
    session.pop('replay_match_id', None)
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

        team1_s_name = teams_data.get(team1_code, {}).get('name', team1_code)
        team2_s_name = teams_data.get(team2_code, {}).get('name', team2_code)
        team1_full_name = teams_data.get(team1_code, {}).get('fullName', team1_s_name)
        team2_full_name = teams_data.get(team2_code, {}).get('fullName', team2_s_name)

        innings1_battracker_processed, wickets1_fallen = process_batting_innings(match_results.get("innings1Battracker", {}))
        innings2_battracker_processed, wickets2_fallen = process_batting_innings(match_results.get("innings2Battracker", {}))

        scorecard_data_for_template = {
            "team1": team1_code, "team2": team2_code,
            "team1_full_name": team1_full_name,
            "team2_full_name": team2_full_name,
            "match_teams_title": f"{team1_full_name} vs {team2_full_name}",
            "tossMsg": match_results.get("tossMsg"),
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

    team1_s_name = full_match_data.get('team1_data', {}).get('name', full_match_data.get('team1_code', 'Team 1'))
    team2_s_name = full_match_data.get('team2_data', {}).get('name', full_match_data.get('team2_code', 'Team 2'))

    return render_template('replay_ball_by_ball.html',
                           full_match_data=full_match_data,
                           team1_short_name=team1_s_name,
                           team2_short_name=team2_s_name)

# Routes for MatchSimulator based interactive simulation (currently disconnected from main UI flow)
# @app.route('/ball_by_ball_game_view')
# def ball_by_ball_game_view():
#     # ... (code for MatchSimulator based view) ...
# @app.route('/simulate_next_ball', methods=['POST'])
# def simulate_next_ball():
#     # ... (code for MatchSimulator based simulation call) ...

@app.route('/api/init_user_or_get_balance', methods=['POST'])
def init_user_or_get_balance():
    conn = None
    data = None
    try:
        data = request.get_json()
        if not data or 'client_id' not in data:
            return jsonify({"error": "Missing client_id"}), 400

        client_id = data['client_id']
        if not isinstance(client_id, str) or not (30 < len(client_id) < 70): # Basic check for UUID-like string
             return jsonify({"error": "Invalid client_id format"}), 400

        current_ip = request.remote_addr
        now_iso = datetime.utcnow().isoformat()

        conn = get_db_connection() # Assumes get_db_connection() is defined from previous step
        cursor = conn.cursor()

        cursor.execute("SELECT coins FROM user_points WHERE client_id = ?", (client_id,))
        user_row = cursor.fetchone()

        if user_row:
            # User exists, update last_seen_ip and last_updated_timestamp
            cursor.execute("""
                UPDATE user_points
                SET last_seen_ip = ?, last_updated_timestamp = ?
                WHERE client_id = ?
            """, (current_ip, now_iso, client_id))
            conn.commit()
            return jsonify({"coins": user_row['coins'], "status": "existing_user"})
        else:
            # New user, check rate limit for this IP
            limit_timestamp_iso = (datetime.utcnow() - timedelta(hours=RATE_LIMIT_WINDOW_HOURS)).isoformat()

            cursor.execute("""
                SELECT COUNT(*) FROM user_points
                WHERE last_seen_ip = ? AND first_seen_timestamp > ?
            """, (current_ip, limit_timestamp_iso))
            count_row = cursor.fetchone()
            ip_count_recent_new_users = count_row[0] if count_row and count_row[0] is not None else 0

            if ip_count_recent_new_users >= RATE_LIMIT_NEW_USERS_PER_IP:
                # Rate limit exceeded for this IP. Register user with 0 coins.
                cursor.execute("""
                    INSERT INTO user_points (client_id, coins, last_seen_ip, first_seen_timestamp, last_updated_timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, 0, current_ip, now_iso, now_iso))
                conn.commit()
                app.logger.info(f"Rate limit exceeded for IP {current_ip}. New client_id {client_id} registered with 0 coins.")
                return jsonify({"coins": 0, "status": "rate_limited"})
            else:
                # Rate limit OK, grant default coins
                cursor.execute("""
                    INSERT INTO user_points (client_id, coins, last_seen_ip, first_seen_timestamp, last_updated_timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, NEW_USER_DEFAULT_COINS, current_ip, now_iso, now_iso))
                conn.commit()
                app.logger.info(f"New client_id {client_id} registered for IP {current_ip} with {NEW_USER_DEFAULT_COINS} coins.")
                return jsonify({"coins": NEW_USER_DEFAULT_COINS, "status": "new_user"})
    except sqlite3.Error as e:
        client_id_for_log = data.get('client_id', 'N/A') if isinstance(data, dict) else 'N/A'
        app.logger.error(f"Database error in /api/init_user_or_get_balance for client_id {client_id_for_log}: {e}")
        return jsonify({"error": "Database operation failed", "details": str(e)}), 500
    except Exception as e:
        client_id_for_log = data.get('client_id', 'N/A') if isinstance(data, dict) else 'N/A'
        app.logger.error(f"Unexpected error in /api/init_user_or_get_balance for client_id {client_id_for_log}: {e}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/deduct_coins', methods=['POST'])
def deduct_coins():
    conn = None
    data = None # Initialize data to None for broader scope in error logging
    try:
        data = request.get_json()
        if not data or 'client_id' not in data or 'action_type' not in data:
            return jsonify({"success": False, "error": "Missing client_id or action_type"}), 400

        client_id = data['client_id']
        action_type = data['action_type']

        if not isinstance(client_id, str) or not (30 < len(client_id) < 70): # Basic check for UUID-like string
             return jsonify({"success": False, "error": "Invalid client_id format"}), 400

        if action_type not in ACTION_COSTS:
            return jsonify({"success": False, "error": "Invalid action_type"}), 400

        cost = ACTION_COSTS[action_type]
        now_iso = datetime.utcnow().isoformat()

        conn = get_db_connection() # Assumes get_db_connection() is defined
        cursor = conn.cursor()

        # Get current coins first
        cursor.execute("SELECT coins FROM user_points WHERE client_id = ?", (client_id,))
        user_row = cursor.fetchone()

        if not user_row:
            # This case should ideally be rare if client always calls init_user first.
            # Treat as insufficient funds or an error state.
            app.logger.warning(f"Attempt to deduct coins for non-existent client_id: {client_id}")
            # Optionally, initialize user here with 0 coins if strict flow not enforced client-side
            # For now, just deny.
            return jsonify({"success": False, "error": "User not found. Please initialize first."}), 404

        current_coins = user_row['coins']

        if current_coins < cost:
            return jsonify({"success": False, "error": "Insufficient coins", "current_balance": current_coins}), 403 # 403 Forbidden or 400 Bad Request

        # Deduct coins and update timestamp
        new_balance = current_coins - cost
        cursor.execute("""
            UPDATE user_points
            SET coins = ?, last_updated_timestamp = ?
            WHERE client_id = ?
        """, (new_balance, now_iso, client_id))
        conn.commit()

        app.logger.info(f"Deducted {cost} coins from client_id {client_id} for action {action_type}. New balance: {new_balance}")
        return jsonify({"success": True, "new_balance": new_balance})

    except sqlite3.Error as e:
        client_id_for_log = data.get('client_id', 'N/A') if isinstance(data, dict) else 'N/A'
        app.logger.error(f"Database error in /api/deduct_coins for client_id {client_id_for_log}: {e}")
        return jsonify({"success": False, "error": "Database operation failed", "details": str(e)}), 500
    except Exception as e:
        client_id_for_log = data.get('client_id', 'N/A') if isinstance(data, dict) else 'N/A'
        app.logger.error(f"Unexpected error in /api/deduct_coins for client_id {client_id_for_log}: {e}")
        return jsonify({"success": False, "error": "An unexpected error occurred", "details": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
