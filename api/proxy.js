// api/proxy.js - Vercel Serverless Function Proxy
// Securely and automatically proxies API calls to your Python backend
// without exposing your local PC IP, tunnel URL, or CRIS endpoints to users.

const GIST_RAW_URL = 'https://gist.githubusercontent.com/BPstech/1d0e0e40f7dd33220e1030f45c2baddf/raw/backend_url.txt';
const GIST_API_URL = 'https://api.github.com/gists/1d0e0e40f7dd33220e1030f45c2baddf';

let cachedBackendUrl = null;
let lastCacheTime = 0;

async function checkBackendAlive(url, timeoutMs = 2000) {
    if (!url || typeof url !== 'string' || !url.startsWith('http')) return false;
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        const resp = await fetch(`${url.replace(/\/+$/, '')}/health`, {
            signal: controller.signal,
            headers: { 'Accept': 'application/json' }
        });
        clearTimeout(timeoutId);
        return resp.ok;
    } catch {
        return false;
    }
}

async function fetchUrlFromGist() {
    // 1. Try fast unauthenticated raw Gist URL (immune to GitHub 60 req/hr API rate limits)
    try {
        const rawResp = await fetch(`${GIST_RAW_URL}?_nocache=${Date.now()}`, {
            headers: { 'User-Agent': 'IRCTC-Seat-Checker-Proxy' },
            cache: 'no-store'
        });
        if (rawResp.ok) {
            const text = (await rawResp.text()).trim();
            if (text && text.startsWith('http')) {
                return text;
            }
        }
    } catch (e) {
        console.error('Raw gist fetch error:', e.message);
    }

    // 2. Fallback to GitHub REST API endpoint
    try {
        const apiResp = await fetch(GIST_API_URL, {
            headers: {
                'User-Agent': 'IRCTC-Seat-Checker-Proxy',
                'Accept': 'application/vnd.github.v3+json'
            }
        });
        if (apiResp.ok) {
            const data = await apiResp.json();
            const content = data.files?.['backend_url.txt']?.content?.trim();
            if (content && content.startsWith('http')) {
                return content;
            }
        }
    } catch (e) {
        console.error('GitHub API gist fetch error:', e.message);
    }

    return null;
}

async function resolveBackendUrl() {
    const isLocal = !process.env.VERCEL || process.env.VERCEL_ENV === 'development';

    // 1. If running locally (vercel dev), prioritize local Flask backend on port 5000 if active
    if (isLocal) {
        const localUrl = 'http://127.0.0.1:5000';
        if (await checkBackendAlive(localUrl, 1000)) {
            return localUrl;
        }
    }

    const now = Date.now();
    // 2. Return cached live tunnel if younger than 20s
    if (cachedBackendUrl && (now - lastCacheTime < 20000)) {
        return cachedBackendUrl;
    }

    // 3. Resolve active live PC tunnel from Cloud Coordinator (GitHub Gist)
    const gistUrl = await fetchUrlFromGist();
    if (gistUrl) {
        cachedBackendUrl = gistUrl;
        lastCacheTime = now;
        return gistUrl;
    }

    // 4. Fallback to BACKEND_URL environment variable if set in Vercel
    if (process.env.BACKEND_URL && process.env.BACKEND_URL.trim()) {
        const envUrl = process.env.BACKEND_URL.trim();
        cachedBackendUrl = envUrl;
        lastCacheTime = now;
        return envUrl;
    }

    // 5. Fallback to local PC backend
    if (await checkBackendAlive('http://127.0.0.1:5000', 1000)) {
        return 'http://127.0.0.1:5000';
    }

    return cachedBackendUrl;
}

function getOriginalPath(req) {
    const fwdUri = req.headers['x-forwarded-uri'] || req.headers['x-matched-path'];
    if (fwdUri && fwdUri.startsWith('/api') && !fwdUri.startsWith('/api/proxy')) {
        return fwdUri;
    }

    try {
        const fullUrl = new URL(req.url || '/', 'http://localhost');
        let subPath = '';
        if (req.query && (req.query.path || req.query.match)) {
            const p = req.query.path || req.query.match;
            subPath = Array.isArray(p) ? p.join('/') : p;
        } else if (fullUrl.searchParams.has('match')) {
            subPath = fullUrl.searchParams.get('match');
        } else if (fullUrl.searchParams.has('path')) {
            subPath = fullUrl.searchParams.get('path');
        }

        fullUrl.searchParams.delete('match');
        fullUrl.searchParams.delete('path');

        const qs = fullUrl.searchParams.toString();
        const baseRoute = subPath ? `/api/${subPath.replace(/^\/+/, '')}` : fullUrl.pathname;
        return `${baseRoute}${qs ? '?' + qs : ''}`;
    } catch {
        return req.url;
    }
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

    res.setHeader('x-resolved-backend', cleanBase);

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
            // Guard against Cloudflare or backend returning HTML error page
            if (text.includes('<!DOCTYPE') || text.includes('<html') || text.includes('<HTML')) {
                return res.status(backendResponse.status >= 400 ? backendResponse.status : 502).json({
                    success: false,
                    message: `Backend returned an HTML error (HTTP ${backendResponse.status}). Please check your PC backend console.`
                });
            }
            return res.send(text);
        }
    } catch (err) {
        return res.status(502).json({
            success: false,
            message: `Could not connect to backend server (${cleanBase}): ${err.message}. Please verify your PC backend is running.`
        });
    }
};
