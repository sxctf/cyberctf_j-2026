# AI Security CTF — запуск стендов

6 самостоятельных заданий по безопасности AI-систем. Каждая папка автономна:
`description.md`, исходники, `docker-compose.yml` и `.env.example`.

Один стенд = один игрок/команда. Входа нет, состояние общее. Для нескольких
команд поднимайте отдельные стенды (и отдельные `.env` с разными флагами/портами).

## Требования

- Docker 24+ с Compose v2
- Для заданий с LLM — Authorization Key GigaChat (Freemium)

## Быстрый старт

Все `.env` уже подготовлены под GigaChat. Общий порядок для любого задания:

    cd "Имя папки"          # имена со скобками — обязательно в кавычках
    cp .env.example .env    # если шаблон есть; иначе создать .env вручную (см. ниже)
    nano .env               # проверить/заменить флаг, порт, ключ
    docker compose up -d --build
    docker compose ps

Остановить и удалить данные стенда:

    docker compose down -v

## Таблица заданий

| Папка                  | Адрес                                                 | LLM                    | Где лежит compose        |
| ---------------------- | ----------------------------------------------------- | ---------------------- | ------------------------ |
| `[Троянский_конь]`     | http://localhost:8100                                 | не нужен               | `src/docker-compose.yml` |
| `[Поручение_сверху]`   | http://localhost:8201, Gitea: http://localhost:8202   | GigaChat               | корень                   |
| `[MCP_Маркетплейс]`    | http://localhost:8300                                 | GigaChat               | корень                   |
| `[Сделка–вне_бюджета]` | http://localhost:8324, магазин: http://localhost:8320 | GigaChat               | корень                   |
| `[Архивариус-67]`      | http://localhost:8400                                 | GigaChat (или fixture) | корень                   |
| `[Тритон]`             | http://localhost:8402                                 | не нужен               | корень                   |

## Ключ GigaChat

1. Войдите через Сбер ID в [Studio](https://developers.sber.ru/studio/workspaces/my-space/get/gigachat-api),
   создайте проект **GigaChat API** (Freemium подключается автоматически).
2. В **Настройках API** нажмите **Получить ключ**.
3. Сохраните **Authorization Key** — показывается один раз.
4. Вставьте в `.env` нужного задания **без кавычек и без слова `Basic`**:

   GIGACHAT_API_KEY=<ваш Authorization Key>

Нужен именно Authorization Key, не Access Token (токен живёт 30 минут, сервисы
получают его сами).

> Freemium работает в один поток. Не запускайте несколько заданий с агентами
> на одном ключе одновременно — делайте это последовательно.

## Задание 1 — `[Троянский_конь]`

LLM не нужен. Compose лежит в подпапке `src`.

    cd "[Троянский_конь]"
    cd src
    nano .env

`.env` (в папке `src`):

    FLAG_TASK_03=FLAG{ваш_флаг}
    WEB_PORT=8100

    docker compose up -d --build
    docker compose ps

Открывать: http://localhost:8100

## Задание 2 — `[Поручение_сверху]`

Нужен GigaChat. Два порта: портал и Gitea.

    cd "[Поручение_сверху]"
    nano .env

`.env`:

    FLAG_TASK_05=FLAG{ваш_флаг}
    WEB_PORT=8201
    GITEA_PORT=8202
    PUBLIC_HOST=localhost

    GITEA_ADMIN_USER=ctfadmin
    GITEA_ADMIN_PASS=ctfadmin123!
    WEBHOOK_SECRET=замените-на-случайную-строку

    GIGACHAT_API_KEY=<ваш Authorization Key>
    GIGACHAT_SCOPE=GIGACHAT_API_PERS
    GIGACHAT_MODEL=GigaChat-Pro

    docker compose up -d --build
    docker compose ps

Портал: http://localhost:8201
Gitea: http://localhost:8202 (логин/пароль — из `.env`)

⚠️ Первый запуск долгий: Gitea healthcheck до ~2,5 минут + `gitea-init`.
⚠️ `GITEA_ADMIN_PASS` применяется только при первом создании админа. Поменяли
после запуска — нужен `docker compose down -v` или смена пароля через веб.
⚠️ Если агент не вызывает инструменты — переключитесь на OpenAI-совместимый
сервер (см. раздел ниже).

## Задание 3 — `[MCP_Маркетплейс]`

Нужен GigaChat.

    cd "[MCP_Маркетплейс]"
    nano .env

`.env`:

    FLAG_TASK_07=FLAG{ваш_флаг}
    WEB_PORT=8300

    GIGACHAT_API_KEY=<ваш Authorization Key>
    GIGACHAT_SCOPE=GIGACHAT_API_PERS
    GIGACHAT_MODEL=GigaChat-Pro

    docker compose up -d --build
    docker compose ps

Открывать: http://localhost:8300

## Задание 4 — `[Сделка–вне_бюджета]`

Нужен GigaChat. Два порта: портал и магазин.

    cd "[Сделка–вне_бюджета]"
    nano .env

`.env`:

    FLAG_TASK_06=FLAG{ваш_флаг}
    WEB_PORT=8324
    SHOP_PORT=8320
    PUBLIC_HOST=localhost
    TASK06_SHARED_SECRET=замените-на-случайную-строку
    TASK06_BUDGET=5000

    GIGACHAT_API_KEY=<ваш Authorization Key>
    GIGACHAT_SCOPE=GIGACHAT_API_PERS
    GIGACHAT_MODEL=GigaChat-Pro

    docker compose up -d --build
    docker compose ps

Портал: http://localhost:8324
Магазин: http://localhost:8320

## Задание 5 — `[Архивариус-67]`

Нужен GigaChat. Один сервис, один порт.

    cd "[Архивариус-67]"
    nano .env

`.env` для игры:

    FLAG_TASK_08=FLAG{ваш_флаг}
    WEB_PORT=8400

    ARCHIVE_LLM_BACKEND=gigachat
    GIGACHAT_API_KEY=<ваш Authorization Key>
    GIGACHAT_MODEL=GigaChat-2-Max

`.env` для проверки без ключа (заготовленные ответы, не настоящая модель):

    FLAG_TASK_08=FLAG{ваш_флаг}
    WEB_PORT=8400

    ARCHIVE_LLM_BACKEND=fixture

    docker compose up -d --build
    docker compose ps

Открывать: http://localhost:8400

## Задание 6 — `[Тритон]`

LLM не нужен. Compose в корне задания.

    cd "[Тритон]"
    nano .env

`.env`:

    FLAG_TASK_10=FLAG{ваш_флаг}
    WEB_PORT=8402

    docker compose up -d --build
    docker compose ps

Открывать: http://localhost:8402

## Альтернатива GigaChat: OpenAI-совместимый сервер

Для заданий с агентами (`Поручение сверху`, `MCP маркетплейс`,
`Сделка вне бюджета`) можно использовать OpenAI-совместимый сервер.
В прошлый раз эти задания проверялись именно так: GigaChat возвращал
вызовы инструментов не в том формате, который ждёт код.

В `.env` задания:

    GIGACHAT_API_KEY=

    LLM_BACKEND_URL=http://host.docker.internal:11434/v1
    LLM_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct
    OPENAI_API_KEY=sk-...

⚠️ `host.docker.internal` — если LLM-сервер запущен на хосте Mac. Сервер
должен слушать `0.0.0.0`, а не только `127.0.0.1`.
⚠️ `Архивариус-67` этот вариант не поддерживает: там только `gigachat`
или `fixture`.

## Частые проблемы

**`zsh: no matches found: [Имя]`**
Скобки в zsh — спецсимволы. Берите имя в кавычки: `cd "[Имя]"` или
экранируйте: `cd \[Имя\]`. Удобно набрать `cd Имя` и нажать Tab.

**`cp: .env.example: No such file or directory`**
В некоторых раздачах шаблона нет — создайте `.env` вручную по образцу
из нужного раздела выше.

**`docker: command not found`**
Docker Desktop установлен, но CLI не в PATH. Settings → Advanced →
включить установку CLI-инструментов, либо добавить в `~/.zshrc`:
`export PATH="$PATH:$HOME/.docker/bin"`, затем `source ~/.zshrc`.

**Контейнер `unhealthy`**
Смотрите логи конкретного сервиса:
`docker compose logs -f <имя-сервиса>`.
Для заданий с LLM чаще всего дело в ключе (`GIGACHAT_API_KEY`) или в том,
что агент не может достучаться до модели.

**Порт занят**
Поменяйте `WEB_PORT` / `GITEA_PORT` / `SHOP_PORT` в `.env` и перезапустите:
`docker compose up -d`.

**Хочу сбросить состояние задания**
`docker compose down -v` — удалит volume'ы с базой и загрузками.
