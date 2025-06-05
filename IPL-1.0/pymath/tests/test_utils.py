import unittest
from pymath.lib.utils import get_file_extension_from_path

class TestGetFileExtension(unittest.TestCase):
    def test_get_file_extension_from_path_with_extension(self):
        """Test with a file that has an extension."""
        self.assertEqual(get_file_extension_from_path("file.txt"), "txt")

    def test_get_file_extension_from_path_without_extension(self):
        """Test with a file that does not have an extension."""
        self.assertEqual(get_file_extension_from_path("file"), "")

    def test_get_file_extension_from_path_with_multiple_dots(self):
        """Test with a file that has multiple dots in the name."""
        self.assertEqual(get_file_extension_from_path("archive.tar.gz"), "gz")

    def test_get_file_extension_from_path_with_leading_dot(self):
        """Test with a hidden file (starts with a dot)."""
        self.assertEqual(get_file_extension_from_path(".bashrc"), "bashrc")

    def test_get_file_extension_from_path_empty_string(self):
        """Test with an empty string."""
        self.assertEqual(get_file_extension_from_path(""), "")

    def test_get_file_extension_from_path_only_dot(self):
        """Test with a path that is just a dot."""
        self.assertEqual(get_file_extension_from_path("."), "")

    def test_get_file_extension_from_path_with_path_components(self):
        """Test with a path that includes directory components."""
        self.assertEqual(get_file_extension_from_path("/path/to/file.jpeg"), "jpeg")

    def test_get_file_extension_from_path_with_no_extension_and_path(self):
        """Test with a path that includes directory components but no file extension."""
        self.assertEqual(get_file_extension_from_path("/path/to/file"), "")

if __name__ == '__main__':
    unittest.main()
