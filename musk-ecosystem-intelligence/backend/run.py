"""
Start the Musk Ecosystem Intelligence app.
Just run:  python run.py
"""

import uvicorn

if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   Musk Ecosystem Intelligence v1.0       ║")
    print("  ║                                          ║")
    print("  ║   Open your browser to:                  ║")
    print("  ║   http://localhost:8000                   ║")
    print("  ║                                          ║")
    print("  ║   Press Ctrl+C to stop the server        ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
