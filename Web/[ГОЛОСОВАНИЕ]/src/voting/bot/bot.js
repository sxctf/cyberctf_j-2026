const express = require('express');
const puppeteer = require('puppeteer');

const app = express();
app.use(express.json());

const FLAG = process.env.FLAG || 'CyberCTF{THIS_IS_FAKE_FLAG}';
const visitQueue = [];
let visitBusy = false;
let browser;

async function initBrowser() {
    browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
}

function isAllowedUrl(url) {
    const allowed = ['web:5000', 'localhost:5000', '127.0.0.1:5000'];
    for (let host of allowed) {
        if (url.startsWith(`http://${host}/`) || url === `http://${host}`) {
            return true;
        }
    }
    return false;
}

async function visitOnce(url) {
    let page;
    try {
        page = await browser.newPage();
        await page.setCookie({
            name: 'flag',
            value: FLAG,
            domain: 'web',
            path: '/',
            httpOnly: false,
            secure: false
        });
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 5000 });
        await new Promise(resolve => setTimeout(resolve, 3000));
        console.log(url);
    } catch (err) {
        console.error(err);
    } finally {
        if (page && !page.isClosed()) {
            await page.close();
        }
    }
}

async function processQueue() {
    if (visitBusy) return;
    visitBusy = true;
    while (visitQueue.length) {
        const url = visitQueue.shift();
        await visitOnce(url);
    }
    visitBusy = false;
}

app.post('/visit', (req, res) => {
    const { url } = req.body;
    if (!url) return res.status(400).send('Missing url');
    if (!isAllowedUrl(url)) return res.status(400).send('Invalid URL');
    if (!browser) return res.status(503).send('Bot is starting');

    visitQueue.push(url);
    res.send('Queued');
    processQueue();
});

app.listen(3000, () => {
    console.log('Bot listening on port 3000');
    initBrowser();
});
