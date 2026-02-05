import React, { useState, useMemo } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useProjectStore } from '../../store/projectStore';
import type { ToolReference, ToolDefinition } from '../../../shared/types';

interface ToolPickerProps {
  onSelect: (tool: ToolReference) => void;
  onClose: () => void;
  existingTools: ToolReference[];
}

export const ToolPicker: React.FC<ToolPickerProps> = ({
  onSelect,
  onClose,
  existingTools,
}) => {
  const { tools, toolsLoading } = useProjectStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedServer, setSelectedServer] = useState<string | null>(null);

  // Get unique servers
  const servers = useMemo(() => {
    const serverSet = new Set(tools.map((t) => t.server));
    return Array.from(serverSet).sort();
  }, [tools]);

  // Filter tools
  const filteredTools = useMemo(() => {
    let filtered = tools;

    if (selectedServer) {
      filtered = filtered.filter((t) => t.server === selectedServer);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (t) =>
          t.name.toLowerCase().includes(query) ||
          t.description?.toLowerCase().includes(query)
      );
    }

    return filtered;
  }, [tools, selectedServer, searchQuery]);

  // Group tools by server
  const groupedTools = useMemo(() => {
    const groups: Record<string, ToolDefinition[]> = {};
    for (const tool of filteredTools) {
      if (!groups[tool.server]) {
        groups[tool.server] = [];
      }
      groups[tool.server].push(tool);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredTools]);

  const isToolSelected = (tool: ToolDefinition) => {
    return existingTools.some(
      (t) => t.server === tool.server && t.name === tool.name
    );
  };

  const handleSelectTool = (tool: ToolDefinition) => {
    onSelect({
      name: tool.name,
      server: tool.server,
      required: true,
    });
  };

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
          <div className="px-6 py-4 border-b border-gray-200">
            <Dialog.Title className="text-lg font-semibold text-gray-900">
              Add Tool
            </Dialog.Title>
            <p className="text-sm text-gray-500 mt-1">
              Select a tool from the catalog to add to this skill
            </p>
          </div>

          {/* Search and filter */}
          <div className="px-6 py-3 border-b border-gray-200 flex gap-3">
            <input
              type="text"
              placeholder="Search tools..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="form-input flex-1"
              autoFocus
            />
            <select
              value={selectedServer || ''}
              onChange={(e) => setSelectedServer(e.target.value || null)}
              className="form-input w-48"
            >
              <option value="">All servers</option>
              {servers.map((server) => (
                <option key={server} value={server}>
                  {server}
                </option>
              ))}
            </select>
          </div>

          {/* Tools list */}
          <div className="flex-1 overflow-y-auto p-4">
            {toolsLoading ? (
              <div className="text-center py-8 text-gray-500">Loading tools...</div>
            ) : filteredTools.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                {searchQuery || selectedServer
                  ? 'No tools match your filters'
                  : 'No tools available'}
              </div>
            ) : (
              <div className="space-y-4">
                {groupedTools.map(([server, serverTools]) => (
                  <div key={server}>
                    <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                      {server}
                    </h4>
                    <div className="space-y-1">
                      {serverTools.map((tool) => {
                        const selected = isToolSelected(tool);
                        return (
                          <button
                            key={`${tool.server}:${tool.name}`}
                            onClick={() => !selected && handleSelectTool(tool)}
                            disabled={selected}
                            className={`w-full text-left px-3 py-2 rounded-lg border transition-colors ${
                              selected
                                ? 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
                                : 'bg-white border-gray-200 hover:bg-dcf-50 hover:border-dcf-300'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{tool.name}</span>
                              {selected && (
                                <span className="text-xs bg-gray-200 px-2 py-0.5 rounded">
                                  Added
                                </span>
                              )}
                            </div>
                            {tool.description && (
                              <p className="text-sm text-gray-500 mt-0.5 line-clamp-2">
                                {tool.description}
                              </p>
                            )}
                            {tool.parameters && Object.keys(tool.parameters).length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-1">
                                {Object.keys(tool.parameters)
                                  .slice(0, 5)
                                  .map((param) => (
                                    <span
                                      key={param}
                                      className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded"
                                    >
                                      {param}
                                    </span>
                                  ))}
                                {Object.keys(tool.parameters).length > 5 && (
                                  <span className="text-[10px] text-gray-400">
                                    +{Object.keys(tool.parameters).length - 5} more
                                  </span>
                                )}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
            <Dialog.Close asChild>
              <button className="btn btn-secondary">Close</button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
