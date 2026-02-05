import React, { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useProjectStore } from '../../store/projectStore';

interface NewSkillDialogProps {
  onClose: () => void;
}

export const NewSkillDialog: React.FC<NewSkillDialogProps> = ({ onClose }) => {
  const { createSkill } = useProjectStore();
  const [category, setCategory] = useState('');
  const [name, setName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fullName = category ? `${category}.${name}` : name;
  const isValid = name.length > 0 && /^[a-z][a-z0-9-]*$/.test(name) &&
    (!category || /^[a-z][a-z0-9-]*$/.test(category));

  const handleCreate = async () => {
    if (!isValid) return;

    setIsCreating(true);
    setError(null);

    try {
      await createSkill(fullName);
      onClose();
    } catch (err) {
      setError(`${err}`);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 animate-fade-in" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl w-full max-w-md p-6 animate-slide-up">
          <Dialog.Title className="text-lg font-semibold text-gray-900 mb-4">
            Create New Skill
          </Dialog.Title>

          <div className="space-y-4">
            <div className="form-group">
              <label className="form-label">Category (optional)</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value.toLowerCase())}
                placeholder="e.g., research, analyze, write"
                className="form-input"
              />
              <p className="text-xs text-gray-500 mt-1">
                Lowercase letters, numbers, and hyphens only
              </p>
            </div>

            <div className="form-group">
              <label className="form-label">Skill Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
                placeholder="e.g., web, news, company"
                className="form-input"
                autoFocus
              />
              <p className="text-xs text-gray-500 mt-1">
                Lowercase letters, numbers, and hyphens only
              </p>
            </div>

            {fullName && (
              <div className="bg-gray-50 rounded-md p-3">
                <p className="text-xs text-gray-500 mb-1">Full skill name:</p>
                <code className="text-sm text-dcf-600">{fullName}</code>
              </div>
            )}

            {error && (
              <div className="bg-red-50 text-red-700 rounded-md p-3 text-sm">
                {error}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <Dialog.Close asChild>
              <button className="btn btn-secondary">Cancel</button>
            </Dialog.Close>
            <button
              onClick={handleCreate}
              disabled={!isValid || isCreating}
              className="btn btn-primary disabled:opacity-50"
            >
              {isCreating ? 'Creating...' : 'Create Skill'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
