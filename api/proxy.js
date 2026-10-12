// api/proxy.js - Vercel Serverless Function Proxy
// Securely and automatically proxies API calls to your Python backend
// without exposing your local PC IP, tunnel URL, or CRIS endpoints to users.

let cachedBackendUrl = process.env.BACKEND_URL || null;
let lastCacheTime = 0;

async function resolveBackendUrl() {
    // 1. If BACKEND_URL environment variable is explicitly set in Vercel, prioritize it
    if (process.env.BACKEND_URL && process.env.BACKEND_URL.trim()) {
        return process.env.BACKEND_URL.trim();
    }

    // 2. Return cached tunnel URL if younger than 20 seconds
    const now = Date.now();
    if (cachedBackendUrl && (now - lastCacheTime < 20000)) {
        return cachedBackendUrl;
    }

    // 3. Auto-resolve the active live PC tunnel URL from the cloud coordinator
    try {
        const resp = await fetch('https://api.github.com/gists/1d0e0e40f7dd33220e1030f45c2baddf', {
            headers: {
                'User-Agent': 'IRCTC-Seat-Checker-Proxy',
                'Accept': 'application/vnd.github.v3+json'
            }
        });
        if (resp.ok) {
            const data = await resp.json();
            const content = data.files?.['backend_url.txt']?.content?.trim();
            if (content && content.startsWith('http')) {
                cachedBackendUrl = content;
                lastCacheTime = now;
                return cachedBackendUrl;
            }
        }
    } catch (e) {
        console.error('Failed to auto-resolve backend URL:', e.message);
    }

    return cachedBackendUrl;
}

function getOriginalPath(req) {
    const fwdUri = req.headers['x-forwarded-uri'] || req.headers['x-matched-path'];
    if (fwdUri && fwdUri.startsWith('/api') && !fwdUri.startsWith('/api/proxy')) {
        return fwdUri;
    }
    if (req.url && req.url.startsWith('/api') && !req.url.startsWith('/api/proxy')) {
        return req.url;
    }
    if (req.query && (req.query.path || req.query.match)) {
        const p = req.query.path || req.query.match;
        const subPath = Array.isArray(p) ? p.join('/') : p;
        const urlObj = new URL(req.url, 'http://localhost');
        urlObj.searchParams.delete('path');
        urlObj.searchParams.delete('match');
        const qs = urlObj.searchParams.toString();
        return `/api/${subPath}${qs ? '?' + qs : ''}`;
    }
    return req.url;
}

module.exports = async function handler(req, res) {
    const customHeader = req.headers['x-backend-url'];
    const backendBase = (customHeader && customHeader.trim()) || await resolveBackendUrl();

    if (!backendBase) {
        return res.status(503).json({
            success: false,
            message: "Backend server is currently offline. Please ensure Host_Backend_For_Vercel.bat is running on your server PC."
        });
    }

    // Clean base URL and construct target endpoint
    const cleanBase = backendBase.replace(/\/+$/, '');
    const apiPath = getOriginalPath(req);
    const targetUrl = `${cleanBase}${apiPath}`;

    try {
        const fetchOptions = {
            method: req.method,
            headers: {
                'accept': 'application/json',
                'content-type': req.headers['content-type'] || 'application/json'
            }
        };

        // Forward payload body for POST/PUT requests
        if (req.method !== 'GET' && req.method !== 'HEAD' && req.body) {
            fetchOptions.body = typeof req.body === 'object' ? JSON.stringify(req.body) : req.body;
        }

        const backendResponse = await fetch(targetUrl, fetchOptions);
        const contentType = backendResponse.headers.get('content-type') || '';

        res.status(backendResponse.status);

        if (contentType.includes('application/json')) {
            const data = await backendResponse.json();
            return res.json(data);
        } else {
            const text = await backendResponse.text();
            return res.send(text);
        }
    } catch (err) {
        return res.status(502).json({
            success: false,
            message: `Could not connect to backend server: ${err.message}. Please verify your PC backend is running.`
        });
    }
};
