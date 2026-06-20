import uvicorn
import subprocess
import sys

# Install dependencies if needed
try:
    import fastapi
    import sqlalchemy
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

if __name__ == "__main__":
    print("\n=== CONCEPT CHECK TOOL ===")
    print("Starting API server on http://localhost:8000")
    print("Magic links will print to console (simulated email)\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)