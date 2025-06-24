import http.server
import socketserver
import threading
import webbrowser
import os
import sys
from pathlib import Path

try:
    from livereload import Server
except ImportError:
    print("The 'livereload' package is required. Install it with: pip install livereload")
    sys.exit(1)

PORT = 8000
# BUILD_DIR = Path(__file__).parent / "docs"
BUILD_DIR = Path(__file__).parent / "serve_me"

if not BUILD_DIR.exists():
    print(f"Build directory '{BUILD_DIR}' does not exist. Run the build first.")
    sys.exit(1)

os.chdir(BUILD_DIR)

server = Server()
server.watch(str(BUILD_DIR / '**' / '*.*'), delay=0.5)

print(f"Serving '{BUILD_DIR}' at http://localhost:{PORT}/aec-foi-static/ with live reload...")
webbrowser.open(f"http://localhost:{PORT}/aec-foi-static/")
server.serve(root=str(BUILD_DIR), port=PORT, open_url_delay=None)
