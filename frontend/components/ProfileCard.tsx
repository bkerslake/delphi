'use client';

import React from 'react';

interface Profile {
  name?: {
    full?: string;
  };
  linkedin?: {
    profile_pic?: string;
    title?: string;
    org?: string;
    location?: {
      text?: string;
    };
    summary?: string;
  };
  company?: {
    name?: string;
  };
}

interface ProfileCardProps {
  profile: Profile;
  onConfirm: () => void;
  onReject: () => void;
}

const ProfileCard: React.FC<ProfileCardProps> = ({ profile, onConfirm, onReject }) => {
  if (!profile) return null;

  const linkedinData = profile.linkedin || {};
  const companyData = profile.company || {};

  return (
    <div className="max-w-md mx-auto bg-white rounded-xl shadow-md overflow-hidden md:max-w-2xl m-4">
      <div className="p-8">
        <div className="flex items-center">
          {linkedinData.profile_pic && (
            <img 
              className="h-16 w-16 rounded-full mr-4" 
              src={linkedinData.profile_pic} 
              alt="Profile"
            />
          )}
          <div>
            <h2 className="text-xl font-bold">{profile.name?.full || 'Unknown'}</h2>
            <p className="text-gray-600">{linkedinData.title || 'No title available'}</p>
          </div>
        </div>

        <div className="mt-4">
          <p className="text-gray-700">
            <strong>Company:</strong> {companyData.name || linkedinData.org || 'Not specified'}
          </p>
          <p className="text-gray-700">
            <strong>Location:</strong> {linkedinData.location?.text || 'Not specified'}
          </p>
          {linkedinData.summary && (
            <p className="text-gray-700 mt-2">
              <strong>Summary:</strong> {linkedinData.summary}
            </p>
          )}
        </div>

        <div className="mt-6 flex justify-center space-x-4">
          <button
            onClick={onConfirm}
            className="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded"
          >
            Yes, that's me
          </button>
          <button
            onClick={onReject}
            className="bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          >
            No, that's not me
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProfileCard; 