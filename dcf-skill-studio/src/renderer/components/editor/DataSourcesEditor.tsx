import React, { useState } from 'react';
import type { SkillDefinition, DataSource } from '../../../shared/types';

interface DataSourcesEditorProps {
  skill: SkillDefinition;
  onChange: (updates: Partial<SkillDefinition>) => void;
}

export const DataSourcesEditor: React.FC<DataSourcesEditorProps> = ({ skill, onChange }) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newDataSource, setNewDataSource] = useState<DataSource>({
    type: 'file',
    path: '',
  });

  const handleAdd = () => {
    if (isValidDataSource(newDataSource)) {
      onChange({ dataSources: [...skill.dataSources, newDataSource] });
      setNewDataSource({ type: 'file', path: '' });
      setShowAddForm(false);
    }
  };

  const handleRemove = (index: number) => {
    const newSources = [...skill.dataSources];
    newSources.splice(index, 1);
    onChange({ dataSources: newSources });
  };

  const isValidDataSource = (ds: DataSource): boolean => {
    switch (ds.type) {
      case 'file':
        return !!ds.path;
      case 'url':
        return !!ds.url;
      case 'memory_block':
        return !!ds.blockLabel;
      default:
        return false;
    }
  };

  const getDataSourceIcon = (type: DataSource['type']) => {
    switch (type) {
      case 'file':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        );
      case 'url':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
            />
          </svg>
        );
      case 'memory_block':
        return (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
            />
          </svg>
        );
    }
  };

  const getDataSourceValue = (ds: DataSource): string => {
    switch (ds.type) {
      case 'file':
        return ds.path || '';
      case 'url':
        return ds.url || '';
      case 'memory_block':
        return ds.blockLabel || '';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-gray-900">Data Sources</h3>
          <p className="text-sm text-gray-500">
            Configure external data sources this skill can access
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="btn btn-primary text-sm"
        >
          Add Data Source
        </button>
      </div>

      {skill.dataSources.length === 0 && !showAddForm ? (
        <div className="bg-gray-50 rounded-lg p-8 text-center">
          <svg
            className="w-12 h-12 mx-auto text-gray-400 mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
            />
          </svg>
          <p className="text-gray-600 mb-2">No data sources configured</p>
          <p className="text-sm text-gray-500">
            Add files, URLs, or memory blocks that this skill needs access to
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {skill.dataSources.map((ds, index) => (
            <div
              key={index}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-lg p-3"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-gray-100 rounded-md flex items-center justify-center text-gray-500">
                  {getDataSourceIcon(ds.type)}
                </div>
                <div>
                  <div className="font-medium text-gray-900 capitalize">{ds.type.replace('_', ' ')}</div>
                  <div className="text-sm text-gray-500 font-mono">
                    {getDataSourceValue(ds)}
                  </div>
                </div>
              </div>

              <button
                onClick={() => handleRemove(index)}
                className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                title="Remove data source"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add form */}
      {showAddForm && (
        <div className="bg-gray-50 rounded-lg p-4 space-y-4">
          <h4 className="font-medium text-gray-900">Add Data Source</h4>

          <div className="form-group">
            <label className="form-label">Type</label>
            <select
              value={newDataSource.type}
              onChange={(e) =>
                setNewDataSource({
                  type: e.target.value as DataSource['type'],
                  path: '',
                  url: '',
                  blockLabel: '',
                })
              }
              className="form-input"
            >
              <option value="file">File</option>
              <option value="url">URL</option>
              <option value="memory_block">Memory Block</option>
            </select>
          </div>

          {newDataSource.type === 'file' && (
            <div className="form-group">
              <label className="form-label">File Path</label>
              <input
                type="text"
                value={newDataSource.path || ''}
                onChange={(e) =>
                  setNewDataSource({ ...newDataSource, path: e.target.value })
                }
                placeholder="/path/to/file.txt"
                className="form-input font-mono"
              />
            </div>
          )}

          {newDataSource.type === 'url' && (
            <div className="form-group">
              <label className="form-label">URL</label>
              <input
                type="text"
                value={newDataSource.url || ''}
                onChange={(e) =>
                  setNewDataSource({ ...newDataSource, url: e.target.value })
                }
                placeholder="https://example.com/data"
                className="form-input font-mono"
              />
            </div>
          )}

          {newDataSource.type === 'memory_block' && (
            <div className="form-group">
              <label className="form-label">Block Label</label>
              <input
                type="text"
                value={newDataSource.blockLabel || ''}
                onChange={(e) =>
                  setNewDataSource({ ...newDataSource, blockLabel: e.target.value })
                }
                placeholder="session_context"
                className="form-input"
              />
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowAddForm(false)}
              className="btn btn-secondary text-sm"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={!isValidDataSource(newDataSource)}
              className="btn btn-primary text-sm disabled:opacity-50"
            >
              Add
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
