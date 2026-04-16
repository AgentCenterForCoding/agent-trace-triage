import type { TriageResult as TriageResultType } from '../types';

interface TriageResultProps {
  result: TriageResultType;
}

const ownerColors: Record<string, string> = {
  model_team: 'bg-purple-100 text-purple-800',
  mcp_team: 'bg-blue-100 text-blue-800',
  agent_team: 'bg-green-100 text-green-800',
  skill_team: 'bg-yellow-100 text-yellow-800',
  user_interaction: 'bg-gray-100 text-gray-800',
};

export function TriageResultDisplay({ result }: TriageResultProps) {
  const confidenceColor =
    result.confidence >= 0.8
      ? 'text-green-600'
      : result.confidence >= 0.6
      ? 'text-yellow-600'
      : 'text-red-600';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Triage Result</h2>
        <span className={`text-lg font-mono ${confidenceColor}`}>
          {(result.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      {/* Primary Owner */}
      <div className="p-4 bg-white rounded-lg border shadow-sm">
        <div className="text-sm text-gray-500 mb-1">Primary Owner</div>
        <span
          className={`inline-block px-3 py-1 rounded-full font-medium ${
            ownerColors[result.primary_owner] || 'bg-gray-100'
          }`}
        >
          {result.primary_owner}
        </span>
        {result.co_responsible.length > 0 && (
          <div className="mt-2">
            <span className="text-sm text-gray-500">Co-responsible: </span>
            {result.co_responsible.map((owner) => (
              <span
                key={owner}
                className={`inline-block px-2 py-0.5 rounded-full text-sm ml-1 ${
                  ownerColors[owner] || 'bg-gray-100'
                }`}
              >
                {owner}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Root Cause */}
      <div className="p-4 bg-white rounded-lg border shadow-sm">
        <div className="text-sm text-gray-500 mb-1">Root Cause</div>
        <p className="text-gray-800">{result.root_cause}</p>
      </div>

      {/* Fault Span */}
      {result.fault_span && (
        <div className="p-4 bg-red-50 rounded-lg border border-red-200">
          <div className="text-sm text-red-600 mb-1">Fault Span</div>
          <div className="font-mono text-sm">
            <div>
              <span className="text-gray-500">name:</span> {result.fault_span.name}
            </div>
            <div>
              <span className="text-gray-500">span_id:</span> {result.fault_span.span_id}
            </div>
            <div>
              <span className="text-gray-500">status:</span>{' '}
              <span className="text-red-600">{result.fault_span.status}</span>
            </div>
            {result.fault_span.status_message && (
              <div>
                <span className="text-gray-500">message:</span>{' '}
                {result.fault_span.status_message}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Action Items */}
      {result.action_items.length > 0 && (
        <div className="p-4 bg-white rounded-lg border shadow-sm">
          <div className="text-sm text-gray-500 mb-2">Action Items</div>
          <ul className="space-y-2">
            {result.action_items.map((item, i) => (
              <li key={i} className="flex items-start">
                <span className="text-blue-500 mr-2">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Source & Pattern */}
      <div className="flex gap-4 text-sm text-gray-500">
        {result.source && (
          <div>
            Source: <span className="font-mono">{result.source}</span>
          </div>
        )}
        {result.fault_pattern && (
          <div>
            Pattern: <span className="font-mono">{result.fault_pattern}</span>
          </div>
        )}
      </div>

      {/* Reasoning (if LLM) */}
      {result.reasoning && (
        <details className="p-4 bg-gray-50 rounded-lg border">
          <summary className="cursor-pointer text-sm text-gray-500">
            LLM Reasoning
          </summary>
          <pre className="mt-2 text-sm whitespace-pre-wrap">{result.reasoning}</pre>
        </details>
      )}
    </div>
  );
}
