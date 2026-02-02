import os
import subprocess
import sys
import webbrowser
import time
from threading import Timer
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
    print(f"✓ Loaded environment variables from .env")
except ImportError:
    print("⚠️  python-dotenv not installed. Run: pip3 install python-dotenv")
except Exception as e:
    print(f"⚠️  Could not load .env file: {e}")

def open_browser():
    """Wait 1.5s then open browser"""
    time.sleep(1.5)
    print("🌍 Opening Dashboard at http://localhost:8000")
    webbrowser.open("http://localhost:8000")

def main():
    # Get the project root
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, 'backend')
    
    print(f"🚀 Starting Rational Equity from {backend_dir}...")
    print("---------------------------------------------------")
    
    # Change to backend dir so local imports (market_data, etc.) work correctly
    os.chdir(backend_dir)
    
    # Schedule browser open
    Timer(1.5, open_browser).start()
    
    # Kill existing process on port 8000
    try:
        # Mac/Linux
        os.system("lsof -ti:8000 | xargs kill -9 2>/dev/null")
    except:
        pass
        
    # Run uvicorn
    # using sys.executable ensures we use the active python environment
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
