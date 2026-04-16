import { useState, useEffect } from 'react';
import { fetchSamples, fetchSample } from '../api/client';
import type { SampleInfo } from '../types';

interface SampleSelectorProps {
  onSelect: (trace: unknown) => void;
  disabled: boolean;
}

export function SampleSelector({ onSelect, disabled }: SampleSelectorProps) {
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSamples()
      .then(setSamples)
      .catch((err) => setError(err.message));
  }, []);

  const handleSelect = async (filename: string) => {
    setLoading(true);
    setError(null);
    try {
      const trace = await fetchSample(filename);
      onSelect(trace);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample');
    } finally {
      setLoading(false);
    }
  };

  if (error) {
    return <div className="text-red-500 text-sm">{error}</div>;
  }

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700">
        Or select a sample trace ({samples.length} available):
      </label>
      <select
        className="w-full p-2 border rounded-lg"
        onChange={(e) => e.target.value && handleSelect(e.target.value)}
        disabled={disabled || loading}
        defaultValue=""
      >
        <option value="">-- Select a sample --</option>
        {samples.map((s) => (
          <option key={s.filename} value={s.filename}>
            {s.filename} ({(s.size_bytes / 1024).toFixed(1)} KB)
          </option>
        ))}
      </select>
      {loading && <div className="text-sm text-gray-500">Loading sample...</div>}
    </div>
  );
}
