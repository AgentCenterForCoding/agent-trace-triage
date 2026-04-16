import { useState, useEffect } from 'react';

const API_BASE = '/api/v1';

interface SettingsState {
  api_key_configured: boolean;
  auth_enabled: boolean;
}

export function Settings({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [authEnabled, setAuthEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/settings`)
      .then((r) => r.json())
      .then((data) => {
        setSettings(data);
        setAuthEnabled(data.auth_enabled);
      })
      .catch(() => setMessage({ type: 'error', text: 'Failed to load settings' }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const body: Record<string, unknown> = { auth_enabled: authEnabled };
      if (apiKey) body.api_key = apiKey;
      else if (settings?.api_key_configured) body.api_key = '';

      await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setMessage({ type: 'success', text: 'Settings saved' });
      setApiKey('');
      const updated = await fetch(`${API_BASE}/settings`).then((r) => r.json());
      setSettings(updated);
      setAuthEnabled(updated.auth_enabled);
    } catch {
      setMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">Settings</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={settings?.api_key_configured ? '(configured - enter new to change)' : 'Enter API key'}
              className="w-full p-2 border rounded-lg text-sm"
            />
            {settings?.api_key_configured && (
              <p className="text-xs text-green-600 mt-1">API Key is configured</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="auth-enabled"
              checked={authEnabled}
              onChange={(e) => setAuthEnabled(e.target.checked)}
              className="w-4 h-4"
            />
            <label htmlFor="auth-enabled" className="text-sm text-gray-700">
              Enable API authentication
            </label>
          </div>

          {message && (
            <div className={`p-3 rounded-lg text-sm ${
              message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'
            }`}>
              {message.text}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
