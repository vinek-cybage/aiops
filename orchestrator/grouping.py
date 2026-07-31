from collections import namedtuple

BreachGroup = namedtuple("BreachGroup", ["org_id", "service", "first_ts", "last_ts", "breaches"])


def group_breaches(breaches, window_seconds):
    """Sweep breaches per (org_id, service) in time order; start a new group
    whenever the gap to the previous breach in that org+service exceeds
    window_seconds. Grouping by org_id too (not just service) keeps two
    tenants' breaches for a same-named service from ever merging into one case."""
    groups = []
    by_org_service = {}
    for breach in sorted(breaches, key=lambda b: (b.org_id, b.service, b.ts)):
        by_org_service.setdefault((breach.org_id, breach.service), []).append(breach)

    for (org_id, service), service_breaches in by_org_service.items():
        current = None
        for breach in service_breaches:
            if current is not None and (breach.ts - current.last_ts).total_seconds() <= window_seconds:
                current = current._replace(last_ts=breach.ts, breaches=current.breaches + [breach])
            else:
                if current is not None:
                    groups.append(current)
                current = BreachGroup(org_id=org_id, service=service, first_ts=breach.ts, last_ts=breach.ts, breaches=[breach])
        if current is not None:
            groups.append(current)
    return groups


def build_signature_text(group):
    """Deterministic text used both as the FAISS embedding input and stored in
    cases.signature_text. Deliberately excludes timestamps/ids/trace_ids so that two
    occurrences of the same fault produce near-identical text (and therefore
    near-identical embeddings)."""
    metrics  = sorted({b.metric for b in group.breaches})
    events   = sorted({b.event for b in group.breaches if b.event})
    severity = "critical" if any(b.severity == "critical" for b in group.breaches) else "warning"
    messages = []
    for b in group.breaches:
        if b.severity == "critical" and b.message and b.message not in messages:
            messages.append(b.message)
        if len(messages) >= 2:
            break

    parts = [
        f"service={group.service}",
        f"metrics=[{', '.join(metrics)}]",
    ]
    if events:
        parts.append(f"events=[{', '.join(events)}]")
    parts.append(f"severity={severity}")
    if messages:
        sample = "; ".join(m[:200] for m in messages)
        parts.append(f'sample_messages="{sample}"')
    return "; ".join(parts)
