import type { ReactNode } from "react";
import { WorkbenchSidebar } from "./WorkbenchSidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="workbench-shell">
      <WorkbenchSidebar />
      <main className="main-content">{children}</main>
    </div>
  );
}
