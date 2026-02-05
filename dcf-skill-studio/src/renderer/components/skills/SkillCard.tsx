import React from 'react';
import type { SkillFile } from '../../../shared/types';
import clsx from 'clsx';

interface SkillCardProps {
  skill: SkillFile;
  isSelected: boolean;
  onClick: () => void;
}

export const SkillCard: React.FC<SkillCardProps> = ({ skill, isSelected, onClick }) => {
  const hasErrors = skill.validationErrors.some((e) => e.severity === 'error');
  const hasWarnings = skill.validationErrors.some((e) => e.severity === 'warning');

  // Get skill name without category prefix
  const displayName = skill.name.includes('.') ? skill.name.split('.')[1] : skill.name;

  return (
    <div
      onClick={onClick}
      className={clsx('skill-card', {
        active: isSelected,
        error: hasErrors,
        warning: !hasErrors && hasWarnings,
      })}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          {/* Status indicator */}
          {hasErrors ? (
            <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
          ) : hasWarnings ? (
            <span className="w-2 h-2 rounded-full bg-yellow-500 flex-shrink-0" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
          )}

          <span className="text-sm font-medium truncate">{displayName}</span>
        </div>

        <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
          {skill.skill.metadata.version}
        </span>
      </div>

      {skill.skill.metadata.description && (
        <p className="text-xs text-gray-500 mt-1 truncate pl-4">
          {skill.skill.metadata.description}
        </p>
      )}

      {skill.skill.metadata.tags.length > 0 && (
        <div className="flex gap-1 mt-1 pl-4 flex-wrap">
          {skill.skill.metadata.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="inline-block px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-600 rounded"
            >
              {tag}
            </span>
          ))}
          {skill.skill.metadata.tags.length > 3 && (
            <span className="text-[10px] text-gray-400">
              +{skill.skill.metadata.tags.length - 3}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
