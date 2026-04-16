interface ProgressDisplayProps {
  stage: string;
  message: string;
}

const stageConfig: Record<string, { icon: string; label: string; color: string }> = {
  parsing: { icon: '📄', label: 'Parsing Trace', color: 'bg-gray-50 text-gray-700' },
  start: { icon: '🚀', label: 'Starting', color: 'bg-blue-50 text-blue-700' },
  thinking: { icon: '🧠', label: 'Thinking', color: 'bg-blue-50 text-blue-700' },
  tool: { icon: '🔧', label: 'Reading Files', color: 'bg-indigo-50 text-indigo-700' },
  l1_rules: { icon: '📏', label: 'L1 Rules Analysis', color: 'bg-amber-50 text-amber-700' },
  l2_llm: { icon: '🤖', label: 'L2 LLM Analysis', color: 'bg-purple-50 text-purple-700' },
  result: { icon: '📊', label: 'Formatting Result', color: 'bg-green-50 text-green-700' },
  step_done: { icon: '✓', label: 'Step Complete', color: 'bg-gray-50 text-gray-600' },
};

export function ProgressDisplay({ stage, message }: ProgressDisplayProps) {
  const config = stageConfig[stage] || { icon: '⏳', label: stage, color: 'bg-gray-50 text-gray-600' };

  return (
    <div className={`flex items-center gap-4 p-4 rounded-lg border ${config.color}`}>
      <div className="text-2xl animate-pulse">{config.icon}</div>
      <div className="flex-1 min-w-0">
        <div className="font-medium">{config.label}</div>
        <div className="text-sm opacity-75 truncate">{message}</div>
      </div>
      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin opacity-50" />
    </div>
  );
}
