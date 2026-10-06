# הרצה: python song.py
# אחר כך בדפדפן: http://localhost:8000/?song=קישור-יוטיוב
# אפשר לשנות מהירות: ...&speed=1.3
import base64, hmac, os, re, subprocess, sys, tempfile, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(tempfile.gettempdir()) / "song_audio"
OUT.mkdir(exist_ok=True)
PASSWORD = os.environ.get("APP_PASSWORD", "")


class H(BaseHTTPRequestHandler):
    def send_text(self, body, ctype="text/html; charset=utf-8", code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        if not PASSWORD:
            return True
        h = self.headers.get("Authorization", "")
        try:
            pw = base64.b64decode(h[6:]).decode().split(":", 1)[1]
        except Exception:
            return False
        return h.startswith("Basic ") and hmac.compare_digest(pw, PASSWORD)

    def do_GET(self):
        if not self.authed():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="song"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/f/"):
            return self.serve_file(OUT / Path(urllib.parse.unquote(u.path[3:])).name)
        raw = urllib.parse.unquote(u.query)
        m = re.search(r"(?:[?&]v=|youtu\.be/|shorts/|embed/|live/|song=)([\w-]{11})(?:[&#?]|$)", raw)
        if not m:
            return self.send_text("הוסף ?song= וקישור יוטיוב", code=400)
        try:
            speed = float(urllib.parse.parse_qs(u.query).get("speed", ["1.2"])[0])
        except ValueError:
            speed = 1.2
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--no-playlist",
             "-f", "bestaudio[ext=m4a]/bestaudio",
             "-o", str(OUT / "%(id)s.%(ext)s"), "--print", "after_move:filepath",
             "https://www.youtube.com/watch?v=" + m.group(1)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return self.send_text("שגיאה:\n" + r.stderr[-500:], "text/plain; charset=utf-8", 500)
        name = urllib.parse.quote(Path(r.stdout.strip().splitlines()[-1]).name)
        self.send_text(
            f'<!doctype html><meta charset="utf-8"><body style="margin:0">'
            f'<audio id="a" controls autoplay src="/f/{name}" style="width:100%"></audio>'
            f'<script>const a=document.getElementById("a");'
            f'function s(){{a.preservesPitch=false;a.playbackRate={speed}}}'
            f's();a.onloadedmetadata=s;a.onplay=s;</script>'
        )

    def serve_file(self, f):
        if not f.is_file():
            return self.send_text("not found", "text/plain", 404)
        size = f.stat().st_size
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if m:
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", "audio/mp4" if f.suffix == ".m4a" else "audio/webm")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with f.open("rb") as fh:
                fh.seek(start)
                self.wfile.write(fh.read(end - start + 1))
        except (BrokenPipeError, ConnectionResetError):
            pass


port = int(os.environ.get("PORT", "8000"))
print("running on port", port)
ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
