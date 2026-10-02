# 🚂 IRCTC Green Seat Finder & Split Journey Planner

Smart split-journey booking assistant and live seat vacancy tracker powered by direct CRIS/IRCTC online charts integration.

---

## 🚀 Architecture & Deployment

This project uses a **hybrid architecture** designed for fast, seamless deployment on **Vercel** while keeping the backend completely hidden from users:

1. **Frontend (Vercel)**:
   - `index.html`: Responsive UI with multi-passenger options, same-coach preferences, dynamic train class detection, and real-time audio/visual alerts.
   - `vercel.json`: Handles URL routing and rewrites `/api/*` to the serverless proxy.
   - `api/proxy.js`: Vercel Serverless Function that forwards API calls to your Python backend using the private `BACKEND_URL` environment variable.

2. **Backend (Python / Flask / Selenium)**:
   - `app.py`: High-performance Flask REST API.
   - `irctc_api.py`: Automation engine that interfaces directly with official CRIS internal endpoints with authenticated headless browser sessions.
   - Runs locally or on a cloud host (Render, Railway, VPS).

---

## 🔒 How the Backend Stays Hidden From Users

- **Zero Exposure in DevTools**: Visitors visiting `https://your-app.vercel.app` only see network requests to `/api/train-info`, `/api/find-seats`, `/api/live-poll` on the **same Vercel domain**. They never see your backend's IP, port, server host, or internal CRIS endpoints.
- **Hidden Secret in Vercel**: Your real backend URL is stored securely in Vercel's **Environment Variables** (`BACKEND_URL`). It is never committed to GitHub or exposed in frontend JavaScript.
- **No CORS Issues**: Since all requests go to your own Vercel domain, there are zero cross-origin (CORS) errors.
- **Private GitHub Option**: In `GitHub_Quick_Push.bat`, choosing **Private** ensures your GitHub repository is visible only to you, while Vercel can still deploy it automatically.

---

## 🛠️ Step-by-Step Deployment Instructions

### Step 1: Upload to GitHub via BAT File
1. Double-click `GitHub_Quick_Push.bat` in this folder.
2. Select **[2] Create a NEW GitHub repository and push this directory**.
3. Enter your repository name (e.g. `irctc-seat-finder`).
4. Choose visibility:
   - Select **[2] Private** if you want your repository completely hidden from public GitHub viewers.
   - Or select **[1] Public** if you want a public repository (your backend URL remains protected via Vercel environment variables regardless).
5. The batch file will automatically initialize Git, commit all files, and push to GitHub.

---

### Step 2: Deploy Frontend on Vercel
1. Log in to [Vercel](https://vercel.com) and click **"Add New..."** > **"Project"**.
2. Select your newly created GitHub repository.
3. In **Project Settings**:
   - Framework Preset: **Other**
   - Root Directory: `./` (default)
4. Click **Deploy**. Vercel will deploy your site in seconds!

---

### Step 3: Connect Your Backend
Since the backend uses headless Chrome to bypass IRCTC's bot detection, run your backend using either of these two methods:

#### Option A: Run Backend on Your PC (Free Cloudflare Tunnel)
1. Start your backend locally with `run_irctc_finder.bat`.
2. Expose it via a free tunnel:
   - Using Cloudflare Tunnel:
     ```bash
     cloudflared tunnel --url http://localhost:5000
     ```
   - Or using ngrok:
     ```bash
     ngrok http 5000
     ```
3. Copy the generated HTTPS URL (e.g. `https://xyz-abc.trycloudflare.com`).
4. In Vercel:
   - Go to your project > **Settings** > **Environment Variables**.
   - Add variable name: `BACKEND_URL`
   - Value: `https://xyz-abc.trycloudflare.com` (your tunnel URL without trailing slash).
   - Save and redeploy.

#### Option B: Deploy Backend to Cloud (Render / Railway / VPS)
1. Deploy `app.py` to Render, Railway, or any Linux VPS with Google Chrome installed.
2. Copy your backend service URL (e.g. `https://my-irctc-backend.onrender.com`).
3. Set `BACKEND_URL` in your Vercel project environment variables.

---

## 💻 Running 100% Locally
To run everything offline or on your local machine:
1. Double-click `run_irctc_finder.bat`.
2. Open your browser and navigate to: `http://localhost:5000`.
