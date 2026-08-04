# --- React build stage disabled (no npm access) ---
# FROM node:20-slim AS web-build
# WORKDIR /web
# COPY log-viewer-ui/web/package.json log-viewer-ui/web/package-lock.json* ./
# RUN npm install
# COPY log-viewer-ui/web/ ./
# RUN npm run build

FROM python:3.13.5-slim
WORKDIR /app

COPY log-viewer/requirements.txt ./worker-requirements.txt
COPY log-viewer-ui/api/requirements.txt ./api-requirements.txt
RUN pip install --no-cache-dir -r worker-requirements.txt -r api-requirements.txt

COPY log-viewer/ ./worker/
COPY log-viewer-ui/api/ ./api/
# COPY --from=web-build /web/dist ./api/static/

COPY log-viewer/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

CMD ["./entrypoint.sh"]
