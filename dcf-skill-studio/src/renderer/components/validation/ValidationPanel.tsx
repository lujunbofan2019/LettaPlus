import React from 'react';
import type { ValidationError } from '../../../shared/types';

interface ValidationPanelProps {
  errors: ValidationError[];
}

export const ValidationPanel: React.FC<ValidationPanelProps> = ({ errors }) => {
  const errorList = errors.filter((e) => e.severity === 'error');
  const warningList = errors.filter((e) => e.severity === 'warning');

  if (errors.length === 0) {
    return (
      <aside className="w-72 border-l border-gray-200 bg-gray-50 p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Validation</h3>
        <div className="flex items-center gap-2 text-green-600">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-sm font-medium">No issues found</span>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          This skill passes all validation checks
        </p>
      </aside>
    );
  }

  return (
    <aside className="w-72 border-l border-gray-200 bg-gray-50 overflow-y-auto">
      <div className="p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Validation</h3>

        {/* Summary */}
        <div className="flex gap-4 mb-4">
          {errorList.length > 0 && (
            <div className="flex items-center gap-1.5 text-red-600">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-sm">
                {errorList.length} error{errorList.length !== 1 ? 's' : ''}
              </span>
            </div>
          )}
          {warningList.length > 0 && (
            <div className="flex items-center gap-1.5 text-yellow-600">
              <span className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-sm">
                {warningList.length} warning{warningList.length !== 1 ? 's' : ''}
              </span>
            </div>
          )}
        </div>

        {/* Errors */}
        {errorList.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-medium text-red-700 uppercase tracking-wider mb-2">
              Errors
            </h4>
            <div className="space-y-2">
              {errorList.map((error, index) => (
                <div
                  key={index}
                  className="bg-red-50 border border-red-200 rounded-md p-2"
                >
                  <code className="text-xs text-red-600 block mb-1">
                    {error.path}
                  </code>
                  <p className="text-sm text-red-800">{error.message}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Warnings */}
        {warningList.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-yellow-700 uppercase tracking-wider mb-2">
              Warnings
            </h4>
            <div className="space-y-2">
              {warningList.map((warning, index) => (
                <div
                  key={index}
                  className="bg-yellow-50 border border-yellow-200 rounded-md p-2"
                >
                  <code className="text-xs text-yellow-600 block mb-1">
                    {warning.path}
                  </code>
                  <p className="text-sm text-yellow-800">{warning.message}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
