import React, { useState, useCallback, useEffect } from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import type { SkillFile, SkillDefinition } from '../../../shared/types';
import { useProjectStore } from '../../store/projectStore';
import { MetadataForm } from '../editor/MetadataForm';
import { PermissionsForm } from '../editor/PermissionsForm';
import { DirectivesEditor } from '../editor/DirectivesEditor';
import { ToolsEditor } from '../editor/ToolsEditor';
import { DataSourcesEditor } from '../editor/DataSourcesEditor';
import { ValidationPanel } from '../validation/ValidationPanel';

interface SkillEditorProps {
  skill: SkillFile;
}

export const SkillEditor: React.FC<SkillEditorProps> = ({ skill: skillFile }) => {
  const { updateSkill, validateSkill, deleteSkill, selectSkill } = useProjectStore();
  const [localSkill, setLocalSkill] = useState<SkillDefinition>(skillFile.skill);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [validationErrors, setValidationErrors] = useState(skillFile.validationErrors);
  const [activeTab, setActiveTab] = useState('metadata');

  // Update local state when a different skill is selected
  useEffect(() => {
    setLocalSkill(skillFile.skill);
    setIsDirty(false);
    setValidationErrors(skillFile.validationErrors);
  }, [skillFile.path]);

  // Validate on changes
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (isDirty) {
        const errors = await validateSkill(localSkill);
        setValidationErrors(errors);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localSkill, isDirty, validateSkill]);

  const handleChange = useCallback((updates: Partial<SkillDefinition>) => {
    setLocalSkill((prev) => {
      const updated = { ...prev, ...updates };
      // Deep merge for nested objects
      if (updates.metadata) {
        updated.metadata = { ...prev.metadata, ...updates.metadata };
      }
      if (updates.permissions) {
        updated.permissions = { ...prev.permissions, ...updates.permissions };
      }
      return updated;
    });
    setIsDirty(true);
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await updateSkill(skillFile.path, localSkill);
      setIsDirty(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (
      window.confirm(
        `Are you sure you want to delete "${localSkill.metadata.name}"? This cannot be undone.`
      )
    ) {
      await deleteSkill(skillFile.path);
      selectSkill(null);
    }
  };

  const hasErrors = validationErrors.some((e) => e.severity === 'error');

  return (
    <div className="editor-panel">
      {/* Header */}
      <div className="editor-header">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-gray-900">
            {localSkill.metadata.name || 'Untitled Skill'}
          </h2>
          {isDirty && (
            <span className="text-xs text-yellow-600 bg-yellow-100 px-2 py-0.5 rounded">
              Unsaved
            </span>
          )}
          {hasErrors && (
            <span className="text-xs text-red-600 bg-red-100 px-2 py-0.5 rounded">
              Has errors
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDelete}
            className="btn btn-secondary text-sm text-red-600 hover:bg-red-50"
          >
            Delete
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving}
            className="btn btn-primary text-sm disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs.Root
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex-1 flex flex-col overflow-hidden"
      >
        <Tabs.List className="border-b border-gray-200 px-6">
          <div className="flex gap-6">
            <Tabs.Trigger
              value="metadata"
              className="py-3 text-sm font-medium border-b-2 -mb-px transition-colors data-[state=active]:border-dcf-500 data-[state=active]:text-dcf-600 border-transparent text-gray-500 hover:text-gray-700"
            >
              Metadata
            </Tabs.Trigger>
            <Tabs.Trigger
              value="permissions"
              className="py-3 text-sm font-medium border-b-2 -mb-px transition-colors data-[state=active]:border-dcf-500 data-[state=active]:text-dcf-600 border-transparent text-gray-500 hover:text-gray-700"
            >
              Permissions
            </Tabs.Trigger>
            <Tabs.Trigger
              value="tools"
              className="py-3 text-sm font-medium border-b-2 -mb-px transition-colors data-[state=active]:border-dcf-500 data-[state=active]:text-dcf-600 border-transparent text-gray-500 hover:text-gray-700"
            >
              Tools
              {localSkill.tools.length > 0 && (
                <span className="ml-1.5 text-xs bg-gray-200 px-1.5 rounded-full">
                  {localSkill.tools.length}
                </span>
              )}
            </Tabs.Trigger>
            <Tabs.Trigger
              value="datasources"
              className="py-3 text-sm font-medium border-b-2 -mb-px transition-colors data-[state=active]:border-dcf-500 data-[state=active]:text-dcf-600 border-transparent text-gray-500 hover:text-gray-700"
            >
              Data Sources
              {localSkill.dataSources.length > 0 && (
                <span className="ml-1.5 text-xs bg-gray-200 px-1.5 rounded-full">
                  {localSkill.dataSources.length}
                </span>
              )}
            </Tabs.Trigger>
          </div>
        </Tabs.List>

        <div className="flex-1 flex overflow-hidden">
          {/* Main content */}
          <div className="flex-1 overflow-auto">
            <Tabs.Content value="metadata" className="p-6">
              <MetadataForm skill={localSkill} onChange={handleChange} />
              <div className="mt-8">
                <DirectivesEditor skill={localSkill} onChange={handleChange} />
              </div>
            </Tabs.Content>

            <Tabs.Content value="permissions" className="p-6">
              <PermissionsForm skill={localSkill} onChange={handleChange} />
            </Tabs.Content>

            <Tabs.Content value="tools" className="p-6">
              <ToolsEditor skill={localSkill} onChange={handleChange} />
            </Tabs.Content>

            <Tabs.Content value="datasources" className="p-6">
              <DataSourcesEditor skill={localSkill} onChange={handleChange} />
            </Tabs.Content>
          </div>

          {/* Validation panel */}
          <ValidationPanel errors={validationErrors} />
        </div>
      </Tabs.Root>
    </div>
  );
};
