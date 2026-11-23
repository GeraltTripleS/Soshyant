"""Startup must delegate before loading dependencies from a system Python."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
from expert.config import ROOT


class StartupTests(unittest.TestCase):
    def test_foreign_python_delegates_with_paths_and_arguments_intact(self):
        foreign = str(ROOT / 'unrelated-python/python.exe')
        with patch.object(sys, 'executable', foreign), patch.object(sys, 'argv', ['start.py', '--port', '8099']), \
                patch('subprocess.call', return_value=7) as launch:
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ROOT / 'start.py'), run_name='__main__')
        self.assertEqual(result.exception.code, 7)
        launch.assert_called_once_with([str(ROOT / 'runtime/python.exe'), str(ROOT / 'start.py'), '--port', '8099'])
