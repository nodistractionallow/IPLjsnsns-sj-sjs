import os

def get_file_extension_from_path(path: str) -> str:
    """
    Extracts the file extension from a given file path.

    Args:
        path (str): The path to the file.

    Returns:
        str: The file extension (e.g., "txt", "jpg", "pdf") or an empty string if no extension is found.
    """
    if not isinstance(path, str):
        raise TypeError("Input path must be a string.")

    filename = os.path.basename(path)

    # Find the last occurrence of '.'
    last_dot_index = filename.rfind('.')

    # If no dot, or if the dot is the first character (e.g., ".bashrc"),
    # or if it's the last character (e.g., "archive.tar."), there's no valid extension.
    if filename.startswith('.') and '.' not in filename[1:]: # Handles cases like ".bashrc"
         return filename[1:]

    if last_dot_index == -1 or last_dot_index == len(filename) - 1: # Handles "file" or "file."
        return ""

    # Standard case: "file.txt" -> "txt"
    extension = filename[last_dot_index + 1:]
    return extension

def get_player_out_description(ball_log, bowling_team_players_json=None):
    """
    Determines how a player got out based on their ballLog.
    Returns "Not out", "DNB", or the dismissal string.
    """
    if not ball_log:  # No balls faced, could be DNB or Not Out if innings ended
        return "DNB" # Default to DNB if no ballLog, app.py will refine

    out_info_str = ""
    for entry in ball_log:
        if "W:" in entry:
            out_info_str = entry
            break

    if not out_info_str:
        return "Not out"

    # Parsing logic from your original app.py, slightly adapted
    # Assuming the format is like "W:CaughtBy-Fielder-Bowler-BowlerName" or "W:run out"
    parts = out_info_str.split(':')[-1].split('-')

    dismissal_type = parts[0].lower()

    if dismissal_type == "caughtby":
        fielder = parts[1] if len(parts) > 1 else "fielder"
        bowler = parts[3] if len(parts) > 3 and parts[2].lower() == "bowler" else "unknown"
        return f"c {fielder} b {bowler}"
    elif dismissal_type == "runout" or dismissal_type == "run out":
        return "Run out"
    elif dismissal_type in ["bowled", "lbw", "stumped", "hitwicket"]:
        bowler = parts[2] if len(parts) > 2 and parts[1].lower() == "bowler" else "unknown"
        return f"{dismissal_type} b {bowler}"
    else: # Fallback for other W:type formats
        return f"Wicket ({dismissal_type})"


def count_wickets_from_ball_log(ball_log_list):
    """Counts wickets from a list of ball_log entries for a team."""
    wickets = 0
    for entry in ball_log_list:
        if "W:" in entry:
            wickets += 1
    return wickets
