# Stage 1: React 빌드
FROM node:20-alpine AS frontend
WORKDIR /web
COPY flight_front/web/package*.json ./
RUN npm ci
COPY flight_front/web/ ./
RUN npm run build

# Stage 2: Python 앱
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
# crawl4ai 제외 (서버에서는 수집 안 함, GitHub Actions에서 실행)
RUN pip install --no-cache-dir $(grep -v 'crawl4ai' requirements.txt | tr '\n' ' ')

COPY . .
COPY --from=frontend /web/dist flight_front/web/dist

EXPOSE 8000
CMD ["uvicorn", "flight_front.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
