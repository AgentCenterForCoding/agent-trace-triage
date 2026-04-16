import { useState, useCallback } from 'react';

interface TraceUploadProps {
  onUpload: (trace: unknown) => void;
  isLoading: boolean;
}

export function TraceUpload({ onUpload, isLoading }: TraceUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const processFile = useCallback(async (file: File) => {
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      setError(null);
      onUpload(json);
    } catch {
      setError('Invalid JSON file');
    }
  }, [onUpload]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files?.[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  }, [processFile]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      processFile(e.target.files[0]);
    }
  }, [processFile]);

  const handlePaste = useCallback(() => {
    try {
      const json = JSON.parse(jsonInput);
      setError(null);
      onUpload(json);
    } catch {
      setError('Invalid JSON');
    }
  }, [jsonInput, onUpload]);

  return (
    <div className="space-y-4">
      {/* Drag & Drop Zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
        } ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".json"
          onChange={handleFileInput}
          className="hidden"
          id="file-upload"
          disabled={isLoading}
        />
        <label
          htmlFor="file-upload"
          className="cursor-pointer text-gray-600 hover:text-blue-600"
        >
          <div className="text-4xl mb-2">📂</div>
          <p>Drag & drop a trace JSON file here</p>
          <p className="text-sm text-gray-400">or click to select</p>
        </label>
      </div>

      {/* JSON Input */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">
          Or paste JSON directly:
        </label>
        <textarea
          value={jsonInput}
          onChange={(e) => setJsonInput(e.target.value)}
          className="w-full h-32 p-3 border rounded-lg font-mono text-sm resize-none"
          placeholder='{"resourceSpans": [...]}'
          disabled={isLoading}
        />
        <button
          onClick={handlePaste}
          disabled={!jsonInput.trim() || isLoading}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Analyze
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 text-red-600 rounded-lg">
          {error}
        </div>
      )}
    </div>
  );
}
