#!/usr/bin/env python3
"""
Personal Finances - FastAPI Application
Run this file to start the application
"""
from pathlib import Path
import sys

import uvicorn

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))

    print("🚀 Starting Personal Finances application...")
    print("📊 Access the app at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("\nPress CTRL+C to stop\n")

    uvicorn.run(
        "finance_app.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
