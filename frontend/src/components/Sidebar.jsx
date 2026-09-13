const fileTypeLabels = {
  pdf: "PDF",
  pptx: "PPT",
  txt: "TXT",
  md: "MD",
  csv: "CSV",
};

export function Sidebar({ documents, selectedDocumentId, onSelectDocument, loadingDocuments, onDeleteDocument, theme, onToggleTheme, userName, onUserNameChange, activeNav, onNavigate, collapsed, onToggleSidebar, onOpenSettings }) {
  const navItems = [
    ["Home", "⌂", false],
    ["Team", "♙", false],
    ["Design System", "◈", false],
    ["Documentation", "", true],
    ["Components", "", true],
    ["Tokens", "", true],
    ["Marketing", "▥", false],
    ["Q3_Assets", "", true],
    ["Urgent", "", false],
    ["Reviewed", "", false],
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">✦</div>
        <div>
          {onUserNameChange ? (
            <input className="user-name-input" value={userName} onChange={(event) => onUserNameChange(event.target.value)} aria-label="Your name" />
          ) : <h1>{userName}</h1>}
          <p className="user-role">Personal workspace</p>
        </div>
        <button className="theme-toggle" type="button" onClick={onToggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      <nav className="sidebar-nav">
        <p className="nav-label">Workspace</p>
        <button className={`nav-item ${activeNav === "Home" ? "is-active" : ""}`} type="button" onClick={() => onNavigate("Home")}><span>⌂</span> Home</button>
        <button className={`nav-item ${activeNav === "Dashboard" ? "is-active" : ""}`} type="button" onClick={() => onNavigate("Dashboard")}><span>▦</span> Dashboard</button>
        <button className={`nav-item ${activeNav === "Analysis" ? "is-active" : ""}`} type="button" onClick={() => onNavigate("Analysis")}><span>◒</span> Analysis</button>
        <button className={`nav-item ${activeNav === "Team" ? "is-active" : ""}`} type="button" onClick={() => onNavigate("Team")}><span>♙</span> Team</button>
        <button className={`nav-item ${activeNav === "Settings" ? "is-active" : ""}`} type="button" onClick={onOpenSettings}><span>⚙</span> Settings</button>
        <p className="nav-label">Projects</p>
        {navItems.slice(2, 8).filter(([label]) => label !== "Design System").map(([label, icon, nested]) => <button key={label} className={`nav-item ${nested ? "nested" : ""} ${activeNav === label ? "is-active" : ""}`} type="button" onClick={() => onNavigate(label)}><span>{icon}</span> {label}</button>)}
        <p className="nav-label">Tags</p>
        {navItems.slice(8).map(([label]) => <button key={label} className="tag-item" type="button" onClick={() => onNavigate(label)}><i className={`tag-dot ${label === "Urgent" ? "urgent" : ""}`} /> {label}</button>)}
      </nav>
      <button className="settings-button" type="button" onClick={onToggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
        <span>⚙</span> Settings <small>{theme === "dark" ? "Dark" : "Light"}</small>
      </button>
    </aside>
  );
}
