FROM python:3.13.5-slim
WORKDIR /app

COPY log-viewer-ui/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY log-viewer-ui/api/ ./

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
