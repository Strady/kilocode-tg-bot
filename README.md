# kilocode-tg-bot

Telegram-бот на **aiogram 3.x**, который выступает пультом дистанционного
управления для headless-сервера Kilo Code (`kilo serve` / `kilo daemon start`).
Бот общается с сервером **исключительно** через библиотеку
[`kilocode-client`](https://github.com/Strady/kilocode-client) — никаких прямых
HTTP-вызовов к Kilo-серверу. Достигнут полный паритет с TUI: сессии, живой
стриминг ответов, interrupt, permission-запросы, смена модели/агента,
slash/shell-команды, revert/unrevert, export/import, todo/context.

Бот рассчитан на **одного владельца**: только Telegram `user_id` из
`TELEGRAM_ALLOWED_USER_ID` обрабатывается, все остальные апдейты молча
игнорируются (авторизующий middleware стоит первым в цепочке и покрывает
message / callback_query / inline_query / document).

## Возможности

| Команда | Действие |
|---|---|
| `/start` | Приветствие и текущая активная сессия |
| `/new [title]` | Создать сессию и сделать её активной |
| `/sessions`, `/switch` | Список сессий, выбрать активную (инлайн-кнопки) |
| `/rename <название>` | Переименовать активную сессию |
| `/delete` | Удалить активную сессию (с подтверждением) |
| `/fork [message_id]` | Форк активной сессии |
| обычный текст | Промпт в активную сессию с живым стримингом + кнопка ⏹ Stop |
| `/history`, `/messages` | Переписка активной сессии с пагинацией |
| `/model` | Сменить модель (provider → model, инлайн-выбор) |
| `/agent` | Сменить агента |
| `/run <slash> [args]` | Slash-команда |
| `/shell <cmd> [args]` | Shell-команда (с подтверждением) |
| `/compact` | Сжать контекст (`compact_v2`) |
| `/context` | Показать активный контекст |
| `/todo` | Todo-список сессии |
| `/revert [msg] [part]`, `/unrevert` | Откат / отмена отката |
| `/export` | Экспорт сессии файлом |
| `/import` | Импорт сессии из присланного JSON |
| `/permissions` | Ожидающие permission-запросы (Once/Always/Reject) |
| `/allow_all <on\|off>` | Автоматически разрешать все запросы |
| `/health` | Статус сервера Kilo |
| `/cancel` | Сброс текущего FSM-состояния диалога |

## Требования

- Python >= 3.10
- Running `kilo serve` (или `kilo daemon start`) — см. ниже
- Telegram bot token (через [@BotFather](https://t.me/BotFather))

## Установка

```bash
git clone <repo> kilocode_tg_bot && cd kilocode_tg_bot
uv venv .venv
uv pip install --python .venv/bin/python -e .
cp .env.example .env   # заполните токены
```

(Без `uv` — обычным `python -m venv .venv && .venv/bin/pip install -e .`.)

## Поднять Kilo-сервер

```bash
# Вариант A: одиночный сервер на 127.0.0.1:4096
kilo serve --port 4096

# Вариант B: демон (занимает порт 4097–4116, текущий — в файле состояния демона)
kilo daemon start
```

По умолчанию бот подключается к `http://127.0.0.1:4096`. Если запущен демон,
узнайте его порт из файла состояния демона и укажите его в `KILO_SERVER_URL`.

## Узнать свой Telegram user id

1. Напишите боту [@userinfobot](https://t.me/userinfobot) — он вернёт ваш числовой `id`.
2. Либо создайте своего бота в `@BotFather`, напишите ему что-нибудь и посмотрите
   `update.message.from_user.id` в логе (бот логирует попытки доступа).

## Переменные окружения (`.env`)

| Переменная | Обязательна | По умолчанию | Описание |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Токен бота от @BotFather |
| `TELEGRAM_ALLOWED_USER_ID` | ✅ | — | Telegram user id владельца (без него бот не стартует) |
| `KILO_SERVER_URL` | — | `http://127.0.0.1:4096` | URL сервера Kilo |
| `KILO_SERVER_USERNAME` | — | env / `kilo` | Basic-auth логин |
| `KILO_SERVER_PASSWORD` | — | — | Basic-auth пароль (пусто = без авторизации) |
| `KILO_SERVER_DIRECTORY` | — | — | Каталог проекта при работе с несколькими |
| `TELEGRAM_EDIT_THROTTLE_SECONDS` | — | `1.0` | Мин. интервал между правками стримингового сообщения |
| `MESSAGE_FILE_THRESHOLD` | — | `3900` | Длинный текст шлётся файлом `.txt` выше этого порога |
| `SESSION_STORE_PATH` | — | `kilocode_bot_state.db` | Путь к SQLite для активной сессии |

## Запуск

```bash
.venv/bin/python -m kilocode_tg_bot.bot
```

Или установите как пакет и:

```bash
kilocode-tg-bot
```

### Полный пример запуска

```bash
# 1) сервер
kilo serve --port 4096 &

# 2) конфиг
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_ALLOWED_USER_ID=123456789
KILO_SERVER_URL=http://127.0.0.1:4096
EOF

# 3) бот
.venv/bin/python -m kilocode_tg_bot.bot
```

## Как это устроено

- `config.py` — настройки через `pydantic-settings` (`.env` + окружение).
- `middlewares/auth.py` — первый в цепочке middleware, пропускает только владельца.
- `middlewares/context.py` — инъекция `settings` / `store` / `kilo` в каждый хендлер.
- `services/kilo.py` — один долгоживущий инстанс `Kilo(...)` на процесс, `close()` на shutdown.
- `services/streaming.py` — стриминг с троттлингом правок (buffering дельт, ≥1 сек между edit).
- `state/session_store.py` — активная сессия на владельца в SQLite (`aiosqlite`).
- `state/states.py` — FSM-состояния интерактивных диалогов.
- `handlers/*` — роутеры по функциональности.
- `keyboards/inline.py` — билдеры инлайн-клавиатур.

### Стриминг (важно)

Бот подписывается на `stream_session_events(session.id)` **до** отправки и шлёт
промпт неблокирующим `send_prompt_async`. Текстовые дельты буферизуются и
сливаются в Telegram-сообщение не чаще, чем раз в
`TELEGRAM_EDIT_THROTTLE_SECONDS` — это защищает от `TelegramRetryAfter`. По
`permission.asked` присылается сообщение с кнопками Once/Always/Reject, ответ
уходит через `permission.reply(request_id, ...)`. Остановка — на
`session.turn.close`; interrupt вызывается по кнопке ⏹ Stop (`interrupt(id)`).

## Разработка и тесты

```bash
uv pip install -e ".[dev]" -p .venv
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/ty check
.venv/bin/python -m pytest -q
```

- **ruff** — линтер + форматтер (`pyproject.toml`, `[tool.ruff]`).
- **ty** — типизатор (Astral Rust checker); читает `requires-python` из
  `pyproject.toml` и проверяет корень проекта.
- Тесты не требуют ни сервера, ни Telegram:

  - `test_auth_middleware.py` — авторизация по `user_id` на всех типах апдейтов.
  - `test_streaming_throttle.py` — буферизация дельт и интервал обновлений.
  - `test_integration_mocked.py` — полный сценарий `/new` → промпт → `/sessions` → `/delete` на фейковом клиенте.
  - `test_bot_assembly.py` — сборка Dispatcher и проверка регистрации роутеров.

## Документация

Docstring'и написаны в reStructuredText и рендерятся Sphinx (autodoc).
Собрать документацию:

```bash
uv pip install -e ".[docs]" -p .venv
cd docs && sphinx-build -b html . _build/html
```

HTML попадает в `docs/_build/html/index.html`.

## Лицензия

MIT.