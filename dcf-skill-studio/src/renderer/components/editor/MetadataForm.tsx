import React from 'react';
import type { SkillDefinition } from '../../../shared/types';

interface MetadataFormProps {
  skill: SkillDefinition;
  onChange: (updates: Partial<SkillDefinition>) => void;
}

export const MetadataForm: React.FC<MetadataFormProps> = ({ skill, onChange }) => {
  const [newTag, setNewTag] = React.useState('');

  const handleMetadataChange = (
    field: keyof SkillDefinition['metadata'],
    value: string | string[]
  ) => {
    // Create full metadata object with updates
    const updatedMetadata = { ...skill.metadata, [field]: value };

    // Auto-update manifestId when name or version changes
    if (field === 'name' || field === 'version') {
      const name = field === 'name' ? (value as string) : skill.metadata.name;
      const version = field === 'version' ? (value as string) : skill.metadata.version;
      updatedMetadata.manifestId = `skill.${name}@${version}`;
    }

    onChange({ metadata: updatedMetadata });
  };

  const handleAddTag = () => {
    if (newTag.trim() && !skill.metadata.tags.includes(newTag.trim())) {
      handleMetadataChange('tags', [...skill.metadata.tags, newTag.trim()]);
      setNewTag('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    handleMetadataChange(
      'tags',
      skill.metadata.tags.filter((t) => t !== tag)
    );
  };

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-gray-900">Metadata</h3>

      <div className="grid grid-cols-2 gap-4">
        <div className="form-group">
          <label className="form-label">Name</label>
          <input
            type="text"
            value={skill.metadata.name}
            onChange={(e) => handleMetadataChange('name', e.target.value)}
            placeholder="category.skill-name"
            className="form-input"
          />
          <p className="text-xs text-gray-500 mt-1">
            Format: category.name (e.g., research.web)
          </p>
        </div>

        <div className="form-group">
          <label className="form-label">Version</label>
          <input
            type="text"
            value={skill.metadata.version}
            onChange={(e) => handleMetadataChange('version', e.target.value)}
            placeholder="0.1.0"
            className="form-input"
          />
          <p className="text-xs text-gray-500 mt-1">Semantic versioning (major.minor.patch)</p>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Manifest ID</label>
        <input
          type="text"
          value={skill.metadata.manifestId}
          readOnly
          className="form-input bg-gray-50 text-gray-600"
        />
        <p className="text-xs text-gray-500 mt-1">
          Auto-generated from name and version
        </p>
      </div>

      <div className="form-group">
        <label className="form-label">Description</label>
        <textarea
          value={skill.metadata.description}
          onChange={(e) => handleMetadataChange('description', e.target.value)}
          placeholder="Brief description of what this skill does..."
          rows={2}
          className="form-textarea"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Tags</label>
        <div className="flex flex-wrap gap-2 mb-2">
          {skill.metadata.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-1 bg-dcf-100 text-dcf-800 rounded text-sm"
            >
              {tag}
              <button
                onClick={() => handleRemoveTag(tag)}
                className="text-dcf-600 hover:text-dcf-800"
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
            placeholder="Add tag..."
            className="form-input flex-1"
          />
          <button
            onClick={handleAddTag}
            disabled={!newTag.trim()}
            className="btn btn-secondary disabled:opacity-50"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
};
