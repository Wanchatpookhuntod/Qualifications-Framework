import os
import sys

# Ensure SECRET_KEY is set before importing app, so the resolver does not warn or fail.
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Make project root importable when pytest is run from any directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
