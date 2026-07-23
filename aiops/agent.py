import json, os, re, time, boto3

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-west-2"))
MODEL   = os.getenv("MODEL_ID", "arn:aws:bedrock:us-west-2:997594557385:application-inference-profile/wdxqrgk9hynd")

# Langfuse v2
_lf = None
try:
    if os.getenv("LANGFUSE_PUBLIC_KEY"):
        from langfuse import Langfuse
        _lf = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
except Exception:
    pass


def _invoke(prompt: str, max_tokens: int = 6000, generation=None) -> str:
    body     = json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens,
                           "messages": [{"role": "user", "content": prompt}]})
    t0       = time.time()
    resp     = bedrock.invoke_model(modelId=MODEL, body=body)
    raw_resp = json.loads(resp["body"].read())
    latency  = round(time.time() - t0, 2)
    text     = raw_resp["content"][0]["text"].strip()
    usage    = raw_resp.get("usage", {})

    if generation:
        generation.end(
            output=text,
            usage={"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
            metadata={"latency_s": latency},
        )

    return re.sub(r"\n?```$", "", re.sub(r"^```[a-z]*\n?", "", text)).strip()


def analyze(raw_input: str | list[dict], open_incidents: list[dict]) -> dict:
    if isinstance(raw_input, str):
        log_section       = f"RAW LOG TEXT (unparsed):\n{raw_input}"
        parse_instruction = 'STEP 1 — Parse the raw log text into the "logs" array.\nEach entry: {"time":"HH:MM:SS","level":"error|warn|info|debug","service":"name","src":"source","msg":"message"}\n- Infer service names from context; group multiline entries (e.g. stack traces) into one msg'
    else:
        log_section       = "STRUCTURED LOGS (already parsed):\n" + "\n".join(
            f"[{l['time']}] [{l['level'].upper()}] [{l['service']}] {l['msg']}" for l in raw_input)
        parse_instruction = 'STEP 1 — Logs are already parsed. Copy them as-is into the "logs" array.'

    inc_section = ("CURRENTLY OPEN INCIDENTS:\n" + "\n".join(
        f"- {i['inc_id']}: {i['title']} | {i['severity']} | {i['ai_summary']}" for i in open_incidents)
    ) if open_incidents else "CURRENTLY OPEN INCIDENTS: none"

    prompt = f"""You are an SRE incident analysis agent. You have access to logs AND distributed traces. Perform ALL steps and return ONE JSON object.

{log_section}

{inc_section}

{parse_instruction}

STEP 2 — Analyze the logs and trace spans together to identify the single most critical incident.
- Use trace spans to understand the exact call path and where latency or errors originated
- Correlate log ERROR/CRITICAL lines with span durations and error flags in the traces
- Identify root cause service vs downstream affected services using the trace hierarchy

STEP 3 — Duplicate and cascade detection using traces + logs:
- DUPLICATE: Same root cause on the same service as an open incident. Evidence: same service erroring, same error pattern, trace shows same failure point. Set duplicate_of to its inc_id.
- CASCADE: This is a downstream symptom of an open incident. Evidence: trace shows this service calling the already-affected service. Set cascade_of to root inc_id, cascade_entry to affected service and symptom.
- NEITHER: New independent incident. Both null.
- Use trace data as strong signal — if the trace shows service A calling service B and B is already in an open incident, this is likely a cascade not a duplicate.

STEP 4 — Extract evidence from both logs and traces:
- Include specific log lines with timestamps as log evidence
- Include span names, durations, and error flags as trace evidence
- Identify the exact span where the failure originated

Return ONLY this JSON, no markdown:
{{
  "logs": [{{"time":"HH:MM:SS","level":"error|warn|info|debug","service":"name","src":"source","msg":"message"}}],
  "title": "short incident title (max 8 words)",
  "severity": "critical|high|medium|low",
  "affected_services": ["service1"],
  "team": "team responsible",
  "hypotheses": [{{"rank":1,"text":"most likely root cause","confidence":87}},{{"rank":2,"text":"second possible cause","confidence":45}}],
  "evidence": [{{"type":"log|trace|pattern","label":"source","text":"relevant detail"}}],
  "ai_summary": "2-sentence summary: what happened and recommended action",
  "duplicate_of": null,
  "cascade_of": null,
  "cascade_entry": null
}}"""

    # Langfuse v2 tracing
    lf_trace   = _lf.trace(name="incident-analysis", metadata={"open_incidents": len(open_incidents)}) if _lf else None
    generation = lf_trace.generation(name="analyze", model=MODEL, input=prompt) if lf_trace else None

    raw = _invoke(prompt, generation=generation)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        short_prompt = prompt + "\n\nIMPORTANT: Keep ai_summary under 100 words. Keep each hypothesis under 20 words. Keep each evidence text under 30 words. Response must be valid complete JSON."
        gen2   = lf_trace.generation(name="analyze-retry", model=MODEL, input=short_prompt) if lf_trace else None
        result = json.loads(_invoke(short_prompt, generation=gen2))

    if lf_trace:
        lf_trace.update(output={"title": result.get("title"), "severity": result.get("severity")})
        _lf.flush()

    return result
