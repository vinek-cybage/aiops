import json, logging, re

import boto3

from . import config

logger  = logging.getLogger("orchestrator.llm")
bedrock = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)


def _invoke(prompt: str, max_tokens: int = None) -> str:
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = bedrock.invoke_model(modelId=config.LLM_MODEL_ID, body=body)
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()
    return re.sub(r"\n?```$", "", re.sub(r"^```[a-z]*\n?", "", text)).strip()


def _build_prompt(case, alerts, logs) -> str:
    alert_lines = "\n".join(
        f"- [{a['severity']}] {a['metric']} on {a['service']} "
        f"(triggered_at={a['triggered_at']}, seen {a['duplicate_count']}x) | {a['raw_payload']}"
        for a in alerts
    ) or "none"

    log_lines = "\n".join(
        f"[{l['ts']}] [{l['level']}] [{l['event']}] {l['message']}" for l in logs
    ) or "none"

    return f"""You are an SRE incident analysis agent. A monitoring pipeline has already grouped
raw metric/log breaches into a single "case" for one service and deduplicated it against
past cases (see occurrence_count / similarity_score below — do NOT re-decide duplicate vs
new, that decision is already made). Your job is ONLY to summarize this case for a human:
a short title, ranked root-cause hypotheses, and supporting evidence.

CASE:
service={case['primary_service']} | status={case['status']} | occurrence_count={case['occurrence_count']}
signature: {case['signature_text']}

ALERTS:
{alert_lines}

LOGS (chronological, same service, case time window):
{log_lines}

Return ONLY this JSON, no markdown:
{{
  "title": "short incident title (max 8 words)",
  "hypotheses": [{{"rank":1,"text":"most likely root cause","confidence":87}},
                 {{"rank":2,"text":"second possible cause","confidence":40}}],
  "evidence": [{{"type":"log|metric|pattern","label":"source","text":"relevant detail"}}],
  "ai_summary": "2-sentence summary: what happened and recommended next step"
}}"""


def summarize_case(case, alerts, logs) -> dict:
    prompt = _build_prompt(case, alerts, logs)
    raw = _invoke(prompt)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Malformed JSON from LLM for case %s, retrying with stricter prompt", case["id"])
        strict_prompt = prompt + "\n\nIMPORTANT: Keep ai_summary under 60 words. Response must be valid complete JSON."
        return json.loads(_invoke(strict_prompt))
