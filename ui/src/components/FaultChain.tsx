import type { TriageResult } from '../types';

interface FaultChainProps {
  result: TriageResult;
}

const layerColors: Record<string, string> = {
  agent: 'border-green-400 bg-green-50',
  model: 'border-purple-400 bg-purple-50',
  mcp: 'border-blue-400 bg-blue-50',
  skill: 'border-yellow-400 bg-yellow-50',
};

export function FaultChain({ result }: FaultChainProps) {
  if (!result.fault_chain || result.fault_chain.length === 0) return null;

  return (
    <div className="p-4 bg-white rounded-lg border shadow-sm">
      <div className="text-sm text-gray-500 mb-3">Fault Chain</div>
      <div className="space-y-2">
        {result.fault_chain.map((item, i) => (
          <div key={i} className="flex items-stretch gap-2">
            {/* Connector */}
            <div className="flex flex-col items-center w-6 flex-shrink-0">
              <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                i === 0 ? 'bg-red-500' : 'bg-gray-300'
              }`} />
              {i < result.fault_chain.length - 1 && (
                <div className="w-0.5 flex-1 bg-gray-200 mt-1" />
              )}
            </div>

            {/* Card */}
            <div className={`flex-1 p-3 rounded border-l-4 text-sm ${
              layerColors[item.layer] || 'border-gray-300 bg-gray-50'
            }`}>
              <div className="flex items-center gap-2">
                <span className="font-mono font-medium">{item.name}</span>
                <span className="text-xs text-gray-400">{item.layer}</span>
                <span className="text-xs font-mono text-gray-400 ml-auto">
                  {item.span_id?.slice(-4)}
                </span>
              </div>
              {item.error && (
                <div className="text-red-600 mt-1 text-xs">{item.error}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
