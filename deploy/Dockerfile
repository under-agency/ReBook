# Бэкенд ReBook: API, бот записи и воркер — один образ, три роли процесса.
# Фронт собирается здесь же и кладётся туда, где его ищет app/main.py (/web/dist).

FROM node:20-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci --no-fund --no-audit
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY apps/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/backend/ ./
COPY --from=web /web/dist /web/dist

RUN useradd -m rebook && chown -R rebook /app
USER rebook

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
