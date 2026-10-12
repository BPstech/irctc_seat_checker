// api/proxy.js - Vercel Serverless Function Proxy
// Securely proxies API calls to your Python backend without exposing
// the backend URL, IP, or internal CRIS APIs to the user or browser.

module.exports = async function handler(req, res) {
    const customHeader = req.headers['x-backend-url'];
    const backendBase = (customHeader && customHeader.trim()) || process.env.BACKEND_URL;

    if (!backendBase) {
        return res.status(503).json({
            success: false,
            message: "Backend server is not connected. If running from your PC, run Host_Backend_For_Vercel.bat and connect your tunnel, or set BACKEND_URL in Vercel."
        });
    }

    // Clean base URL and construct target endpoint
    const cleanBase = backendBase.replace(/\/+$/, '');
    const targetUrl = `${cleanBase}${req.url}`;

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
            message: `Could not connect to backend server: ${err.message}. Please verify your backend server is online.`
        });
    }
}
