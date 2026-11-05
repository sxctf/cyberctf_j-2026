const puppeteer = require('puppeteer');
const http = require('http');
const url = require('url');
const fs = require('fs');

const BACKEND_URL = process.env.BACKEND_URL || 'http://backend:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://frontend:8080';
const TWOFA_SERVICE_URL = process.env.TWOFA_SERVICE_URL || 'http://2fa-service:3001';
const LISTEN_PORT = process.env.LISTEN_PORT || 8080;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function loadAdminPassword() {
    if (process.env.ADMIN_PASSWORD && process.env.ADMIN_PASSWORD.trim()) {
        return process.env.ADMIN_PASSWORD.trim();
    }

    const file = process.env.ADMIN_PASSWORD_FILE;
    if (!file) {
        throw new Error('ADMIN_PASSWORD or ADMIN_PASSWORD_FILE is required');
    }

    for (let attempt = 0; attempt < 50; attempt++) {
        try {
            const value = fs.readFileSync(file, 'utf8').trim();
            if (value) return value;
        } catch (err) {
            if (err.code !== 'ENOENT') throw err;
        }
        await sleep(200);
    }

    throw new Error('Timed out waiting for admin password');
}

let browserInstance = null;

async function getBrowser() {
    if (!browserInstance) {
        browserInstance = await puppeteer.launch({
            headless: true,
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || '/usr/bin/chromium-browser',
            args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
            protocolTimeout: 60000
        });
    }
    return browserInstance;
}

async function visitUrl(targetUrl, password) {
    console.log(`[Bot] Visiting ${targetUrl}`);
    const browser = await getBrowser();
    const page = await browser.newPage();

    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'networkidle2' });
    await page.waitForSelector('input[placeholder="Логин"]', { timeout: 15000 });
    await page.type('input[placeholder="Логин"]', 'admin');
    await page.type('input[placeholder="Пароль"]', password);
    await page.click('#login-btn');

    const twoFaInput = await page.waitForSelector('input[placeholder="Код 2FA"]', { timeout: 8000 }).catch(() => null);
    if (twoFaInput) {
        console.log(`on 2FA`);
        const codeRes = await fetch(`${TWOFA_SERVICE_URL}/code?login=${encodeURIComponent('admin')}`);
        const codeData = await codeRes.json();
        if (codeData.code) {
            console.log(`Got code: ${codeData.code}`);
            await twoFaInput.type(codeData.code);
            await page.click('#check-btn');
            await new Promise(r => setTimeout(r, 2000));
        }
    }

    console.log(`Go to ${targetUrl}`);

    await page.goto(targetUrl, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 5000));
    await page.close();
    console.log(`[Bot] Done visiting ${targetUrl}`);
}

async function main() {
    const password = await loadAdminPassword();

    const server = http.createServer(async (req, res) => {
        const parsedUrl = url.parse(req.url, true);
        if (req.method === 'POST' && parsedUrl.pathname === '/visit') {
            let body = '';
            req.on('data', chunk => body += chunk);
            req.on('end', async () => {
                let targetUrl;
                try {
                    const json = JSON.parse(body);
                    targetUrl = json.url;
                } catch(e) {
                    res.writeHead(400);
                    res.end('Bad request');
                    return;
                }
                if (!targetUrl) {
                    res.writeHead(400);
                    res.end('Missing url');
                    return;
                }
                // Запускаем посещение в фоне, ответ даём сразу
                visitUrl(targetUrl, password).catch(err => console.error('Visit error:', err));
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'visiting' }));
            });
        } else {
            res.writeHead(404);
            res.end('Not found');
        }
    });

    server.listen(LISTEN_PORT, () => {
        console.log(`Bot HTTP server listening on port ${LISTEN_PORT}`);
        console.log(`Send POST /visit with {"url": "http://..."} to trigger`);
    });

    process.on('SIGINT', async () => {
        if (browserInstance) await browserInstance.close();
        process.exit();
    });
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});