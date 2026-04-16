import type { OTLPSpan, ParsedSpan } from '../types';

function getAttr(span: OTLPSpan, key: string): string | undefined {
  const attr = span.attributes?.find((a) => a.key === key);
  if (!attr) return undefined;
  return attr.value.stringValue ?? attr.value.intValue ?? String(attr.value.boolValue ?? '');
}

function inferLayer(span: OTLPSpan): ParsedSpan['layer'] {
  const name = span.name.toLowerCase();
  if (/^(llm|gen_ai)|model_inference|model_call/.test(name)) return 'model';
  if (/^mcp[_.]|tool_call|tool_execute/.test(name)) return 'mcp';
  if (/skill/.test(name)) return 'skill';
  if (/^(turn|agent_run|agent_step|orchestrat)/.test(name)) return 'agent';
  if (/user|human|approval/.test(name)) return 'user';

  const layerAttr = getAttr(span, 'layer');
  if (layerAttr) {
    const l = layerAttr.toLowerCase();
    if (['agent', 'model', 'mcp', 'skill', 'user'].includes(l)) return l as ParsedSpan['layer'];
  }
  return 'unknown';
}

export function parseTrace(traceJson: unknown): ParsedSpan[] {
  if (!traceJson || typeof traceJson !== 'object') return [];

  const root = traceJson as { resourceSpans?: Array<{ scopeSpans?: Array<{ spans?: OTLPSpan[] }> }> };
  const rawSpans: OTLPSpan[] = [];

  for (const rs of root.resourceSpans ?? []) {
    for (const ss of rs.scopeSpans ?? []) {
      for (const span of ss.spans ?? []) {
        rawSpans.push(span);
      }
    }
  }

  if (rawSpans.length === 0) return [];

  const spanMap = new Map<string, ParsedSpan>();

  for (const raw of rawSpans) {
    const start = Number(raw.startTimeUnixNano);
    const end = Number(raw.endTimeUnixNano);
    const parsed: ParsedSpan = {
      ...raw,
      children: [],
      depth: 0,
      durationMs: Math.round((end - start) / 1_000_000),
      layer: inferLayer(raw),
      isError: raw.status?.code === 2,
      isFaultSpan: false,
    };
    spanMap.set(raw.spanId, parsed);
  }

  const roots: ParsedSpan[] = [];
  for (const span of spanMap.values()) {
    if (span.parentSpanId && spanMap.has(span.parentSpanId)) {
      spanMap.get(span.parentSpanId)!.children.push(span);
    } else {
      roots.push(span);
    }
  }

  function setDepth(span: ParsedSpan, depth: number) {
    span.depth = depth;
    for (const child of span.children) setDepth(child, depth + 1);
  }
  roots.forEach((r) => setDepth(r, 0));

  return roots;
}
