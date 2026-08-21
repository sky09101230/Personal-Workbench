import { BookOpen } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type WorkbenchModule = {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const moduleRegistry: WorkbenchModule[] = [
  {
    id: "literature",
    label: "Literature",
    description: "文献库",
    icon: BookOpen,
  },
];
