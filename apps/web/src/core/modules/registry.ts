import { BookOpen, Newspaper } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type WorkbenchModule = {
  id: string;
  label: string;
  description: string;
  path: string;
  icon: LucideIcon;
};

export const moduleRegistry: WorkbenchModule[] = [
  {
    id: "literature",
    label: "Literature",
    description: "文献库",
    path: "/literature",
    icon: BookOpen,
  },
  {
    id: "news",
    label: "News",
    description: "外部信息",
    path: "/news",
    icon: Newspaper,
  },
];
