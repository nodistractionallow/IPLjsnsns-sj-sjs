from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import mainconnect # Import the game logic from mainconnect.py
from match_simulator import MatchSimulator # Import the new simulator class
import os

app = Flask(__name__)
app.secret_key = os.urandom(24) # Needed for session management

# Load teams from teams/teams.json
def load_teams():
    try:
        with open('teams/teams.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: teams/teams.json not found. Please ensure the file exists.")
        return {} # Return empty dict or handle error as appropriate
    except json.JSONDecodeError:
        print("Error: Could not decode JSON from teams/teams.json.")
        return {}

# Ensure scores directory exists for mainconnect.py
dir_path = os.path.join(os.getcwd(), "scores")
os.makedirs(dir_path, exist_ok=True)
# Clean scores folder before starting (optional, based on doipl.py behavior)
for f_remove in os.listdir(dir_path):
    os.remove(os.path.join(dir_path, f_remove))

@app.route('/', methods=['GET'])
def index():
    teams_data = load_teams()
    return render_template('index.html', teams=teams_data, scorecard_data=None)

@app.route('/generate_scorecard', methods=['POST'])
def generate_scorecard():
    teams_data = load_teams()
    # Updated to get team codes from new hidden input fields in index.html
    team1_code = request.form.get('selectedTeam1')
    team2_code = request.form.get('selectedTeam2')
    simulation_type = request.form.get('simulation_type')

    if not team1_code or not team2_code:
        # Handle error: team codes not provided
        return redirect(url_for('index')) # Or show an error message

    if team1_code == team2_code:
        # Handle error: same team selected
        return redirect(url_for('index')) # Or show an error message

    if not simulation_type:
        # Handle error: simulation type not provided
        # This case should ideally not be reached if UI controls are correctly shown/hidden
        return redirect(url_for('index'))


    if simulation_type == 'direct':
        # Proceed with existing direct scorecard logic
        match_results = mainconnect.game(manual=False, sentTeamOne=team1_code, sentTeamTwo=team2_code, switch="webapp")

        # Adapt the match_results to the structure expected by index.html
        def process_batting_innings(bat_tracker):
            wickets = 0
            for player, stats in bat_tracker.items():
                stats['how_out'] = "Not out" # Default
                if not stats['ballLog']: # Did not bat
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
                                except (ValueError, IndexError):
                                    stats['how_out'] = "Caught"
                            elif "-runout" in event_details:
                                stats['how_out'] = "Run out"
                            elif "-Bowler-" in event_details:
                                try:
                                    details = event_details.split('-')
                                    dismissal_type = details[0][1:]
                                    bowler = details[details.index('Bowler') + 1]
                                    stats['how_out'] = f"{dismissal_type} b {bowler}"
                                except (ValueError, IndexError):
                                    stats['how_out'] = "Wicket"
                            else:
                                stats['how_out'] = "Wicket"
                            break
                if not wicket_found and stats['balls'] == 0 and stats['runs'] == 0:
                    is_dnb = True
                    for p_stats in bat_tracker.values():
                        if p_stats['balls'] > 0:
                            is_dnb = (stats['balls'] == 0)
                            break
                    if is_dnb:
                        stats['how_out'] = "DNB"
            return bat_tracker, wickets

        innings1_battracker_processed, wickets1_fallen = process_batting_innings(match_results.get("innings1Battracker", {}))
        innings2_battracker_processed, wickets2_fallen = process_batting_innings(match_results.get("innings2Battracker", {}))

        scorecard_data_for_template = {
            "team1": team1_code,
            "team2": team2_code,
            "tossMsg": match_results.get("tossMsg"),
            "innings1BatTeam": match_results.get("innings1BatTeam"),
            "innings1Runs": match_results.get("innings1Runs"),
            "innings1Wickets": wickets1_fallen,
            "innings1Balls": match_results.get("innings1Balls", 0),
            "innings1Battracker": innings1_battracker_processed,
            "innings1Bowltracker": match_results.get("innings1Bowltracker"),
            "innings2BatTeam": match_results.get("innings2BatTeam"),
            "innings2Runs": match_results.get("innings2Runs"),
            "innings2Wickets": wickets2_fallen,
            "innings2Balls": match_results.get("innings2Balls", 0),
            "innings2Battracker": innings2_battracker_processed,
            "innings2Bowltracker": match_results.get("innings2Bowltracker"),
            "winMsg": match_results.get("winMsg"),
            "winner": match_results.get("winner"),
            "innings1Log": match_results.get("innings1Log"),
            "innings2Log": match_results.get("innings2Log")
        }
        return render_template('index.html', teams=teams_data, scorecard_data=scorecard_data_for_template)

    elif simulation_type == 'ball_by_ball':
        try:
            simulator = MatchSimulator(team1_code, team2_code)
            toss_message, toss_winner, toss_decision = simulator.perform_toss()
            # Storing the simulator instance directly in session.
            # This might require custom serialization if MatchSimulator isn't directly pickleable.
            # For complex objects, consider storing __dict__ and reconstructing, or using Flask-Session with a proper backend.
            session['match_simulator_dict'] = simulator.__dict__
            session['team1_code'] = simulator.team1_code # Store codes for re-instantiation
            session['team2_code'] = simulator.team2_code

            # Instead of returning f-string, redirect to a new route that will render the ball_by_ball.html template
            return redirect(url_for('ball_by_ball_game_view'))
        except Exception as e:
            print(f"Error initializing MatchSimulator or performing toss: {e}")
            # Fallback or error message
            return redirect(url_for('index', error_message="Failed to start ball-by-ball simulation."))

    else:
        # Unknown simulation type, redirect to index
        return redirect(url_for('index'))

@app.route('/ball_by_ball_game_view')
def ball_by_ball_game_view():
    simulator_dict = session.get('match_simulator_dict')
    if not simulator_dict:
        return redirect(url_for('index', error_message="No simulation found. Please start a new game."))

    # Re-instantiate the simulator object from its dictionary representation
    # This is a common pattern if the object itself isn't directly session-serializable
    # or to ensure a fresh object that can have methods called.
    team1_code = session.get('team1_code')
    team2_code = session.get('team2_code')
    if not team1_code or not team2_code: # Should not happen if session is consistent
         return redirect(url_for('index', error_message="Session error. Please start a new game."))

    simulator = MatchSimulator(team1_code, team2_code) # Create a new instance
    simulator.__dict__.update(simulator_dict) # Load its state from the session dictionary

    # For now, we'll create a placeholder ball_by_ball.html if it doesn't exist.
    # The actual UI will be built in the next subtask.
    initial_game_state = simulator.get_game_state()
    return render_template('ball_by_ball.html', game_state=initial_game_state)


@app.route('/simulate_next_ball', methods=['POST'])
def simulate_next_ball():
    simulator_dict = session.get('match_simulator_dict')
    if not simulator_dict:
        return jsonify({"error": "No simulation found in session. Please start a new game."}), 400

    team1_code = session.get('team1_code')
    team2_code = session.get('team2_code')
    if not team1_code or not team2_code:
         return jsonify({"error": "Session error with team codes."}), 400

    simulator = MatchSimulator(team1_code, team2_code) # Re-instantiate
    simulator.__dict__.update(simulator_dict) # Load state

    try:
        ball_outcome_data = simulator.simulate_one_ball() # This should return both summary and ball_event
        session['match_simulator_dict'] = simulator.__dict__ # Save updated state

        # ball_outcome_data already contains 'summary' (which is get_game_state()) and 'ball_event'
        return jsonify(ball_outcome_data)
    except Exception as e:
        print(f"Error during simulate_next_ball: {e}")
        # Consider logging the full traceback for debugging
        # import traceback
        # traceback.print_exc()
        return jsonify({"error": f"An error occurred during simulation: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
