import { Settings } from "lucide-react";
import { moduleRegistry } from "../modules/registry";

export function WorkbenchSidebar() {
  const pathname = window.location.pathname;

  return (
    <aside className="sidebar" aria-label="Workbench navigation">
      <div className="brand-mark">
        <span className="brand-dot" aria-hidden="true" />
        <span>Personal Workbench</span>
      </div>
      <div className="sidebar-label">Modules</div>
      <nav className="module-nav">
        {moduleRegistry.map((module) => {
          const Icon = module.icon;
          const active = pathname === module.path
            || pathname.startsWith(`${module.path}/`)
            || (module.id === "literature" && pathname === "/");
          return (
            <a className={`module-link${active ? " active" : ""}`} href={module.path} key={module.id}>
              <Icon size={17} strokeWidth={1.8} />
              <span>{module.label}</span>
            </a>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <button className="icon-button" type="button" title="Settings" aria-label="Settings">
          <Settings size={17} strokeWidth={1.8} />
        </button>
        <span>v0.1 foundation</span>
      </div>
    </aside>
  );
}
