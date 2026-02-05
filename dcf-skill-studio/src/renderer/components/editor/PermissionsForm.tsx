import React from 'react';
import type { SkillDefinition } from '../../../shared/types';

interface PermissionsFormProps {
  skill: SkillDefinition;
  onChange: (updates: Partial<SkillDefinition>) => void;
}

export const PermissionsForm: React.FC<PermissionsFormProps> = ({ skill, onChange }) => {
  const handlePermissionChange = (
    field: keyof SkillDefinition['permissions'],
    value: boolean | string
  ) => {
    onChange({ permissions: { ...skill.permissions, [field]: value } });
  };

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-gray-900">Permissions</h3>

      <div className="bg-gray-50 rounded-lg p-4 space-y-4">
        <p className="text-sm text-gray-600">
          Configure the security permissions required by this skill. These settings
          affect governance and auditing.
        </p>

        {/* Egress */}
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id="egress"
            checked={skill.permissions.egress}
            onChange={(e) => handlePermissionChange('egress', e.target.checked)}
            className="mt-1 h-4 w-4 text-dcf-600 border-gray-300 rounded focus:ring-dcf-500"
          />
          <div>
            <label htmlFor="egress" className="font-medium text-gray-900 cursor-pointer">
              Network Egress
            </label>
            <p className="text-sm text-gray-500">
              Allow outbound network requests (HTTP, WebSocket, etc.)
            </p>
          </div>
        </div>

        {/* Secrets */}
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id="secrets"
            checked={skill.permissions.secrets}
            onChange={(e) => handlePermissionChange('secrets', e.target.checked)}
            className="mt-1 h-4 w-4 text-dcf-600 border-gray-300 rounded focus:ring-dcf-500"
          />
          <div>
            <label htmlFor="secrets" className="font-medium text-gray-900 cursor-pointer">
              Secret Access
            </label>
            <p className="text-sm text-gray-500">
              Allow access to secrets and credentials (API keys, tokens, etc.)
            </p>
          </div>
        </div>

        {/* Risk Level */}
        <div className="pt-2">
          <label className="font-medium text-gray-900 block mb-2">Risk Level</label>
          <div className="flex gap-4">
            {(['low', 'medium', 'high'] as const).map((level) => (
              <label
                key={level}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg border cursor-pointer transition-colors ${
                  skill.permissions.riskLevel === level
                    ? level === 'low'
                      ? 'bg-green-50 border-green-300 text-green-800'
                      : level === 'medium'
                        ? 'bg-yellow-50 border-yellow-300 text-yellow-800'
                        : 'bg-red-50 border-red-300 text-red-800'
                    : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="riskLevel"
                  value={level}
                  checked={skill.permissions.riskLevel === level}
                  onChange={(e) => handlePermissionChange('riskLevel', e.target.value)}
                  className="sr-only"
                />
                <span
                  className={`w-2 h-2 rounded-full ${
                    level === 'low'
                      ? 'bg-green-500'
                      : level === 'medium'
                        ? 'bg-yellow-500'
                        : 'bg-red-500'
                  }`}
                />
                <span className="capitalize font-medium">{level}</span>
              </label>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-2">
            {skill.permissions.riskLevel === 'low' &&
              'Low risk: Read-only operations, no external access'}
            {skill.permissions.riskLevel === 'medium' &&
              'Medium risk: May modify data or access external services'}
            {skill.permissions.riskLevel === 'high' &&
              'High risk: Can perform destructive operations or access sensitive data'}
          </p>
        </div>
      </div>

      {/* Permission summary */}
      <div className="bg-blue-50 rounded-lg p-4">
        <h4 className="font-medium text-blue-900 mb-2">Permission Summary</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li className="flex items-center gap-2">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                skill.permissions.egress ? 'bg-blue-500' : 'bg-gray-400'
              }`}
            />
            Network: {skill.permissions.egress ? 'Enabled' : 'Disabled'}
          </li>
          <li className="flex items-center gap-2">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                skill.permissions.secrets ? 'bg-blue-500' : 'bg-gray-400'
              }`}
            />
            Secrets: {skill.permissions.secrets ? 'Enabled' : 'Disabled'}
          </li>
          <li className="flex items-center gap-2">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                skill.permissions.riskLevel === 'low'
                  ? 'bg-green-500'
                  : skill.permissions.riskLevel === 'medium'
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
              }`}
            />
            Risk: {skill.permissions.riskLevel.charAt(0).toUpperCase() +
              skill.permissions.riskLevel.slice(1)}
          </li>
        </ul>
      </div>
    </div>
  );
};
