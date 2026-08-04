"""Bedrock Titan text embedding — one call per new/changed Drain3 cluster."""

import json
import os

import boto3
import numpy as np

AWS_PROFILE = os.environ.get("AWS_PROFILE")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBEDDING_DIM = int(os.environ.get("FAISS_DIM", "1024"))

_session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
_bedrock = _session.client("bedrock-runtime", region_name=AWS_REGION)


def embed_text(text):
    resp = _bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIM, "normalize": True}),
        contentType="application/json",
        accept="application/json",
    )
    data = json.loads(resp["body"].read())
    return np.array(data["embedding"], dtype="float32")
