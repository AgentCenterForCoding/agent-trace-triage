import { useState, useCallback } from 'react';
import { TraceUpload } from './components/TraceUpload';
import { TraceList } from './components/TraceList';
import { ProgressDisplay } from './components/ProgressDisplay';
import { TriageResultDisplay } from './components/TriageResult';
import { SpanTree } from './components/SpanTree';
import { SpanDetail } from './components/SpanDetail';
import { FaultChain } from './components/FaultChain';
import { Settings } from './components/Settings';
import { triageSSE } from './api/client';
import { parseTrace } from './utils/parseTrace';
import type { TriageResult, SSEEvent, ParsedSpan } from './types';
import './App.css';

type AppState = 'idle' | 'loading' | 'complete' | 'error';

function App() {
  const [state, setState] = useState<AppState>('idle');
  const [progress, setProgress] = useState<{ stage: string; message: string } | null>(null);
  const [result, setResult] = useState<TriageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [spans, setSpans] = useState<ParsedSpan[]>([]);
  const [selectedSpan, setSelectedSpan] = useState<ParsedSpan | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const handleUpload = useCallback((trace: unknown) => {
    setState('loading');
    setProgress({ stage: 'parsing', message: 'Starting analysis...' });
    setResult(null);
    setError(null);
    setSelectedSpan(null);

    const parsed = parseTrace(trace);
    setSpans(parsed);

    triageSSE(
      trace,
      (event: SSEEvent) => {
        if (event.type === 'progress') {
          setProgress({ stage: event.stage, message: event.message });
        }
      },
      (triageResult: TriageResult) => {
        setResult(triageResult);
        setState('complete');
        setProgress(null);
      },
      (errorMsg: string) => {
        setError(errorMsg);
        setState('error');
        setProgress(null);
      }
    );
  }, []);

  const handleReset = useCallback(() => {
    setState('idle');
    setProgress(null);
    setResult(null);
    setError(null);
    setSpans([]);
    setSelectedSpan(null);
  }, []);

  const faultSpanId = result?.fault_span?.span_id;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agent Trace Triage</h1>
            <p className="text-gray-500 text-sm">Fault attribution analysis for Agent execution traces</p>
          </div>
          <button
            onClick={() => setShowSettings(true)}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
            title="Settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {state === 'idle' ? (
          /* Idle: Upload + Trace List */
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-lg shadow-sm border max-w-2xl mx-auto">
              <h2 className="text-lg font-semibold mb-4">Upload Trace</h2>
              <TraceUpload onUpload={handleUpload} isLoading={false} />
            </div>
            <div className="bg-white p-6 rounded-lg shadow-sm border">
              <TraceList onSelect={handleUpload} disabled={false} />
            </div>
          </div>
        ) : state === 'loading' ? (
          /* Loading: Progress + Span tree preview */
          <div className="max-w-2xl mx-auto space-y-6">
            {progress && <ProgressDisplay stage={progress.stage} message={progress.message} />}
            {spans.length > 0 && (
              <div className="bg-white p-4 rounded-lg shadow-sm border">
                <h3 className="text-sm font-medium text-gray-500 mb-3">Trace Structure</h3>
                <SpanTree spans={spans} onSelectSpan={setSelectedSpan} selectedSpanId={selectedSpan?.spanId} />
              </div>
            )}
          </div>
        ) : state === 'error' ? (
          /* Error */
          <div className="max-w-2xl mx-auto">
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="text-red-600 font-medium">Analysis Failed</div>
              <div className="text-red-500 text-sm mt-1">{error}</div>
              <button onClick={handleReset} className="mt-3 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700">
                Try Again
              </button>
            </div>
          </div>
        ) : (
          /* Complete: Full result view */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Span Tree */}
            <div className="lg:col-span-1 space-y-4">
              <div className="bg-white p-4 rounded-lg shadow-sm border">
                <h3 className="text-sm font-medium text-gray-500 mb-3">Span Tree</h3>
                <SpanTree
                  spans={spans}
                  faultSpanId={faultSpanId}
                  onSelectSpan={setSelectedSpan}
                  selectedSpanId={selectedSpan?.spanId}
                />
              </div>

              {selectedSpan && (
                <div className="bg-white p-4 rounded-lg shadow-sm border">
                  <SpanDetail span={selectedSpan} isFaultSpan={selectedSpan.spanId === faultSpanId} />
                </div>
              )}
            </div>

            {/* Right: Triage Result + Fault Chain */}
            <div className="lg:col-span-2 space-y-6">
              {result && (
                <>
                  <TriageResultDisplay result={result} />
                  <FaultChain result={result} />
                  <button onClick={handleReset} className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300">
                    Analyze Another Trace
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Settings Modal */}
      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
    </div>
  );
}

export default App;
