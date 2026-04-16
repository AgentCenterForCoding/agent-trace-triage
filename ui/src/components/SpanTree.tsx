import { useState } from 'react';
import type { ParsedSpan } from '../types';

interface SpanTreeProps {
  spans: ParsedSpan[];
  faultSpanId?: string;
  onSelectSpan: (span: ParsedSpan) => void;
  selectedSpanId?: string;
}

const statusColors: Record<string, string> = {
  ERROR: 'bg-red-100 text-red-700 border-red-300',
  OK: 'bg-green-50 text-green-700 border-green-200',
  UNSET: 'bg-gray-50 text-gray-600 border-gray-200',
};

const layerBadge: Record<string, string> = {
  agent: 'bg-green-100 text-green-700',
  model: 'bg-purple-100 text-purple-700',
  mcp: 'bg-blue-100 text-blue-700',
  skill: 'bg-yellow-100 text-yellow-700',
  user: 'bg-gray-100 text-gray-600',
  unknown: 'bg-gray-100 text-gray-500',
};

function SpanNode({
  span,
  faultSpanId,
  onSelectSpan,
  selectedSpanId,
}: {
  span: ParsedSpan;
  faultSpanId?: string;
  onSelectSpan: (span: ParsedSpan) => void;
  selectedSpanId?: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const isFault = span.spanId === faultSpanId;
  const isSelected = span.spanId === selectedSpanId;
  const hasChildren = span.children.length > 0;
  const statusCode = span.status?.code === 2 ? 'ERROR' : span.status?.code === 1 ? 'OK' : 'UNSET';

  return (
    <div className="ml-4 first:ml-0">
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors border ${
          isSelected ? 'ring-2 ring-blue-400 ' : ''
        }${isFault ? 'ring-2 ring-red-400 ' : ''}${statusColors[statusCode] || statusColors.UNSET}`}
        onClick={() => onSelectSpan(span)}
      >
        {hasChildren && (
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600 flex-shrink-0"
          >
            {expanded ? '▼' : '▶'}
          </button>
        )}
        {!hasChildren && <span className="w-5" />}

        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${layerBadge[span.layer] || layerBadge.unknown}`}>
          {span.layer.toUpperCase()}
        </span>

        <span className="font-mono text-sm font-medium truncate">{span.name}</span>

        <span className="text-xs text-gray-400 ml-auto flex-shrink-0">
          {span.durationMs}ms
        </span>

        {isFault && (
          <span className="text-xs bg-red-500 text-white px-1.5 py-0.5 rounded flex-shrink-0">
            ROOT
          </span>
        )}
      </div>

      {hasChildren && expanded && (
        <div className="mt-1 space-y-1 border-l-2 border-gray-200 ml-2">
          {span.children.map((child) => (
            <SpanNode
              key={child.spanId}
              span={child}
              faultSpanId={faultSpanId}
              onSelectSpan={onSelectSpan}
              selectedSpanId={selectedSpanId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function SpanTree({ spans, faultSpanId, onSelectSpan, selectedSpanId }: SpanTreeProps) {
  if (spans.length === 0) {
    return <div className="text-gray-400 text-sm text-center py-4">No spans to display</div>;
  }

  return (
    <div className="space-y-1">
      {spans.map((span) => (
        <SpanNode
          key={span.spanId}
          span={span}
          faultSpanId={faultSpanId}
          onSelectSpan={onSelectSpan}
          selectedSpanId={selectedSpanId}
        />
      ))}
    </div>
  );
}
