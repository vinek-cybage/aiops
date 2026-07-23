FROM python:3.13.5-slim
WORKDIR /app

COPY aiops/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY aiops/*.py ./
COPY web/ ./web/

ENV FRONTEND_DIR=/app/web
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
