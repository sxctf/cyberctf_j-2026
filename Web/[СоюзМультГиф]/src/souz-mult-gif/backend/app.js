const express = require('express');
const cookieParser = require('cookie-parser');
const cors = require('cors');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'
const TWOFA_SERVICE_URL = process.env.TWOFA_SERVICE_URL || 'http://2fa-service:3001'
const FLAG = process.env.FLAG || 'flag{THIS_IS_FAKE_FLAG}'

const app = express();
app.use(express.json({ limit: '10mb' }));
app.use(cookieParser());
app.use(cors({ origin: BASE_URL, credentials: true }));

const users = {};
const sessions = {};
let nextUserId = 1;

function resolveAdminPassword() {
  if (process.env.ADMIN_PASSWORD && process.env.ADMIN_PASSWORD.trim()) {
    return process.env.ADMIN_PASSWORD.trim();
  }

  const file = process.env.ADMIN_PASSWORD_FILE;
  if (file) {
    try {
      const existing = fs.readFileSync(file, 'utf8').trim();
      if (existing) return existing;
    } catch (err) {
      if (err.code !== 'ENOENT') throw err;
    }
    const generated = crypto.randomBytes(24).toString('base64url');
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, generated, { mode: 0o600 });
    return generated;
  }

  return crypto.randomBytes(24).toString('base64url');
}

const adminPassword = resolveAdminPassword();

users['admin'] = {
  id: nextUserId++,
  login: 'admin',
  passwordHash: crypto.createHash('sha256').update(adminPassword).digest('hex'),
  enabled2FA: true,
  session: null
};

// Мультфильмы
let cartoons = [];
let nextCartoonId = 1;

// Кадры (хранятся как base64)
let frames = [];
let nextFrameId = 1;

// Вспомогательные функции
function generateSessionToken() {
  return Math.random().toString(36).substring(2, 15);
}

function findUserBySession(token) {
  const login = sessions[token];
  return login ? users[login] : null;
}

function saveSession(login, token) {
  sessions[token] = login;
  if (users[login]) users[login].session = token;
}

async function call2fa(method, path, data = null) {
  const url = `${TWOFA_SERVICE_URL}${path}`;
  const options = {
      method,
      headers: { 'Content-Type': 'application/json' },
  };
  if (data) {
      options.body = JSON.stringify(data);
  }
  try {
      const res = await fetch(url, options);
      const body = await res.json().catch(() => ({}));
      return { ok: res.ok, status: res.status, data: body };
  } catch (e) {
      return { ok: false, status: 500, data: { error: 'Service unavailable' } };
  }
}

// ----- Регистрация -----
app.post('/api/register', (req, res) => {
  const { login, password } = req.body;
  if (!login || !password) return res.status(400).json({ error: 'Логин и пароль обязательны' });
  if (users[login]) return res.status(409).json({ error: 'Пользователь уже существует' });
  users[login] = {
    id: nextUserId++,
    login,
    passwordHash: crypto.createHash('sha256').update(password).digest('hex'),
    enabled2FA: false,
    session: null
  };
  console.log(`[+] Зарегистрирован: ${login}`);
  res.status(201).json({ success: true, login });
});

// ----- Аутентификация -----
app.post('/api/login', async (req, res) => {
  const { login, password } = req.body;
  const user = users[login];
  if (!user) return res.status(401).json({ error: 'Invalid credentials' });
  const hash = crypto.createHash('sha256').update(password).digest('hex');
  if (user.passwordHash !== hash) return res.status(401).json({ error: 'Invalid credentials' });
  if (user.enabled2FA) {
    const result = await call2fa('POST', '/generate', { login: login });
    if (!result.ok) {
        return res.status(500).json({ error: '2FA service error' });
    }
    return res.json({ require2FA: true, login });
  }
  const session = generateSessionToken();
  saveSession(login, session);
  res.cookie('auth', session, { httpOnly: true });
  res.json({ success: true, session });
});

app.put('/api/user/password', (req, res) => {
  const { newPassword } = req.query;
  const authToken = req.cookies.auth;
  if (!authToken) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(authToken);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  if (!newPassword) return res.status(400).json({ error: 'newPassword required' });
  user.passwordHash = crypto.createHash('sha256').update(newPassword).digest('hex');
  console.log(`[!] Password changed for ${user.login} to "${newPassword}"`);
  res.json({ success: true, message: 'Password updated' });
});

app.post('/api/login/2fa', async (req, res) => {
  const { login, code } = req.body;
  if (!login || !code) {
    return res.status(401).json({ error: 'Invalid 2FA code' });
  }

  const checkResult = await call2fa('POST', '/check', { login: login, code });
  if (!checkResult.ok) {
    return res.status(401).json({ error: 'Invalid code' });
  }

  const user = users[login];
  if (!user) return res.status(401).json({ error: 'User not found' });
  const session = generateSessionToken();
  saveSession(login, session);

  if (login === 'admin') {
    res.cookie('flag', FLAG, { httpOnly: true });
  }

  res.cookie('auth', session, { httpOnly: true });
  res.json({ success: true, session });
});

app.get('/api/me', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'No session' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  res.json({ login: user.login, has2FA: user.enabled2FA });
});

// ----- МУЛЬТФИЛЬМЫ -----
// Создать мультфильм (текущий пользователь — владелец)
app.post('/api/cartoons', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const { title, description } = req.body;
  if (!title) return res.status(400).json({ error: 'Title required' });
  const cartoon = {
    id: nextCartoonId++,
    ownerLogin: user.login,
    title,
    description: description || '',
    participants: [user.login],
    inviteTokens: {}
  };
  cartoons.push(cartoon);
  res.status(201).json({ cartoon });
});

// Получить все мультфильмы, где пользователь является участником (владелец или приглашённый)
app.get('/api/cartoons', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const myCartoons = cartoons.filter(c => c.participants.includes(user.login));
  res.json({ cartoons: myCartoons });
});

// Получить конкретный мультфильм (с кадрами) — доступ участникам
app.get('/api/cartoons/:id', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoon = cartoons.find(c => c.id == req.params.id);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  if (!cartoon.participants.includes(user.login)) return res.status(403).json({ error: 'Access denied' });
  const cartoonFrames = frames.filter(f => f.cartoonId === cartoon.id).sort((a,b) => a.order - b.order);
  res.json({ cartoon, frames: cartoonFrames });
});

// Добавить кадр (в конец) — доступ участникам
app.post('/api/cartoons/:id/frames', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoon = cartoons.find(c => c.id == req.params.id);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  if (!cartoon.participants.includes(user.login)) return res.status(403).json({ error: 'Access denied' });
  const { imageData } = req.body;
  if (!imageData) return res.status(400).json({ error: 'Image data required' });
  const maxOrder = frames.filter(f => f.cartoonId === cartoon.id).length;
  const newFrame = {
    id: nextFrameId++,
    cartoonId: cartoon.id,
    order: maxOrder,
    imageData
  };
  frames.push(newFrame);
  res.status(201).json({ frame: newFrame });
});

// Обновить кадр (перезаписать)
app.put('/api/cartoons/:id/frames/:frameId', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoon = cartoons.find(c => c.id == req.params.id);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  if (!cartoon.participants.includes(user.login)) return res.status(403).json({ error: 'Access denied' });
  const frame = frames.find(f => f.id == req.params.frameId && f.cartoonId == cartoon.id);
  if (!frame) return res.status(404).json({ error: 'Frame not found' });
  const { imageData } = req.body;
  frame.imageData = imageData;
  res.json({ frame });
});

// Удалить кадр
app.delete('/api/cartoons/:id/frames/:frameId', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoon = cartoons.find(c => c.id == req.params.id);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  if (!cartoon.participants.includes(user.login)) return res.status(403).json({ error: 'Access denied' });
  const idx = frames.findIndex(f => f.id == req.params.frameId && f.cartoonId == cartoon.id);
  if (idx === -1) return res.status(404).json({ error: 'Frame not found' });
  frames.splice(idx, 1);
  // перенумерация order
  const remaining = frames.filter(f => f.cartoonId === cartoon.id).sort((a,b) => a.order - b.order);
  remaining.forEach((f, i) => f.order = i);
  res.json({ success: true });
});

// Удалить мультфильм (только владелец)
app.delete('/api/cartoons/:id', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const idx = cartoons.findIndex(c => c.id == req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Cartoon not found' });
  const cartoon = cartoons[idx];
  if (cartoon.ownerLogin !== user.login) return res.status(403).json({ error: 'Only owner can delete' });
  frames = frames.filter(f => f.cartoonId !== cartoon.id);
  cartoons.splice(idx, 1);
  res.json({ success: true });
});

// ----- ПРИГЛАШЕНИЯ -----
// Создать приглашение (только владелец)
app.post('/api/cartoons/:id/invites', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoon = cartoons.find(c => c.id == req.params.id);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  if (cartoon.ownerLogin !== user.login) return res.status(403).json({ error: 'Only owner can invite' });
  const inviteToken = crypto.randomBytes(16).toString('hex');
  cartoon.inviteTokens[inviteToken] = { used: false, invitedLogin: null };
  const inviteUrl = `/invite?action=join&cartoonId=${cartoon.id}&token=${inviteToken}`;
  res.json({ token: inviteToken, inviteUrl });
});

// ПРИНЯТЬ ПРИГЛАШЕНИЕ
app.put('/api/cartoons/:cartoonId/invites/:token', (req, res) => {
  const token = req.cookies.auth;
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(token);
  if (!user) return res.status(401).json({ error: 'Invalid session' });
  const cartoonId = parseInt(req.params.cartoonId);
  const inviteToken = req.params.token;
  const cartoon = cartoons.find(c => c.id === cartoonId);
  if (!cartoon) return res.status(404).json({ error: 'Cartoon not found' });
  const invite = cartoon.inviteTokens[inviteToken];
  if (!invite) return res.status(404).json({ error: 'Invalid invite token' });
  if (invite.used) return res.status(400).json({ error: 'Invite already used' });
  if (!cartoon.participants.includes(user.login)) {
    cartoon.participants.push(user.login);
  }
  invite.used = true;
  invite.invitedLogin = user.login;
  console.log(`[+] Пользователь ${user.login} присоединился к мультфильму ${cartoonId}`);
  res.json({ success: true, cartoon });
});

// Корневой маршрут
app.get('/', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html>
    <head><title>Мультбюро API</title></head>
    <body style="background:#1e1910; color:#e6d5b8; font-family: monospace; padding:2rem">
      <h1 style="color:#d94f1a">🎬 Мультбюро API</h1>
      <p>Веб-интерфейс: <a href="${BASE_URL}" style="color:#c9a03d">${BASE_URL}</a></p>
    </body>
    </html>
  `);
});

const PORT = 8000;
app.listen(PORT, () => {
  console.log(`API СоюзМультГиф запущен на порту ${PORT}`);
});