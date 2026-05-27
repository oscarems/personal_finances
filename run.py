#!/usr/bin/env python3
"""
Personal Finances - FastAPI Application
Run this file to start the application
"""
from pathlib import Path
import subprocess
import sys

import uvicorn

def _free_port(port: int) -> None:
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True, text=True
    )
    pids = result.stdout.strip().split()
    if pids:
        subprocess.run(["kill", "-9"] + pids, check=False)
        print(f"Killed existing process(es) on port {port}: {', '.join(pids)}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))

    _free_port(8000)
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
