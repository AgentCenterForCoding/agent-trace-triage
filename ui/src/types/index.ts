// Triage 相关类型定义

export interface FaultSpan {
  span_id: string;
  name: string;
  status: string;
  status_message?: string;
}

export interface FaultChainItem {
  span_id: string;
  name: string;
  layer: string;
  error?: string;
}

export interface TriageResult {
  primary_owner: string;
  co_responsible: string[];
  confidence: number;
  fault_span?: FaultSpan;
  fault_chain: FaultChainItem[];
  root_cause: string;
  action_items: string[];
  source?: string;
  fault_pattern?: string;
  reasoning?: string;
}

export interface ProgressEvent {
  type: 'progress';
  stage: string;
  message: string;
}

export interface ResultEvent {
  type: 'result';
  data: TriageResult;
}

export interface ErrorEvent {
  type: 'error';
  error: string;
}

export type SSEEvent = ProgressEvent | ResultEvent | ErrorEvent;

export interface SampleInfo {
  filename: string;
  size_bytes: number;
}

// OTLP Span 类型
export interface OTLPSpan {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  startTimeUnixNano: string;
  endTimeUnixNano: string;
  status?: {
    code: number;
    message?: string;
  };
  attributes?: Array<{
    key: string;
    value: {
      stringValue?: string;
      intValue?: string;
      boolValue?: boolean;
    };
  }>;
}

export interface ParsedSpan extends OTLPSpan {
  children: ParsedSpan[];
  depth: number;
  durationMs: number;
  layer: 'agent' | 'model' | 'mcp' | 'skill' | 'user' | 'unknown';
  isError: boolean;
  isFaultSpan: boolean;
}
