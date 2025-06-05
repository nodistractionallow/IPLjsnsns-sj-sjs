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

    parts = path.split('.')
    if len(parts) > 1:
        return parts[-1]
    return ""
