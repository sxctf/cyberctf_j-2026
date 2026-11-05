const express = require('express');
const app = express();
app.use(express.json());

const pendingCodes = {};
const codesByLogin = {};
const timers = {};

// Генерация кода по запросу бота (или бэкенда)
app.post('/generate', (req, res) => {
    const { login } = req.body;
    if (!login) {
        return res.status(400).json({ error: 'Missing login' });
    }

    const code = Math.floor(100000 + Math.random() * 900000).toString();

    if (codesByLogin[login]) {
        clearTimeout(timers[login]);
        delete pendingCodes[codesByLogin[login]];
        delete timers[login];
        delete codesByLogin[login];
    }

    const timer = setTimeout(() => {
        delete pendingCodes[codesByLogin[login]];
        delete codesByLogin[login];
        console.log(`[2FA] Code for ${login} expired`);
    }, 60000);

    pendingCodes[code] = login;
    codesByLogin[login] = code;
    timers[login] = timer;
    console.log(`[2FA] Generated code for ${login}: ${code}`);
    res.json({ success: true });
});

// Получение кода (для бота)
app.get('/code', (req, res) => {
    const { login } = req.query;
    if (!login) {
        return res.status(400).json({ error: 'Missing login' });
    }
    if (!codesByLogin[login]) {
        return res.status(404).json({ error: 'No code found or expired' });
    }
    res.json({ code: codesByLogin[login] });
});

// Проверка кода
app.post('/check', (req, res) => {
    const { login, code } = req.body;
    if (!login) {
        return res.status(400).json({ error: 'Missing login' });
    }
    if (!code) {
        return res.status(400).json({ error: 'Missing code' });
    }
    if (pendingCodes[code]) {
        return res.status(200).json({ success: true });
    }
    return res.status(403).json({ success: false });
});

const PORT = 3001;
app.listen(PORT, () => {
    console.log(`2FA Service listening on port ${PORT}`);
});
