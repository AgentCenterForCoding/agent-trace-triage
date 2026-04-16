import { useState, useEffect } from 'react';
import { fetchSamples, fetchSample } from '../api/client';
import type { SampleInfo } from '../types';

interface TraceListProps {
  onSelect: (trace: unknown) => void;
  disabled: boolean;
}

// 根据文件名解析故障类型
function parseTraceInfo(filename: string): { category: string; description: string } {
  const name = filename.replace('.json', '');
  
  // 4_x 系列：基础故障类型
  if (name.startsWith('4_')) {
    const patterns: Record<string, string> = {
      '4_1_model_timeout': 'Model API 超时',
      '4_2_model_bad_output': 'Model 输出格式错误',
      '4_3_mcp_connection': 'MCP 连接失败',
      '4_4_mcp_tool_error': 'MCP 工具执行错误',
      '4_5_skill_not_found': 'Skill 未找到',
      '4_6_skill_execute_error': 'Skill 执行错误',
      '4_7_agent_stuck': 'Agent 死循环',
      '4_8_agent_retry_exhausted': 'Agent 重试耗尽',
      '4_9_upstream_bad_params': '上游参数错误',
      '4_10_cascade_truncation': '级联截断',
      '4_11_cumulative_timeout': '累积超时',
      '4_12_mcp_no_retry': 'MCP 无重试',
      '4_13_tool_loop': '工具调用循环',
      '4_14_content_filter': '内容过滤拦截',
      '4_15_model_bad_tool_params': 'Model 工具参数错误',
      '4_16_agent_timeout_short': 'Agent 超时配置过短',
      '4_17_swallowed_error': '吞掉的错误',
      '4_18_rate_limit': '速率限制',
      '4_19_three_layer_chain': '三层错误链',
      '4_20_semantic_error': '语义错误',
    };
    return { category: 'Basic', description: patterns[name] || name };
  }
  
  // 5_x 系列：复杂场景
  if (name.startsWith('5_')) {
    const patterns: Record<string, string> = {
      '5_1_multi_layer_error': '多层错误',
      '5_2_semantic_tool_error': '语义工具错误',
      '5_3_partial_batch_failure': '部分批量失败',
      '5_4_cascading_timeout_chain': '级联超时链',
      '5_5_hidden_content_filter': '隐藏的内容过滤',
      '5_6_conflicting_signals': '冲突信号',
      '5_7_retry_exhausted_unclear': '重试耗尽不明确',
      '5_8_user_approval_cascade': '用户审批级联',
      '5_9_sub_agent_failure': '子 Agent 失败',
      '5_10_mixed_tool_types': '混合工具类型',
    };
    return { category: 'Complex', description: patterns[name] || name };
  }
  
  // c_x 系列：边界场景
  if (name.startsWith('c')) {
    return { category: 'Edge', description: name.replace('c', '').replace(/_/g, ' ') };
  }
  
  return { category: 'Other', description: name };
}

export function TraceList({ onSelect, disabled }: TraceListProps) {
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSamples()
      .then(setSamples)
      .catch((err) => setError(err.message));
  }, []);

  const handleSelect = async (filename: string) => {
    setLoading(filename);
    setError(null);
    try {
      const trace = await fetchSample(filename);
      onSelect(trace);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample');
      setLoading(null);
    }
  };

  if (error) {
    return (
      <div className="p-4 bg-red-50 text-red-600 rounded-lg">
        Failed to load samples: {error}
      </div>
    );
  }

  // 按类别分组
  const grouped = samples.reduce((acc, sample) => {
    const info = parseTraceInfo(sample.filename);
    if (!acc[info.category]) acc[info.category] = [];
    acc[info.category].push({ ...sample, ...info });
    return acc;
  }, {} as Record<string, (SampleInfo & { category: string; description: string })[]>);

  const categoryOrder = ['Basic', 'Complex', 'Edge', 'Other'];
  const categoryColors: Record<string, string> = {
    Basic: 'bg-blue-50 border-blue-200',
    Complex: 'bg-purple-50 border-purple-200',
    Edge: 'bg-orange-50 border-orange-200',
    Other: 'bg-gray-50 border-gray-200',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          Sample Traces ({samples.length})
        </h2>
      </div>

      {categoryOrder.map((category) => {
        const items = grouped[category];
        if (!items?.length) return null;

        return (
          <div key={category} className="space-y-2">
            <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider">
              {category} ({items.length})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {items.map((sample) => (
                <button
                  key={sample.filename}
                  onClick={() => handleSelect(sample.filename)}
                  disabled={disabled || loading !== null}
                  className={`p-3 rounded-lg border text-left transition-all hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed ${
                    categoryColors[category]
                  } ${loading === sample.filename ? 'ring-2 ring-blue-500' : ''}`}
                >
                  <div className="font-mono text-sm text-gray-800 truncate">
                    {sample.filename.replace('.json', '')}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {sample.description}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {(sample.size_bytes / 1024).toFixed(1)} KB
                  </div>
                  {loading === sample.filename && (
                    <div className="text-xs text-blue-600 mt-1 animate-pulse">
                      Loading...
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
