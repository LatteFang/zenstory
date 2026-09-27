import React, { createContext, useContext, useState, useCallback } from 'react';
import type { ReactNode } from 'react';

/** 单条消息最多显式选择的技能数（与后端 AgentRequest.selected_skill_ids 上限一致） */
export const MAX_SELECTED_SKILLS = 3;

export interface SelectedSkill {
  id: string;
  name: string;
}

export interface SkillTriggerContextType {
  /** 用户为下一条消息显式选择的技能（以 chip 形式显示在输入框上方） */
  selectedSkills: SelectedSkill[];
  /** 选择一个技能；已选或已达上限时忽略 */
  selectSkill: (skill: SelectedSkill) => void;
  /** 移除一个已选技能 */
  removeSkill: (skillId: string) => void;
  /** 清空已选技能（消息发送后调用） */
  clearSkills: () => void;
}

const SkillTriggerContext = createContext<SkillTriggerContextType | undefined>(undefined);

export const SkillTriggerProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [selectedSkills, setSelectedSkills] = useState<SelectedSkill[]>([]);

  const selectSkill = useCallback((skill: SelectedSkill) => {
    setSelectedSkills((prev) => {
      if (prev.some((s) => s.id === skill.id) || prev.length >= MAX_SELECTED_SKILLS) {
        return prev;
      }
      return [...prev, { id: skill.id, name: skill.name }];
    });
  }, []);

  const removeSkill = useCallback((skillId: string) => {
    setSelectedSkills((prev) => prev.filter((s) => s.id !== skillId));
  }, []);

  const clearSkills = useCallback(() => {
    setSelectedSkills([]);
  }, []);

  return (
    <SkillTriggerContext.Provider value={{ selectedSkills, selectSkill, removeSkill, clearSkills }}>
      {children}
    </SkillTriggerContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useSkillTrigger = (): SkillTriggerContextType => {
  const context = useContext(SkillTriggerContext);
  if (context === undefined) {
    throw new Error('useSkillTrigger must be used within a SkillTriggerProvider');
  }
  return context;
};
