// API 客户端

import type { SampleInfo, TriageResult, SSEEvent } from '../types';

const API_BASE = '/api/v1';

export async function fetchSamples(): Promise<SampleInfo[]> {
  const res = await fetch(`${API_BASE}/samples`);
  if (!res.ok) throw new Error('Failed to fetch samples');
  return res.json();
}

export async function fetchSample(filename: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}/samples/${filename}`);
  if (!res.ok) throw new Error('Failed to fetch sample');
  return res.json();
}

export function triageSSE(
  trace: unknown,
  onProgress: (event: SSEEvent) => void,
  onComplete: (result: TriageResult) => void,
  onError: (error: string) => void
): () => void {
  const controller = new AbortController();

  fetch(`${API_BASE}/triage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trace }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const chunk of lines) {
          if (!chunk.trim()) continue;

          const eventMatch = chunk.match(/^event: (\w+)/);
          const dataMatch = chunk.match(/^data: (.+)$/m);

          if (eventMatch && dataMatch) {
            const eventType = eventMatch[1];
            const data = JSON.parse(dataMatch[1]);

            if (eventType === 'progress') {
              onProgress({ type: 'progress', ...data });
            } else if (eventType === 'result') {
              onComplete(data);
            } else if (eventType === 'error') {
              onError(data.message || data.error || 'Unknown error');
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message);
      }
    });

  return () => controller.abort();
}
