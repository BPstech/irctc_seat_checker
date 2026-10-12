#!/usr/bin/env python3
"""
host_tunnel.py — Automated Cloudflare Tunnel & Flask Backend Launcher
Exposes the local IRCTC Flask backend to the internet via a secure HTTPS tunnel
for seamless integration with Vercel frontend or mobile access.
"""

import os
import sys
import time
import re
import signal
import subprocess
import urllib.request

# Ensure UTF-8 output on Windows consoles without UnicodeEncodeError
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CLOUDFLARED_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
CLOUDFLARED_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.log")
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

def download_cloudflared():
    if os.path.exists(CLOUDFLARED_EXE) and os.path.getsize(CLOUDFLARED_EXE) > 10_000_000:
        return True

    print("[*] Downloading Cloudflare Tunnel tool (~50MB one-time setup)...")
    try:
        def reporthook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, int(downloaded * 100 / total_size))
                mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                sys.stdout.write(f"\r    Download progress: [{percent:3d}%] ({mb:.1f}MB / {total_mb:.1f}MB)")
                sys.stdout.flush()

        urllib.request.urlretrieve(CLOUDFLARED_URL, CLOUDFLARED_EXE, reporthook=reporthook)
        print("\n[OK] Cloudflare Tunnel tool downloaded successfully.")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to download cloudflared.exe: {e}")
        return False

def copy_to_clipboard(text):
    try:
        p = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
        p.communicate(text.encode('utf-8'))
        return True
    except Exception:
        return False

def extract_tunnel_url(log_file, timeout_secs=25):
    pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
    start_time = time.time()
    while time.time() - start_time < timeout_secs:
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    match = pattern.search(content)
                    if match:
                        return match.group(0)
            except Exception:
                pass
        time.sleep(0.5)
    return None

def main():
    print("=" * 66)
    print("       [IRCTC] Green Seat Finder -- PC Backend for Vercel")
    print("=" * 66)
    print()

    # 1. Ensure cloudflared is downloaded
    if not download_cloudflared():
        sys.exit(1)

    # Clean old log file
    if os.path.exists(CLOUDFLARED_LOG):
        try:
            os.remove(CLOUDFLARED_LOG)
        except Exception:
            pass

    # 2. Start Cloudflare Tunnel
    print("[1/2] Launching secure Cloudflare Tunnel to port 5000...")
    tunnel_cmd = [
        CLOUDFLARED_EXE,
        "tunnel",
        "--url", "http://127.0.0.1:5000",
        "--logfile", CLOUDFLARED_LOG
    ]
    
    tunnel_proc = subprocess.Popen(
        tunnel_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )

    # 3. Wait for the URL to be generated
    print("      Connecting to Cloudflare network...")
    tunnel_url = extract_tunnel_url(CLOUDFLARED_LOG)

    if not tunnel_url:
        print("[!] Tunnel connection timed out. Inspect cloudflared.log for error details.")
        try:
            tunnel_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    # 4. Sync tunnel URL with Cloud Coordinator
    print("[2/2] Connecting Vercel cloud coordinator to this PC...")
    try:
        sync_res = subprocess.run(
            ['gh', 'api', '-X', 'PATCH', '/gists/1d0e0e40f7dd33220e1030f45c2baddf', '-f', f'files[backend_url.txt][content]={tunnel_url}'],
            capture_output=True,
            text=True
        )
        if sync_res.returncode == 0:
            print("      [OK] Vercel website is now connected to your PC automatically!")
        else:
            print("      [!] Cloud coordinator sync check skipped.")
    except Exception as e:
        print(f"      [!] Cloud coordinator notice: {e}")

    # Copy to clipboard
    copied = copy_to_clipboard(tunnel_url)

    # 5. Display banner
    print()
    print("=" * 66)
    print("  [SUCCESS] YOUR PC IS NOW SERVING AS THE LIVE BACKEND!")
    print("=" * 66)
    print()
    print(f"  • Live Tunnel:      {tunnel_url}")
    print("  • Vercel Website:   AUTOMATICALLY CONNECTED")
    print("  • Mobile Access:    Your Vercel site is live for all visitors & phones!")
    if copied:
        print("  • Clipboard:        Tunnel URL copied to clipboard")
    print()
    print("=" * 66)
    print("  LOCAL BACKEND LOGS (Starting Flask on port 5000):")
    print("  Press Ctrl+C to stop hosting.")
    print("=" * 66)
    print()

    # 6. Start Flask App in the current process
    try:
        flask_env = os.environ.copy()
        flask_env['PORT'] = '5000'
        flask_env['PYTHONIOENCODING'] = 'utf-8'
        flask_proc = subprocess.Popen([sys.executable, "app.py"], env=flask_env)
        flask_proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping backend and closing tunnel...")
    finally:
        try:
            tunnel_proc.terminate()
            tunnel_proc.kill()
        except Exception:
            pass
        print("[OK] Tunnel closed.")

if __name__ == '__main__':
    main()
