#!/usr/bin/env python3
"""
Initialize database - wrapper script
Run this from the project root directory
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Now import and run the initialization
from finance_app.init_db import initialize_database

if __name__ == '__main__':
    print("🔧 Initializing Personal Finances database...")
    initialize_database(create_samples=True)
