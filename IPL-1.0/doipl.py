import os
import sys
import random
from mainconnect import game
from tabulate import tabulate
import copy

# Ensure scores directory exists
dir_path = os.path.join(os.getcwd(), "scores")
os.makedirs(dir_path, exist_ok=True)

# Clean scores folder before starting
for f in os.listdir(dir_path):
    os.remove(os.path.join(dir_path, f))

teams = ['dc', 'csk', 'rcb', 'mi', 'kkr', 'pbks', 'rr', 'srh']
points = {}
battingInfo = {}
bowlingInfo = {}

# Initialize points table
for team in teams:
    points[team] = {
        "P": 0, "W": 0, "L": 0, "T": 0,
        "runsScored": 0, "ballsFaced": 0,
        "runsConceded": 0, "ballsBowled": 0,
        "pts": 0
    }

battingf = 0
bowlingf = 0

# Enhanced commentary lines for different events
commentary_lines = {
    'start': [
        "It's a packed stadium today, folks! The atmosphere is electric!",
        "The players are ready, and the crowd is roaring for action!",
        "What a perfect day for some thrilling cricket!"
    ],
    '0': [
        "Good ball! Dot ball, no run scored.",
        "Tight bowling, the batsman defends solidly.",
        "No run, excellent line and length from the bowler!"
    ],
    '1': [
        "Quick single taken, good running between the wickets!",
        "Pushed for a single, smart cricket.",
        "One run added to the total, tidy shot."
    ],
    '2': [
        "Nicely placed for a couple of runs!",
        "Two runs, good placement in the gap.",
        "Driven for two, excellent running!"
    ],
    '3': [
        "Three runs! Brilliant effort in the field to stop the boundary.",
        "Rare three runs, well-judged by the batsmen.",
        "Three to the total, superb running!"
    ],
    '4': [
        "FOUR! Cracked through the covers, what a shot!",
        "Boundary! Perfectly timed, races to the fence.",
        "FOUR runs! That’s a glorious cover drive!"
    ],
    '6': [
        "SIX! Launched over the stands, what a hit!",
        "Huge SIX! That’s gone miles into the crowd!",
        "Maximum! Smashed with authority!"
    ],
    'wicket': [
        "OUT! Bowled him! The stumps are shattered!",
        "Caught! Brilliant grab in the deep, big wicket down!",
        "GONE! Cleaned up with a peach of a delivery!"
    ],
    'wide': [
        "Wide ball! The bowler strays down the leg side.",
        "Called wide, too far outside off stump.",
        "Extra run! Wide from the bowler."
    ],
    'end': [
        "What a match that was, folks! A true spectacle!",
        "The crowd is buzzing after that thrilling finish!",
        "A game to remember for years to come!"
    ],
    'innings_end': [
        "That’s the end of the innings. A solid total on the board!",
        "Innings wrapped up, setting up an exciting chase!",
        "End of the batting effort, now over to the bowlers!"
    ]
}

def display_points_table():
    pointsTabulate = []
    for team in points:
        data = points[team]
        nrr = 0
        if data['ballsFaced'] > 0 and data['ballsBowled'] > 0:
            nrr = (data['runsScored'] / data['ballsFaced']) * 6 - (data['runsConceded'] / data['ballsBowled']) * 6
        row = [team.upper(), data['P'], data['W'], data['L'], data['T'], round(nrr, 2), data['pts']]
        pointsTabulate.append(row)
    pointsTabulate = sorted(pointsTabulate, key=lambda x: (x[6], x[5]), reverse=True)
    print("\nCurrent Points Table:")
    print(tabulate(pointsTabulate, headers=["Team", "Played", "Won", "Lost", "Tied", "NRR", "Points"], tablefmt="grid"))

def display_top_players():
    battingTabulate = []
    for b in battingInfo:
        c = battingInfo[b]
        outs = sum(1 for bl in c['ballLog'] if "W" in bl)
        avg = round(c['runs'] / outs, 2) if outs else float('inf')
        sr = round((c['runs'] / c['balls']) * 100, 2) if c['balls'] else 0
        battingTabulate.append([b, c['runs'], avg, sr])
    battingTabulate = sorted(battingTabulate, key=lambda x: x[1], reverse=True)[:3]
    
    print("\nTop 3 Batsmen:")
    print(tabulate(battingTabulate, headers=["Player", "Runs", "Average", "Strike Rate"], tablefmt="grid"))

    bowlingTabulate = []
    for b in bowlingInfo:
        c = bowlingInfo[b]
        economy = round((c['runs'] / c['balls']) * 6, 2) if c['balls'] else float('inf')
        bowlingTabulate.append([b, c['wickets'], economy])
    bowlingTabulate = sorted(bowlingTabulate, key=lambda x: x[1], reverse=True)[:3]
    
    print("\nTop 3 Bowlers:")
    print(tabulate(bowlingTabulate, headers=["Player", "Wickets", "Economy"], tablefmt="grid"))

def display_scorecard(bat_tracker, bowl_tracker, team_name, innings_num):
    print(f"\n--- {team_name.upper()} Scorecard: Innings {innings_num} ---")
    
    # Batting Scorecard
    batsmanTabulate = []
    for player in bat_tracker:
        data = bat_tracker[player]
        runs = data['runs']
        balls = data['balls']
        sr = round((runs / balls) * 100, 2) if balls else 'NA'
        how_out = "DNB"
        batted = False
        for log in data['ballLog']:
            batted = True
            if "W" in log:
                if "CaughtBy" in log:
                    split_log = log.split("-")
                    catcher = split_log[2]
                    bowler = split_log[-1]
                    how_out = f"c {catcher} b {bowler}"
                elif "runout" in log:
                    how_out = "Run out"
                else:
                    split_log = log.split("-")
                    out_type = split_log[1]
                    bowler = split_log[-1]
                    how_out = f"{out_type} b {bowler}"
            else:
                how_out = "Not out" if balls > 0 else "DNB"
        if batted or balls > 0:
            batsmanTabulate.append([player, runs, balls, sr, how_out])
    
    print("\nBatting:")
    print(tabulate(batsmanTabulate, headers=["Player", "Runs", "Balls", "SR", "How Out"], tablefmt="grid"))

    # Bowling Scorecard
    bowlerTabulate = []
    for player in bowl_tracker:
        data = bowl_tracker[player]
        runs = data['runs']
        balls = data['balls']
        wickets = data['wickets']
        overs = f"{balls // 6}.{balls % 6}" if balls else "0.0"
        economy = round((runs / balls) * 6, 2) if balls else 'NA'
        bowlerTabulate.append([player, overs, runs, wickets, economy])
    
    print("\nBowling:")
    print(tabulate(bowlerTabulate, headers=["Player", "Overs", "Runs", "Wickets", "Economy"], tablefmt="grid"))

def display_ball_by_ball(innings_log, innings_num, team_name, runs, balls, wickets, bat_tracker, bowl_tracker):
    print(f"\n--- Innings {innings_num}: {team_name} Batting ---")
    for event in innings_log:
        outcome = event['event'].split()[-2]  # Extract outcome (e.g., '4', 'W', 'Wide')
        commentary_key = outcome if outcome in commentary_lines else ('wicket' if 'W' in outcome else '0')
        print(f"Ball {event['balls']}: {event['event']} - {random.choice(commentary_lines[commentary_key])}")
    overs = f"{balls // 6}.{balls % 6}"
    print(f"\nInnings Total: {runs}/{wickets} in {overs} overs")
    print(random.choice(commentary_lines['innings_end']))
    
    # Display scorecard after innings
    display_scorecard(bat_tracker, bowl_tracker, team_name, innings_num)

# League Matches
for i in range(len(teams)):
    for j in range(i + 1, len(teams)):
        team1, team2 = teams[i], teams[j]
        print(f"\nMatch: {team1.upper()} vs {team2.upper()}")
        
        try:
            input("Press Enter to start the match...")
            
            print(random.choice(commentary_lines['start']))
            
            resList = game(False, team1, team2)

            # Display ball-by-ball and innings summary for both innings
            for innings, team_key, runs_key, balls_key, bat_tracker_key, bowl_tracker_key in [
                ('innings1Log', 'innings1BatTeam', 'innings1Runs', 'innings1Balls', 'innings1Battracker', 'innings1Bowltracker'),
                ('innings2Log', 'innings2BatTeam', 'innings2Runs', 'innings2Balls', 'innings2Battracker', 'innings2Bowltracker')
            ]:
                display_ball_by_ball(
                    resList[innings],
                    1 if innings == 'innings1Log' else 2,
                    resList[team_key],
                    resList[runs_key],
                    resList[balls_key],
                    max([event['wickets'] for event in resList[innings]], default=0),
                    resList[bat_tracker_key],
                    resList[bowl_tracker_key]
                )

            print(f"\nResult: {resList['winMsg']}")
            print(random.choice(commentary_lines['end']))

            # Track batting/bowling format win
            if "runs" in resList['winMsg']:
                battingf += 1
            else:
                bowlingf += 1

            # Update batting stats
            for bat_map in [('innings1Battracker', 'innings1BatTeam'), ('innings2Battracker', 'innings2BatTeam')]:
                bat_tracker = resList[bat_map[0]]
                for player in bat_tracker:
                    if player not in battingInfo:
                        battingInfo[player] = copy.deepcopy(bat_tracker[player])
                        battingInfo[player]['innings'] = 1
                        battingInfo[player]['scoresArray'] = [int(battingInfo[player]['runs'])]
                    else:
                        battingInfo[player]['balls'] += bat_tracker[player]['balls']
                        battingInfo[player]['runs'] += bat_tracker[player]['runs']
                        battingInfo[player]['ballLog'] += bat_tracker[player]['ballLog']
                        battingInfo[player]['innings'] += 1
                        battingInfo[player]['scoresArray'].append(int(bat_tracker[player]['runs']))

            # Update bowling stats
            for bowl_map in [('innings1Bowltracker',), ('innings2Bowltracker',)]:
                bowl_tracker = resList[bowl_map[0]]
                for player in bowl_tracker:
                    if player not in bowlingInfo:
                        bowlingInfo[player] = copy.deepcopy(bowl_tracker[player])
                        bowlingInfo[player]['matches'] = 1
                    else:
                        bowlingInfo[player]['balls'] += bowl_tracker[player]['balls']
                        bowlingInfo[player]['runs'] += bowl_tracker[player]['runs']
                        bowlingInfo[player]['ballLog'] += bowl_tracker[player]['ballLog']
                        bowlingInfo[player]['wickets'] += bowl_tracker[player]['wickets']
                        bowlingInfo[player]['matches'] += 1

            # Points Table Update
            teamA = resList['innings1BatTeam']
            teamB = resList['innings2BatTeam']
            teamARuns, teamABalls = resList['innings1Runs'], resList['innings1Balls']
            teamBRuns, teamBBalls = resList['innings2Runs'], resList['innings2Balls']
            winner = resList['winner']
            loser = team1 if winner == team2 else team2

            for t in [team1, team2]:
                points[t]['P'] += 1

            if winner == "tie":
                for t in [team1, team2]:
                    points[t]['T'] += 1
                    points[t]['pts'] += 1
            else:
                points[winner]['W'] += 1
                points[loser]['L'] += 1
                points[winner]['pts'] += 2

            points[teamA]['runsScored'] += teamARuns
            points[teamB]['runsScored'] += teamBRuns
            points[teamA]['runsConceded'] += teamBRuns
            points[teamB]['runsConceded'] += teamARuns
            points[teamA]['ballsFaced'] += teamABalls
            points[teamB]['ballsFaced'] += teamBBalls
            points[teamA]['ballsBowled'] += teamBBalls
            points[teamB]['ballsBowled'] += teamABalls

            display_points_table()
            display_top_players()

            # Pause after match to keep console open
            input("Press Enter to continue to the next match...")

        except Exception as e:
            print(f"Error during match {team1.upper()} vs {team2.upper()}: {str(e)}")
            input("Press Enter to continue or Ctrl+C to exit...")
            continue

# POINTS TABLE (Final)
display_points_table()

# === PLAYOFFS ===
def playoffs(team1, team2, matchtag):
    print(f"\n{matchtag.upper()} - {team1.upper()} vs {team2.upper()}")
    try:
        input("Press Enter to start the playoff match...")
        print(random.choice(commentary_lines['start']))
        
        res = game(False, team1.lower(), team2.lower(), matchtag)
        
        for innings, team_key, runs_key, balls_key, bat_tracker_key, bowl_tracker_key in [
            ('innings1Log', 'innings1BatTeam', 'innings1Runs', 'innings1Balls', 'innings1Battracker', 'innings1Bowltracker'),
            ('innings2Log', 'innings2BatTeam', 'innings2Runs', 'innings2Balls', 'innings2Battracker', 'innings2Bowltracker')
        ]:
            display_ball_by_ball(
                res[innings],
                1 if innings == 'innings1Log' else 2,
                res[team_key],
                res[runs_key],
                res[balls_key],
                max([event['wickets'] for event in res[innings]], default=0),
                res[bat_tracker_key],
                res[bowl_tracker_key]
            )
        
        print(f"\nResult: {res['winMsg'].upper()}")
        print(random.choice(commentary_lines['end']))

        winner = res['winner']
        loser = team1 if winner == team2 else team2

        for bat_map in ['innings1Battracker', 'innings2Battracker']:
            tracker = res[bat_map]
            for player in tracker:
                if player not in battingInfo:
                    battingInfo[player] = copy.deepcopy(tracker[player])
                    battingInfo[player]['innings'] = 1
                    battingInfo[player]['scoresArray'] = [int(tracker[player]['runs'])]
                else:
                    battingInfo[player]['balls'] += tracker[player]['balls']
                    battingInfo[player]['runs'] += tracker[player]['runs']
                    battingInfo[player]['ballLog'] += tracker[player]['ballLog']
                    battingInfo[player]['innings'] += 1
                    battingInfo[player]['scoresArray'].append(int(tracker[player]['runs']))

        for bowl_map in ['innings1Bowltracker', 'innings2Bowltracker']:
            tracker = res[bowl_map]
            for player in tracker:
                if player not in bowlingInfo:
                    bowlingInfo[player] = copy.deepcopy(tracker[player])
                    bowlingInfo[player]['matches'] = 1
                else:
                    bowlingInfo[player]['balls'] += tracker[player]['balls']
                    bowlingInfo[player]['runs'] += tracker[player]['runs']
                    bowlingInfo[player]['ballLog'] += tracker[player]['ballLog']
                    bowlingInfo[player]['wickets'] += tracker[player]['wickets']
                    bowlingInfo[player]['matches'] += 1

        display_points_table()
        display_top_players()

        # Pause after playoff match
        input("Press Enter to continue...")

        return winner, loser

    except Exception as e:
        print(f"Error during {matchtag.upper()}: {str(e)}")
        input("Press Enter to continue or Ctrl+C to exit...")
        return team1, team2  # Default to team1 as winner to continue playoffs

# PLAYOFF SEQUENCE
pointsTabulate = sorted(
    [[team, points[team]['pts'], (points[team]['runsScored'] / points[team]['ballsFaced']) * 6 - (points[team]['runsConceded'] / points[team]['ballsBowled']) * 6]
     for team in points],
    key=lambda x: (x[1], x[2]), reverse=True
)
q1 = [pointsTabulate[0][0], pointsTabulate[1][0]]
elim = [pointsTabulate[2][0], pointsTabulate[3][0]]

finalists = []

winnerQ1, loserQ1 = playoffs(q1[0], q1[1], "Qualifier 1")
finalists.append(winnerQ1)

winnerElim, _ = playoffs(elim[0], elim[1], "Eliminator")

winnerQ2, _ = playoffs(winnerElim, loserQ1, "Qualifier 2")
finalists.append(winnerQ2)

finalWinner, _ = playoffs(finalists[0], finalists[1], "Final")
print(f"\n🏆 {finalWinner.upper()} WINS THE IPL!!!")

# === SAVE FINAL STATS ===
battingTabulate = []
for b in battingInfo:
    c = battingInfo[b]
    outs = sum(1 for bl in c['ballLog'] if "W" in bl)
    avg = round(c['runs'] / outs, 2) if outs else "NA"
    sr = round((c['runs'] / c['balls']) * 100, 2) if c['balls'] else "NA"
    battingTabulate.append([b, c['innings'], c['runs'], avg, max(c['scoresArray']), sr, c['balls']])

battingTabulate = sorted(battingTabulate, key=lambda x: x[2], reverse=True)

bowlingTabulate = []
for b in bowlingInfo:
    c = bowlingInfo[b]
    overs = f"{c['balls'] // 6}.{c['balls'] % 6}" if c['balls'] else "0"
    economy = round((c['runs'] / c['balls']) * 6, 2) if c['balls'] else "NA"
    bowlingTabulate.append([b, c['wickets'], overs, c['runs'], economy])

bowlingTabulate = sorted(bowlingTabulate, key=lambda x: x[1], reverse=True)

with open(os.path.join(dir_path, "batStats.txt"), "w") as f:
    sys.stdout = f
    print(tabulate(battingTabulate, headers=["Player", "Innings", "Runs", "Average", "Highest", "SR", "Balls"], tablefmt="grid"))
    sys.stdout = sys.__stdout__

with open(os.path.join(dir_path, "bowlStats.txt"), "w") as f:
    sys.stdout = f
    print(tabulate(bowlingTabulate, headers=["Player", "Wickets", "Overs", "Runs Conceded", "Economy"], tablefmt="grid"))
    sys.stdout = sys.__stdout__

print("bat", battingf, "bowl", bowlingf)
input("\nPress Enter to exit...")