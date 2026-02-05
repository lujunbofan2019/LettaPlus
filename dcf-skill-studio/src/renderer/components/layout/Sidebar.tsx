import React, { useState, useMemo } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { SkillCard } from '../skills/SkillCard';
import { NewSkillDialog } from '../skills/NewSkillDialog';

export const Sidebar: React.FC = () => {
  const { skills, skillsLoading, selectedSkillPath, selectSkill } = useProjectStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [showNewDialog, setShowNewDialog] = useState(false);

  // Group skills by category (first part of name)
  const groupedSkills = useMemo(() => {
    const filtered = skills.filter(
      (s) =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.skill.metadata.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.skill.metadata.tags.some((t) =>
          t.toLowerCase().includes(searchQuery.toLowerCase())
        )
    );

    const groups: Record<string, typeof skills> = {};
    for (const skill of filtered) {
      const parts = skill.name.split('.');
      const category = parts.length > 1 ? parts[0] : 'misc';
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(skill);
    }

    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [skills, searchQuery]);

  const errorCount = skills.filter((s) =>
    s.validationErrors.some((e) => e.severity === 'error')
  ).length;

  const warningCount = skills.filter(
    (s) =>
      !s.validationErrors.some((e) => e.severity === 'error') &&
      s.validationErrors.some((e) => e.severity === 'warning')
  ).length;

  return (
    <aside className="sidebar w-72 flex flex-col">
      <div className="sidebar-header flex items-center justify-between">
        <span>SKILLS</span>
        <div className="flex items-center gap-2 text-xs">
          {errorCount > 0 && (
            <span className="text-red-500" title={`${errorCount} with errors`}>
              {errorCount}
            </span>
          )}
          {warningCount > 0 && (
            <span className="text-yellow-500" title={`${warningCount} with warnings`}>
              {warningCount}
            </span>
          )}
          <span className="text-gray-400">{skills.length} total</span>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-gray-200">
        <input
          type="text"
          placeholder="Search skills..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-dcf-500"
        />
      </div>

      {/* Skills list */}
      <div className="flex-1 overflow-y-auto py-2">
        {skillsLoading ? (
          <div className="px-4 py-8 text-center text-gray-500 text-sm">
            Loading skills...
          </div>
        ) : groupedSkills.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500 text-sm">
            {searchQuery ? 'No skills match your search' : 'No skills found'}
          </div>
        ) : (
          groupedSkills.map(([category, categorySkills]) => (
            <div key={category} className="mb-2">
              <div className="px-4 py-1 text-xs font-medium text-gray-500 uppercase tracking-wider">
                {category}
              </div>
              <div className="space-y-0.5 px-2">
                {categorySkills.map((skill) => (
                  <SkillCard
                    key={skill.path}
                    skill={skill}
                    isSelected={skill.path === selectedSkillPath}
                    onClick={() => selectSkill(skill.path)}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* New skill button */}
      <div className="p-3 border-t border-gray-200">
        <button
          onClick={() => setShowNewDialog(true)}
          className="w-full btn btn-secondary text-sm flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          New Skill
        </button>
      </div>

      {showNewDialog && <NewSkillDialog onClose={() => setShowNewDialog(false)} />}
    </aside>
  );
};
