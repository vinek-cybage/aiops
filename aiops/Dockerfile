FROM node:20-slim AS frontend-build
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.13.5-slim
WORKDIR /app

COPY aiops/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY aiops/ ./
COPY --from=frontend-build /app/dist/ ./web/

ENV FRONTEND_DIR=/app/web
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
