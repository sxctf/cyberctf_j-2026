# СоюзМультГиф

## 1. Описание сервиса для участников

СоюзМультГиф — коллективная анимационная мастерская «по ГОСТ 2.0». Здесь регистрируются аниматоры, заводят мультфильмы, рисуют кадры на холсте и собирают из них GIF.

Владелец проекта может пригласить соавторов по ссылке: приглашённый присоединяется к мультфильму и рисует наравне с остальными.

---

## 2. Подробное описание функционала

### 2.1. Состав стенда

Четыре сервиса в `souz-mult-gif/docker-compose.yml`:

| Сервис | Образ / стек | Порт | Роль |
|--------|----------------|------|------|
| `frontend` | React SPA + nginx | `3000 → 80` | UI, прокси `/api/` на backend |
| `backend` | Express 4 | `8000` | REST API, пользователи/мультфильмы in-memory |
| `2fa-service` | Express 4 | `3001` (только docker-сеть) | 6-значные коды 2FA, TTL 60 с |
| `bot` | Puppeteer + Chromium | `8080` | логин `admin` и переход по URL |

Флаг задаётся в `docker-compose.yml` как `FLAG` (`${FLAG:-flag{THIS_IS_FAKE_FLAG}}`) и попадает в cookie backend при успешном 2FA admin.

```
браузер  →  frontend:80 (nginx)
                ├─ SPA
                └─ /api/*  →  backend:8000
backend  →  2fa-service:3001
игрок    →  bot:8080  POST /visit  {"url": "..."}
```

Все данные (пользователи, сессии, мультфильмы, кадры, коды 2FA) живут в памяти процесса. Рестарт backend обнуляет сессии. Пароль admin при этом не сбрасывается: он один раз генерируется при первом старте и лежит в томе `admin_secret`. Новый пароль появляется только вместе с новым томом.

### 2.2. Frontend

React 18 + `react-router-dom` + axios (`withCredentials: true`). Сборку раздаёт nginx:

```
location /      → try_files $uri /index.html
location /api/  → proxy_pass http://backend:8000/api/
```

Cookie, которые backend ставит на ответы `/api/*`, браузер считает cookie хоста фронтенда. Отдельного origin у API для SPA нет.

| Путь | Компонент | Назначение |
|------|-----------|------------|
| `/` | `App` | Лендинг |
| `/login` | `Login` | Логин/пароль, при необходимости шаг 2FA |
| `/register` | `Register` | Регистрация |
| `/cartoons` | `CartoonList` | Список своих мультфильмов, создание, приглашение, удаление |
| `/cartoon/:id` | `CartoonEditor` | Холст, кадры, скачивание GIF |
| `/profile` | `Profile` | Логин текущего пользователя (`GET /api/me`) |
| `/invite` | `AcceptInvite` | Принятие приглашения по query-параметрам |

Навигация смотрит на `GET /api/me`: при 200 показывает «Профиль» и «Выйти», иначе — «Войти» / «Регистрация». Выход только клиентский: cookie `auth` затирается датой в прошлом, серверного `/logout` нет.

Холст (`DrawingCanvas`): 640×640, цвет и толщина кисти, сохранение кадра как `canvas.toDataURL()` (PNG в data-URL). Кадры показываются через `<img src={imageData}>`. Просмотр листает кадры с шагом 200 мс. GIF собирается на клиенте библиотекой gif.js (CDN + `/gif.worker.js`), кнопка «Скачать GIF» только у владельца; размер кадра в GIF — 400×400.

`SessionView.js` в роутер не подключён и ходит в несуществующие `/api/render-sessions/*`. Это мёртвый код.

### 2.3. Backend: маршруты

Express слушает `:8000`. JSON до 10 МБ, `cookie-parser`, CORS: `origin = BASE_URL` (`http://localhost:3000` по умолчанию), `credentials: true`.

| Метод | Путь | Auth | Назначение |
|-------|------|------|------------|
| `POST` | `/api/register` | нет | Регистрация |
| `POST` | `/api/login` | нет | Пароль; если 2FA — генерация кода, без cookie |
| `POST` | `/api/login/2fa` | нет | Проверка кода, выдача `auth`; для `admin` ещё cookie `flag` |
| `GET` | `/api/me` | cookie | `{ login, has2FA }` |
| `PUT` | `/api/user/password` | cookie | Смена пароля, `newPassword` из **query** |
| `POST` | `/api/cartoons` | cookie | Создать мультфильм |
| `GET` | `/api/cartoons` | cookie | Список, где пользователь участник |
| `GET` | `/api/cartoons/:id` | cookie | Мультфильм + кадры (только участникам) |
| `DELETE` | `/api/cartoons/:id` | cookie | Удалить (только владелец) |
| `POST` | `/api/cartoons/:id/frames` | cookie | Добавить кадр |
| `PUT` | `/api/cartoons/:id/frames/:frameId` | cookie | Перезаписать кадр |
| `DELETE` | `/api/cartoons/:id/frames/:frameId` | cookie | Удалить кадр, перенумеровать `order` |
| `POST` | `/api/cartoons/:id/invites` | cookie | Создать invite-токен (только владелец) |
| `PUT` | `/api/cartoons/:cartoonId/invites/:token` | cookie | Принять приглашение |
| `GET` | `/` | нет | HTML-заглушка «Мультбюро API» |

### 2.4. Пользователи и сессии

Хранилище — объект `users` в памяти. Пароль: SHA-256 без соли (`crypto.createHash('sha256')`).

При старте создаётся пользователь:

```
login:        admin
password:     случайный, общий с ботом
enabled2FA:   true
```

Пароль — 24 байта в `base64url`. Backend пишет его в `ADMIN_PASSWORD_FILE` (`/shared/admin_password` на томе `admin_secret`), если файла ещё нет, и хеширует SHA-256. Если задан `ADMIN_PASSWORD`, берётся он и файл не создаётся. В лог пароль не попадает.

Регистрация того же логина даёт `409`. У новых пользователей `enabled2FA = false`.

Сессия — строка `Math.random().toString(36).substring(2, 15)`, кладётся в `sessions[token] = login` и в cookie `auth` с флагом `httpOnly`. `SameSite` и `Domain` не заданы. На `/api/login` cookie ставится только если 2FA выключена; у admin этот путь cookie не выдаёт.

`GET /api/me` без cookie или с неизвестным токеном — `401`.

### 2.5. Двухфакторный вход

Если `user.enabled2FA`, `POST /api/login` при верном пароле вызывает `POST {2fa-service}/generate` с `{ login }` и отвечает `{ require2FA: true, login }` без сессии.

`POST /api/login/2fa` принимает `{ login, code }`, прогоняет их через `POST {2fa-service}/check`. При успехе создаёт сессию. Если `login === 'admin'`, берёт `process.env.FLAG` и ставит:

```
Set-Cookie: flag=<FLAG>; HttpOnly
```

В UI флаг нигде не рендерится. Из `document.cookie` его не прочитать.

Код после успешной проверки не сжигается: до истечения TTL его можно предъявить повторно.

### 2.6. Мультфильмы и кадры

Мультфильм: `id`, `ownerLogin`, `title`, `description`, `participants[]`, `inviteTokens{}`. Создатель сразу единственный участник.

Кадр: `id`, `cartoonId`, `order`, `imageData` (строка base64/data-URL). Доступ на чтение и правку кадров — всем из `participants`. Удалить сам мультфильм может только `ownerLogin`.

### 2.7. Приглашения

`POST /api/cartoons/:id/invites` (владелец) генерирует 16 байт hex и отвечает:

```
{ token, inviteUrl: "/invite?action=join&cartoonId=<id>&token=<token>" }
```

Фронт показывает абсолютную ссылку `origin + inviteUrl`.

Страница `/invite` (`AcceptInvite.js`) на маунте читает query и, если есть `action=join`, `cartoonId` и `token`, делает:

```javascript
const url = `/api/cartoons/${cartoonId}/invites/${token}`;
axios.put(url, {}, { withCredentials: true });
```

Значения из query в URL не экранируются и не проверяются на `../` или `?`.

Серверный `PUT /api/cartoons/:cartoonId/invites/:token` требует cookie, ищет мультфильм по `parseInt(cartoonId)`, проверяет токен в `inviteTokens`, одноразовость и добавляет текущего пользователя в `participants`.

### 2.8. Смена пароля

```javascript
app.put('/api/user/password', (req, res) => {
  const { newPassword } = req.query;
  // cookie auth → пользователь
  user.passwordHash = sha256(newPassword);
});
```

Новый пароль берётся из query, не из JSON-тела. CSRF-токена нет. Достаточно cookie `auth` и любого `PUT` на этот путь с `?newPassword=...`. Origin для same-site запроса с фронтенда совпадает с cookie.

### 2.9. 2FA-сервис

Внутренний Express на `:3001`. В compose только `expose`, с хоста порта нет.

| Метод | Путь | Назначение |
|-------|------|------------|
| `POST` | `/generate` | `{ login }` → 6-значный OTP, кладётся как `pendingCodes[code] = login` |
| `GET` | `/code?login=` | отдать текущий код **без авторизации** |
| `POST` | `/check` | `{ login, code }` → 200, если `pendingCodes[code]` truthy |

Код пишется в stdout: `Generated code for admin: 123456`. `GET /code` нужен боту, чтобы пройти форму 2FA. С хоста 2fa-service недоступен.

### 2.10. Бот

HTTP-сервер на `:8080`. Единственный метод:

```
POST /visit
Content-Type: application/json
{"url": "http://..."}
```

Проверки origin/allowlist нет: любой URL принимается. Ответ сразу `{ status: "visiting" }`, переход идёт в фоне.

Сценарий `visitUrl`:

1. Открыть `{FRONTEND_URL}/login` (`http://frontend` внутри сети).
2. Ввести `admin` и пароль из `/shared/admin_password`, нажать `#login-btn`.
3. Если появилось поле «Код 2FA» — `GET {2fa-service}/code?login=admin`, ввести код, нажать `#check-btn`, подождать 2 с.
4. `page.goto(targetUrl)`, ждать `networkidle2` + ещё 5 с, закрыть вкладку.

Бот ходит на фронтенд, поэтому cookie `auth` висит на хосте `frontend`. Ссылка для визита должна быть из docker-сети (`http://frontend/...`), а не `http://localhost:3000` с точки зрения Chromium в контейнере.

В `bot/package.json` есть `telegraf`, в `.env` — `BOT_TOKEN`. Бот их не читает.

### 2.11. Где флаг

Переменная `FLAG` в окружении backend. Единственная выдача — `Set-Cookie: flag=...; HttpOnly` на успешном `POST /api/login/2fa` при `login=admin`. Нужны верный пароль admin (после смены — новый) и живой код 2FA.

Локальное значение по умолчанию: `flag{THIS_IS_FAKE_FLAG}`. На площадке задаётся через env.

### 2.12. Запуск

```bash
cd souz-mult-gif
docker compose up -d --build
```

- UI: http://localhost:3000
- API: http://localhost:8000
- бот: http://localhost:8080

Предустановленный admin: логин `admin`, пароль случайный (том `admin_secret`), 2FA включена. Игроку пароль неизвестен.

Эталонный солвер (из корня задания):

```bash
python3 solve.py
python3 solve.py --target http://localhost:3000 --bot http://localhost:8080
```

Стандартной библиотеки Python достаточно. Код 2FA с площадки не читается: солвер обходит проверку, отправив `__proto__` вместо OTP.

### 2.13. Структура репозитория

- `souz-mult-gif/docker-compose.yml` — frontend, backend, 2fa-service, bot
- `souz-mult-gif/frontend/` — React SPA и nginx
- `souz-mult-gif/backend/` — Express API
- `souz-mult-gif/2fa-service/` — генерация и проверка кодов
- `souz-mult-gif/bot/` — Puppeteer-админ
- `solve.py` — эталонное решение
- `writeup/exploit.html` — минимальная страница, которая открывает invite-URL

---

## Подробный разбор решения

Первым делом разберёмся, где вообще лежит флаг и кому он достаётся. В бэкенде есть ровно одно место, где флаг покидает сервер, — это ответ на успешный ввод 2FA, причём только для админа:

```
if (login === 'admin') {
    res.cookie('flag', FLAG, { httpOnly: true });
}
```

То есть задача сводится к одному: как-то залогиниться под `admin` и дойти до конца формы 2FA. Админ заведён при старте, но пароль каждый раз случайный и игроку неизвестен. Двухфакторка у него включена с самого старта:

```
users['admin'] = {
  login: 'admin',
  passwordHash: sha256(adminPassword),
  enabled2FA: true,
  ...
};

if (user.enabled2FA) {
    await call2fa('POST', '/generate', { login: login });
    return res.json({ require2FA: true, login });
}
```

Даже если бы пароль был известен, этого мало: для аутентификации нужен второй фактор - одноразовый код. Код генерируется на отдельном 2fa-сервисе, который наружу не проброшен. Значит, честно получить код не выйдет — придётся обходить проверку. Отложим это на потом и вернёмся к паролю.

Посмотрим, как вообще меняется пароль пользователя:

```
app.put('/api/user/password', (req, res) => {
  const { newPassword } = req.query;
  const authToken = req.cookies.auth;
  if (!authToken) return res.status(401).json({ error: 'Unauthorized' });
  const user = findUserBySession(authToken);
  ...
  user.passwordHash = crypto.createHash('sha256').update(newPassword).digest('hex');
```

Здесь сразу бросается в глаза несколько проблем. Новый пароль берётся из query-строки, то есть целиком помещается в URL. Никакого CSRF-токена нет, Origin и Referer никто не проверяет — достаточно, чтобы в запросе улетела кука `auth`. Получается классический CSRF: если заставить браузер жертвы сделать такой `PUT`, пароль сменится на наш. Своей сессией пароль админа, разумеется, не поменять — нужна сессия самого админа.

А вот и способ её задействовать — бот. Его эндпоинт `POST /visit` принимает любой URL и перед тем, как по нему перейти, сам заходит в аккаунт админа (пароль читает из того же файла, что записал backend, код 2FA — с внутреннего сервиса):

```
if (req.method === 'POST' && parsedUrl.pathname === '/visit') {
    ...
    targetUrl = json.url;
    visitUrl(targetUrl)
}

await page.type('input[placeholder="Логин"]', 'admin');
await page.type('input[placeholder="Пароль"]', PASSWORD);
await page.click('#login-btn');
...
await page.goto(targetUrl, { waitUntil: 'networkidle2' });
```

То есть бот — это и есть наша «жертва» с валидной сессией админа. Осталось придумать, какую ссылку ему скормить, чтобы из его браузера ушёл нужный `PUT`. Просто отдать боту `/api/user/password` не получится: это кросс-доменный запрос с чужой страницы, его срежет браузер. Нам нужна страница на самом фронтенде, которая сама сходит на API. И такая есть — обработчик приглашений.

`AcceptInvite` читает параметры из query и подставляет их в путь запроса конкатенацией строк, без какой-либо проверки:

```
const params = new URLSearchParams(window.location.search);
const action = params.get('action');
const cartoonId = params.get('cartoonId');
const token = params.get('token');

if (action === 'join' && cartoonId && token) {
    const url = `/api/cartoons/${cartoonId}/invites/${token}`;
    axios.put(url, {}, { withCredentials: true })
```

Проблема в том, что `cartoonId` и `token` попадают в URL как есть. А браузер, перед тем как отправить запрос, сам нормализует путь: схлопывает `..` и обрезает всё после первого `?` в query-строку. Значит, если в `cartoonId` подсунуть не число, а кусок пути с переходами наверх и собственным `?`, то хвост `/invites/${token}` перестанет быть частью пути и уедет в query — на итоговый маршрут он больше не повлияет. Это и есть client-side path traversal.

Нормальная ссылка-приглашение выглядит так:

```
/invite?action=join&cartoonId=1&token=<hex>
```

Подменяем `cartoonId` на путь к смене пароля и прямо внутри него открываем query, чтобы `newPassword` доехал до бэкенда:

```
cartoonId = ../../../../api/user/password?newPassword=hacked123&a=a
token     = ../
```

Тогда `AcceptInvite` склеит такую строку:

```
/api/cartoons/../../../../api/user/password?newPassword=hacked123&a=a/invites/../
```

А после нормализации пути браузером из неё получится совсем другой запрос:

```
PUT /api/user/password?newPassword=hacked123&a=a/invites/../
```

Разберём, почему пэйлоад собран именно так. Знак `?` внутри `cartoonId` открывает query-строку: всё, что `AcceptInvite` дописывает дальше (`/invites/../`), становится значением безобидного параметра `a`, а не частью пути. Без этого `?` хвост остался бы в пути, адрес свернулся бы в `/api/user/password/`, и `newPassword` просто не попал бы в query — бэкенд ответил бы `400`. Поэтому `a=a` и нужен: он «съедает» лишний хвост. При этом `token` обязан быть непустым — иначе не выполнится условие `cartoonId && token` и запрос вообще не уйдёт.

Теперь отдаём готовую ссылку боту. Важная деталь: адрес должен указывать на имя сервиса внутри docker-сети (`http://frontend/...`). Если дать `localhost`, бот откроет сам себя — Chromium резолвит `localhost` в контейнер бота, а не во фронтенд.

```
POST /visit
{"url":"http://frontend/invite?action=join&cartoonId=../../../../api/user/password%3FnewPassword%3Dhacked123%26a%3Da&token=../"}
```

Бот заходит под админом, открывает `/invite`, страница сама делает `PUT` с его кукой — и пароль админа становится `hacked123`.

Дальше логинимся уже сами с новым паролем:

```
POST /api/login
{"login":"admin","password":"hacked123"}
```

В ответ приходит `{ "require2FA": true, "login": "admin" }` — пароль действительно наш, но сессию ещё не дают: сервер сгенерировал одноразовый код и ждёт его. Вот тут и возвращаемся к отложенной проблеме 2FA. Код нам недоступен, значит, надо найти слабость в самой проверке.

Смотрим на 2fa-сервис. Коды он хранит в обычном объекте, где **ключ** — это сам OTP, а значение — логин:

```
const pendingCodes = {};  // { "482916": "admin" }

function issueOTP(login) {
    const code = generateRandom6Digit();
    pendingCodes[code] = login;
}

app.post('/check', (req, res) => {
    const { login, code } = req.body;
    if (pendingCodes[code]) {           // уязвимость
        return res.status(200).json({ success: true });
    }
    return res.status(403).json({ success: false });
});
```

Вся проверка держится на строчке `if (pendingCodes[code])`. Казалось бы, если такого кода не было, то и свойства нет, и условие ложно. Но обращение по ключу в JavaScript работает иначе: если в самом объекте ключа нет, движок идёт искать его вверх по цепочке прототипов. У любого `{}` прототип — это `Object.prototype`, а там уже лежат готовые свойства: `constructor`, `toString`, `valueOf`, `hasOwnProperty` и, в том числе, `__proto__`. Все они — функции или объекты, то есть в `if` дают `true`.

Получается, достаточно прислать в качестве кода имя любого такого свойства. Сервер ничего не мутирует — он просто читает чужое унаследованное свойство и принимает его за валидный код. Отправляем:

```
POST /api/login/2fa
{"login":"admin","code":"__proto__"}
```

```
pendingCodes["__proto__"]
//  -> Object.prototype  (значение «истинно»)
//  -> if () проходит, сервер отдаёт сессию админа
```

Никакого настоящего OTP мы не знали, но проверку прошли. В ответе прилетает `Set-Cookie: flag=...` вместе с новой кукой `auth` — это и есть флаг.

Всю цепочку автоматизирует готовый скрипт:

```
python3 solve.py --target http://localhost:3000 --bot http://localhost:8080
```
