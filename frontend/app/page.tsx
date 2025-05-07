'use client';

import { useState } from 'react';
import ProfileCard from '../components/ProfileCard';

interface Candidate {
  summary: string;
  url: string;
  score?: number;
}

export default function Home() {
  const [name, setName] = useState('');
  const [socialUrl, setSocialUrl] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const NEXT_PUBLIC_BACKEND_URL = process.env.BACKEND_URL;

  const callEnrich = async (url?: string) => {
    setLoading(true);
    setError(null);

    try {
      const payload: any = { name };
      if (url) payload.social_url = url;

      const response = await fetch(`${NEXT_PUBLIC_BACKEND_URL}/api/enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Enrichment failed');

      if (data.candidates) {
        // Disambiguation phase
        setCandidates(data.candidates);
      } else {
        // Final enrichment phase
        setProfile(data);
      }
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
    callEnrich();
  };

  const handleSelectCandidate = async (candidate: Candidate) => {
    setLoading(true);
    setError(null);
    setCandidates([]);
    
    try {
      const response = await fetch(`${NEXT_PUBLIC_BACKEND_URL}/api/full_profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          summary: candidate.summary,
          url: candidate.url
        }),
        credentials: 'include',
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Failed to get full profile');

      setProfile(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
      // Reset to initial state on error
      setCandidates([]);
      setSocialUrl('');
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    setConfirmed(true);
    console.log('Profile confirmed:', profile);
    // TODO: persist confirmed profile to backend
  };

  const handleReject = () => {
    // reset to initial state
    setCandidates([]);
    setSocialUrl('');
    setProfile(null);
    setName('');
  };

  return (
    <div className="min-h-screen bg-gray-100 py-6 flex flex-col justify-center sm:py-12">
      <div className="relative py-3 sm:max-w-xl sm:mx-auto">
        <div className="relative px-4 py-10 bg-white mx-8 md:mx-0 shadow rounded-3xl sm:p-10">
          <div className="max-w-md mx-auto">
            <h1 className="text-2xl font-bold mb-8 text-center">Profile Enrichment</h1>

            {/* Entry Form */}
            {!candidates.length && !profile && !confirmed && (
              <form onSubmit={handleEnrich} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Full Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
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

            {/* Error Display */}
            {error && <div className="text-red-500 text-center mt-4">{error}</div>}

            {/* Candidate Selection */}
            {candidates.length > 0 && (
              <div className="space-y-4">
                <h2 className="text-xl font-semibold">Select Your Profile</h2>
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
                  onClick={handleReject}
                  className="mt-4 w-full bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
                >
                  None of These
                </button>
              </div>
            )}

            {/* Profile JSON Display */}
            {profile && !confirmed && (
              <div className="bg-white rounded-lg shadow p-6 space-y-4">
                <h2 className="text-xl font-semibold">Full Profile Data</h2>
                <pre className="bg-gray-50 p-4 rounded-lg overflow-auto max-h-96 text-sm">
                  {JSON.stringify(profile, null, 2)}
                </pre>
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
                <h2 className="text-xl font-bold text-green-600 mb-4">Profile Confirmed!</h2>
                <button
                  onClick={handleReject}
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
