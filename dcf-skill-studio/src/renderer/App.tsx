import React, { useEffect } from 'react';
import { useProjectStore } from './store/projectStore';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { StatusBar } from './components/layout/StatusBar';
import { SkillEditor } from './components/skills/SkillEditor';
import { WelcomeScreen } from './components/layout/WelcomeScreen';

const App: React.FC = () => {
  const { project, selectedSkillPath, skills, loadSkills, loadTools, checkPython } =
    useProjectStore();

  // Set up file watching listeners
  useEffect(() => {
    if (!project) return;

    const unsubChange = window.electronAPI.onSkillChanged((path) => {
      console.log('Skill changed:', path);
      loadSkills();
    });

    const unsubAdd = window.electronAPI.onSkillAdded((path) => {
      console.log('Skill added:', path);
      loadSkills();
    });

    const unsubRemove = window.electronAPI.onSkillRemoved((path) => {
      console.log('Skill removed:', path);
      loadSkills();
    });

    return () => {
      unsubChange();
      unsubAdd();
      unsubRemove();
    };
  }, [project, loadSkills]);

  // Load tools and check Python when project changes
  useEffect(() => {
    if (project) {
      loadTools();
      checkPython();
    }
  }, [project, loadTools, checkPython]);

  const selectedSkill = skills.find((s) => s.path === selectedSkillPath);

  return (
    <div className="h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex overflow-hidden">
        {project ? (
          <>
            <Sidebar />
            <main className="flex-1 flex flex-col overflow-hidden">
              {selectedSkill ? (
                <SkillEditor skill={selectedSkill} />
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-500">
                  <div className="text-center">
                    <p className="text-lg">Select a skill from the sidebar</p>
                    <p className="text-sm mt-1">or create a new one</p>
                  </div>
                </div>
              )}
            </main>
          </>
        ) : (
          <WelcomeScreen />
        )}
      </div>
      <StatusBar />
    </div>
  );
};

export default App;
