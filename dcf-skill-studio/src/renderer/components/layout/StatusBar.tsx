import React from 'react';
import { useProjectStore } from '../../store/projectStore';

export const StatusBar: React.FC = () => {
  const {
    project,
    skills,
    pythonAvailable,
    pythonVersion,
    pythonError,
    isGenerating,
    generationResult,
  } = useProjectStore();

  const validSkills = skills.filter(
    (s) => !s.validationErrors.some((e) => e.severity === 'error')
  ).length;

  return (
    <footer className="status-bar">
      <div className="flex items-center gap-4">
        {/* Generation status */}
        <span className="flex items-center gap-1.5">
          {isGenerating ? (
            <>
              <svg
                className="animate-spin h-3 w-3 text-dcf-600"
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
              <span>Generating...</span>
            </>
          ) : generationResult ? (
            generationResult.status === 'success' ? (
              <>
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>Generation complete</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-red-600">
                  Generation failed: {generationResult.error}
                </span>
              </>
            )
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-gray-400" />
              <span>Ready</span>
            </>
          )}
        </span>

        {/* Divider */}
        <span className="text-gray-300">|</span>

        {/* Validation status */}
        {project && (
          <span className="flex items-center gap-1.5">
            {validSkills === skills.length ? (
              <>
                <svg
                  className="w-3.5 h-3.5 text-green-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
                <span>{skills.length} skills valid</span>
              </>
            ) : (
              <>
                <svg
                  className="w-3.5 h-3.5 text-yellow-500"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
                <span>
                  {validSkills}/{skills.length} skills valid
                </span>
              </>
            )}
          </span>
        )}
      </div>

      {/* Right side - Python status */}
      <div className="flex items-center gap-2">
        {pythonAvailable ? (
          <span className="text-green-600 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            Python {pythonVersion}
          </span>
        ) : (
          <span className="text-red-600 flex items-center gap-1" title={pythonError || ''}>
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            Python not found
          </span>
        )}
      </div>
    </footer>
  );
};
