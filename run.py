#!/usr/bin/env python3
"""
Personal Finances - FastAPI Application
Run this file to start the application
"""
import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Personal Finances application...")
    print("📊 Access the app at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("\nPress CTRL+C to stop\n")

    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
