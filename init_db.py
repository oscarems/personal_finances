#!/usr/bin/env python3
"""
Initialize database - wrapper script
Run this from the project root directory
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Now import and run the initialization
from backend.init_db import initialize_database

if __name__ == '__main__':
    print("🔧 Initializing Personal Finances database...")
    initialize_database(create_samples=True)
