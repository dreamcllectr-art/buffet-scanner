"""Simple dev server — serves the Buffet project root so the dashboard
can fetch scan_results.csv and individual moat_lane.md files."""
import http.server
import os
import webbrowser
import threading

PORT = 8765
ROOT = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)
    def log_message(self, fmt, *args):
        # Suppress noisy request logs
        if '404' in str(args):
            print(f'  404 {args[1] if len(args) > 1 else ""}')

def open_browser():
    import time; time.sleep(0.5)
    webbrowser.open(f'http://localhost:{PORT}/dashboard/index.html')

threading.Thread(target=open_browser, daemon=True).start()
print(f'\n  Buffett Scanner Dashboard')
print(f'  → http://localhost:{PORT}/dashboard/index.html')
print(f'  Ctrl+C to stop\n')

with http.server.HTTPServer(('', PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n  Server stopped.')
