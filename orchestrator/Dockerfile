FROM python:3.13.5-slim
WORKDIR /app

COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/ ./orchestrator/

CMD ["python", "-m", "orchestrator.worker"]
