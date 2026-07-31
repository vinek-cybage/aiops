import json, time, logging

import boto3, numpy as np

from . import config

logger  = logging.getLogger("orchestrator.embeddings")
bedrock = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)


def embed_text(text: str) -> np.ndarray:
    body = json.dumps({"inputText": text, "dimensions": config.FAISS_DIM, "normalize": True})

    last_err = None
    for attempt in range(3):
        try:
            resp = bedrock.invoke_model(modelId=config.EMBEDDING_MODEL_ID, body=body)
            data = json.loads(resp["body"].read())
            return np.array(data["embedding"], dtype="float32")
        except Exception as e:
            last_err = e
            if "Throttling" in type(e).__name__ or "Throttling" in str(e):
                logger.warning("Bedrock throttled (attempt %d/3): %s", attempt + 1, e)
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_err
