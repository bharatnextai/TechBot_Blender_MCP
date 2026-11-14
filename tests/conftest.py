import sys
import unittest
from pathlib import Path

# Polyfill enterContext on unittest.TestCase for Python < 3.11
if not hasattr(unittest.TestCase, "enterContext"):
    def enterContext(self, cm):
        val = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return val
    unittest.TestCase.enterContext = enterContext

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

