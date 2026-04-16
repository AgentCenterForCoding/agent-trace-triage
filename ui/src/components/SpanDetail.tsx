import type { ParsedSpan } from '../types';

interface SpanDetailProps {
  span: ParsedSpan;
  isFaultSpan: boolean;
}

export function SpanDetail({ span, isFaultSpan }: SpanDetailProps) {
  const statusCode = span.status?.code === 2 ? 'ERROR' : span.status?.code === 1 ? 'OK' : 'UNSET';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-semibold font-mono">{span.name}</h3>
        {isFaultSpan && (
          <span className="text-xs bg-red-500 text-white px-2 py-0.5 rounded">ROOT CAUSE</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-gray-500">Span ID</span>
          <div className="font-mono text-xs">{span.spanId}</div>
        </div>
        <div>
          <span className="text-gray-500">Parent</span>
          <div className="font-mono text-xs">{span.parentSpanId || '(root)'}</div>
        </div>
        <div>
          <span className="text-gray-500">Layer</span>
          <div className="capitalize">{span.layer}</div>
        </div>
        <div>
          <span className="text-gray-500">Depth</span>
          <div>{span.depth}</div>
        </div>
        <div>
          <span className="text-gray-500">Status</span>
          <div className={statusCode === 'ERROR' ? 'text-red-600 font-medium' : ''}>{statusCode}</div>
        </div>
        <div>
          <span className="text-gray-500">Duration</span>
          <div>{span.durationMs}ms</div>
        </div>
      </div>

      {span.status?.message && (
        <div>
          <span className="text-sm text-gray-500">Status Message</span>
          <div className="mt-1 p-3 bg-red-50 border border-red-200 rounded text-sm font-mono break-all">
            {span.status.message}
          </div>
        </div>
      )}

      {span.attributes && span.attributes.length > 0 && (
        <div>
          <span className="text-sm text-gray-500">Attributes</span>
          <div className="mt-1 space-y-1">
            {span.attributes.map((attr) => {
              const val = attr.value.stringValue ?? attr.value.intValue ?? String(attr.value.boolValue ?? '');
              return (
                <div key={attr.key} className="flex gap-2 text-sm font-mono">
                  <span className="text-gray-500 flex-shrink-0">{attr.key}:</span>
                  <span className="break-all">{val}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
