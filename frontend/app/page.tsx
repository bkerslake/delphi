'use client';

import { useState } from 'react';

interface Candidate {
  summary: string;
  url: string;
  score?: number;
}

type ManualMode = 'enrich' | 'confirm' | null;

export default function Home() {
  const [name, setName] = useState('');
  const [socialUrl, setSocialUrl] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [location, setLocation] = useState<string>('');
  const [requireUrl, setRequireUrl] = useState(false);
  const [manualMode, setManualMode] = useState<ManualMode>(null);
  const [urlMessage, setUrlMessage] = useState<string>('');
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const backendUrl = 'http://localhost:8000';

  const callEnrich = async (url?: string) => {
    setLoading(true);
    setError(null);
    setRequireUrl(false);
    setManualMode(null);
    try {
      const payload: any = { name };
      if (url) payload.social_url = url;

      const response = await fetch(`${backendUrl}/api/enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Enrichment failed');

      if (data.require_social_url) {
        setRequireUrl(true);
        setManualMode('enrich');
        setUrlMessage(data.message || 'Please provide a social URL');
        if (data.location) setLocation(data.location);
      } else if (data.candidates) {
        setLocation(data.location || '');
        setCandidates(data.candidates);
      } else {
        setError('Unexpected response from server');
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const callConfirmProfile = async (linkedinUrl: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${backendUrl}/api/confirm_profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, linkedin_url: linkedinUrl }),
        credentials: 'include',
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Confirmation failed');

      setProfile(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleEnrich = (e: React.FormEvent) => {
    e.preventDefault();
    setCandidates([]);
    setProfile(null);
    setConfirmed(false);
    setError(null);
    callEnrich();
  };

  const handleSelectCandidate = async (candidate: Candidate) => {
    setLoading(true);
    setError(null);
    setCandidates([]);

    try {
      const response = await fetch(`${backendUrl}/api/full_profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, summary: candidate.summary, url: candidate.url }),
        credentials: 'include',
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Failed to get full profile');

      setProfile(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
      setCandidates([]);
      setSocialUrl('');
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitUrl = () => {
    if (socialUrl) {
      if (manualMode === 'enrich') {
        callEnrich(socialUrl);
      } else if (manualMode === 'confirm') {
        callConfirmProfile(socialUrl);
      }
    }
  };

  const handleConfirm = () => {
    setConfirmed(true);
    console.log('Profile confirmed:', profile);
    // TODO: persist confirmed profile to backend
  };

  const handleNoneOfThese = () => {
    // ask for manual LinkedIn URL to confirm
    setManualMode('confirm');
    setRequireUrl(true);
    setUrlMessage('None matched. Please provide your LinkedIn profile URL to confirm.');
    setCandidates([]);
  };

  const handleRestart = () => {
    setName('');
    setSocialUrl('');
    setCandidates([]);
    setLocation('');
    setRequireUrl(false);
    setManualMode(null);
    setUrlMessage('');
    setProfile(null);
    setError(null);
    setConfirmed(false);
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-6 flex flex-col justify-center sm:py-12">
      <div className="relative py-3 sm:max-w-xl sm:mx-auto">
        <div className="relative px-4 py-10 bg-white dark:bg-gray-800 mx-8 md:mx-0 shadow rounded-3xl sm:p-10">
          <div className="max-w-md mx-auto">
            <h1 className="text-2xl font-bold mb-8 text-center text-gray-900 dark:text-white">Delphi Enrichment</h1>

            {/* Entry Form */}
            {!candidates.length && !profile && !confirmed && !requireUrl && (
              <form onSubmit={handleEnrich} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 dark:text-white">Full Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-gray-900 dark:text-white bg-white dark:bg-gray-700"
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700"
                >
                  {loading ? 'Searching...' : 'Find Profiles'}
                </button>
              </form>
            )}

            {/* Require URL / Manual Confirm */}
            {requireUrl && !profile && (
              <div className="space-y-4">
                <p className="text-center text-gray-700">{urlMessage}</p>
                <input
                  type="url"
                  placeholder="https://linkedin.com/in/..."
                  value={socialUrl}
                  onChange={(e) => setSocialUrl(e.target.value)}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-gray-900 dark:text-white bg-white dark:bg-gray-700"
                />
                <button
                  onClick={handleSubmitUrl}
                  disabled={loading || !socialUrl}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700"
                >
                  {loading
                    ? (manualMode === 'confirm' ? 'Confirming...' : 'Enriching...')
                    : (manualMode === 'confirm' ? 'Confirm URL' : 'Submit URL')}
                </button>
                <button
                  onClick={handleRestart}
                  className="w-full bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
                >
                  Start Over
                </button>
              </div>
            )}

            {/* Error Display */}
            {error && <div className="text-red-500 text-center mt-4">{error}</div>}

            {/* Candidate Selection */}
            {candidates.length > 0 && (
              <div className="space-y-4">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Select Your Profile</h2>
                <p className="text-sm text-gray-700 dark:text-gray-300">Location: {location}</p>
                <ul className="divide-y divide-gray-200">
                  {candidates.map((cand, idx) => (
                    <li key={idx} className="py-2 flex justify-between items-center">
                      <span>{cand.summary}</span>
                      <button
                        onClick={() => handleSelectCandidate(cand)}
                        className="ml-4 bg-indigo-600 text-white px-3 py-1 rounded hover:bg-indigo-700"
                      >
                        This is me
                      </button>
                    </li>
                  ))}
                </ul>
                <button
                  onClick={handleNoneOfThese}
                  className="mt-4 w-full bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
                >
                  None of These
                </button>
              </div>
            )}

            {/* Profile JSON Display */}
            {profile && !confirmed && (
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-4">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Profile Summary</h2>
                <div className="prose dark:prose-invert max-w-none">
                  <div className="bg-gray-50 dark:bg-gray-700 p-6 rounded-lg">
                    <p className="text-gray-800 dark:text-gray-200 whitespace-pre-line leading-relaxed">
                      {profile.summary}
                    </p>
                  </div>
                </div>
                <div className="flex space-x-4 pt-4">
                  <button
                    onClick={handleConfirm}
                    className="flex-1 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setProfile(null)}
                    className="flex-1 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}

            {/* Confirmation Message */}
            {confirmed && (
              <div className="text-center">
                <h2 className="text-xl font-bold text-green-700 dark:text-green-400 mb-4">Profile Confirmed!</h2>
                <button
                  onClick={handleRestart}
                  className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700"
                >
                  Start Over
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
