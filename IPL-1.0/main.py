import os
from pymath.lib.utils import get_file_extension_from_path

if __name__ == "__main__":
    file_path = "example.txt"
    extension = get_file_extension_from_path(file_path)
    print(f"Hello, World! The file extension is: {extension}")
