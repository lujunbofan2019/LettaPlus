import React from 'react';
import { useProjectStore } from '../../store/projectStore';

export const Header: React.FC = () => {
  const { project, openProject, isGenerating, generateAll, pythonAvailable } =
    useProjectStore();

  return (
    <header className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
          <svg
            className="w-6 h-6 text-dcf-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          DCF Skill Studio
        </h1>
        {project && (
          <span className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
            {project.path}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {project && (
          <button
            onClick={generateAll}
            disabled={isGenerating || !pythonAvailable}
            className="btn btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            title={
              !pythonAvailable
                ? 'Python 3.9+ required for generation'
                : 'Generate all manifests'
            }
          >
            {isGenerating ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4 inline"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Generating...
              </>
            ) : (
              'Generate All'
            )}
          </button>
        )}

        <button onClick={openProject} className="btn btn-secondary text-sm">
          {project ? 'Switch Project' : 'Open Project'}
        </button>
      </div>
    </header>
  );
};
