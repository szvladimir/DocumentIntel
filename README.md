# DocumentIntel

DocumentIntel — FastAPI-сервис для загрузки и анализа PDF-документов: извлечения реквизитов, краткого резюме, семантического поиска и запросов к истории платежей.

## Возможности

- загрузка и извлечение текста из PDF с помощью PyMuPDF;
- извлечение даты, сторон, адреса и сумм счёта;
- индексация текста в ChromaDB и поиск по содержимому;
- резюме документов через OpenAI;
- вопросы о платежах через SQLite. Эндпоинт `/ask-db-intent` преобразует вопрос в ограниченную структуру intent и выполняет параметризованный SQL-запрос.

## Требования

- Python 3.11 или 3.12;
- ключ OpenAI API для `/summary`, `/ask-db` и `/ask-db-intent`;
- Docker — опционально, для контейнерного запуска.

## Локальный запуск

```bash
git clone https://github.com/szvladimir/DocumentIntel.git
cd DocumentIntel

python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\\Scripts\\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Задайте API-ключ OpenAI в текущем сеансе терминала:

```bash
# macOS/Linux
export OPENAI_API_KEY="your_api_key"

# Windows PowerShell
# $env:OPENAI_API_KEY = "your_api_key"
```

Запустите сервер из корня проекта:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Документация OpenAPI будет доступна по адресу [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), а проверка состояния — по `GET /health`.

Все рабочие файлы создаются локально в `data/` и не входят в Git: загруженные и обработанные PDF, SQLite-база и индекс ChromaDB.

## Примеры запросов

Загрузить PDF:

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@./invoice.pdf"
```

Извлечь текст и разобрать реквизиты:

```bash
curl http://127.0.0.1:8000/extract/invoice.pdf
curl -X POST http://127.0.0.1:8000/match/invoice.pdf
```

Создать индекс документа и выполнить поиск:

```bash
curl -X POST http://127.0.0.1:8000/index/invoice.pdf
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query":"сумма к оплате"}'
```

Получить резюме:

```bash
curl http://127.0.0.1:8000/summary/invoice.pdf
```

Запросить сумму платежей через ограниченный intent-интерфейс:

```bash
curl -X POST http://127.0.0.1:8000/ask-db-intent \
  -H "Content-Type: application/json" \
  -d '{"question":"Сколько я заплатил за электричество зимой 2026 года?"}'
```

Для обработки папки с PDF и записи результатов в SQLite:

```bash
python -m app.process_folder \
  --input-dir data/uploads \
  --processed-dir data/processed \
  --failed-dir data/failed \
  --db data/documentintel.db
```

## Запуск в Docker

```bash
docker build -t documentintel .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="your_api_key" \
  -v "${PWD}/data:/app/data" \
  documentintel
```

В PowerShell вместо `${PWD}` можно использовать `${PWD.Path}`. Подключение тома сохраняет базу и индекс между перезапусками контейнера.

## Тесты

```bash
python -m pytest -q
```

## Важное ограничение для запросов платежей

`/ask-db-intent` ожидает таблицу `providers`, связывающую значение `Recipient` с категорией услуги (`electricity`, `water`, `internet_tv` или `housekeeper`). При развёртывании новой базы создайте и заполните эту таблицу до выполнения запросов по категориям.
