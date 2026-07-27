"""Pytest bootstrap: put the backend dir on sys.path so `import app.*` works
whether pytest is run from the repo root or the backend/ directory."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
