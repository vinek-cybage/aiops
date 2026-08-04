FROM python:3.13.5-slim
WORKDIR /app

COPY log-viewer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY log-viewer/ ./

CMD ["python", "-u", "service.py"]
