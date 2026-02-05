import React, { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import type { SkillDefinition } from '../../../shared/types';

interface DirectivesEditorProps {
  skill: SkillDefinition;
  onChange: (updates: Partial<SkillDefinition>) => void;
}

export const DirectivesEditor: React.FC<DirectivesEditorProps> = ({ skill, onChange }) => {
  const [showPreview, setShowPreview] = useState(false);

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      onChange({ directives: value || '' });
    },
    [onChange]
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-gray-900">Directives</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="text-sm text-dcf-600 hover:text-dcf-700"
          >
            {showPreview ? 'Edit' : 'Preview'}
          </button>
        </div>
      </div>

      <p className="text-sm text-gray-500">
        Instructions that guide the agent when using this skill. Supports Markdown formatting.
      </p>

      {showPreview ? (
        <div className="prose prose-sm max-w-none bg-white border border-gray-200 rounded-lg p-4 min-h-[300px]">
          <pre className="whitespace-pre-wrap font-sans text-sm">{skill.directives}</pre>
        </div>
      ) : (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <Editor
            height="300px"
            defaultLanguage="markdown"
            value={skill.directives}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: false },
              lineNumbers: 'off',
              wordWrap: 'on',
              fontSize: 13,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              scrollBeyondLastLine: false,
              padding: { top: 12, bottom: 12 },
              renderLineHighlight: 'none',
              overviewRulerBorder: false,
              hideCursorInOverviewRuler: true,
              folding: false,
              automaticLayout: true,
            }}
            theme="vs"
          />
        </div>
      )}

      <div className="bg-gray-50 rounded-lg p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Tips for writing directives:</h4>
        <ul className="text-xs text-gray-600 space-y-1 list-disc list-inside">
          <li>Be specific about what the skill should accomplish</li>
          <li>Include any constraints or limitations</li>
          <li>Describe expected inputs and outputs</li>
          <li>Mention which tools should be used and when</li>
        </ul>
      </div>
    </div>
  );
};
