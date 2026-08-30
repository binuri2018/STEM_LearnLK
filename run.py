"""
Entry point to run the entire AI STEM Ecosystem application (Backend + Frontend).

Usage:
  python run.py
Or:
  uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""
import uvicorn

if __name__ == "__main__":
    print("Starting AI STEM Ecosystem on http://127.0.0.1:8000 ...")
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
