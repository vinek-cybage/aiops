FROM node:20-slim
WORKDIR /app
COPY log-viewer-ui/web/package.json log-viewer-ui/web/package-lock.json* ./
RUN npm install
COPY log-viewer-ui/web/ ./
RUN npm run build
EXPOSE 4000
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "4000"]
