export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <>
      <header className="topbar">
        <div>
          <p className="eyebrow">LOCAL TASK LEDGER</p>
          <h1>agtask dashboard</h1>
        </div>
        <div className="summary" id="summary">
          Loading tasks…
        </div>
      </header>

      <main>
        <nav id="view-tabs" className="view-tabs" aria-label="Task views" />
        <section className="toolbar" aria-label="Dashboard controls">
          <label className="search">
            Task search
            <input
              id="search"
              type="search"
              autoComplete="off"
              placeholder="Search titles or SHAs"
            />
          </label>

          <div className="toolbar-actions">
            <label>
              Sort by
              <select id="sort">
                <option value="updated">Updated</option>
                <option value="created">Created</option>
                <option value="closed">Closed</option>
              </select>
            </label>
            <label>
              Direction
              <select id="direction">
                <option value="desc">Newest first</option>
                <option value="asc">Oldest first</option>
              </select>
            </label>
            <button id="refresh" className="secondary-button" type="button">
              Refresh
            </button>

            <div className="filter-launcher">
              <button
                id="filter-trigger"
                className="filter-trigger"
                type="button"
                aria-haspopup="dialog"
                aria-controls="filter-menu"
                aria-expanded="false"
              >
                <span aria-hidden="true">＋</span> Add filter
              </button>
              <div
                id="filter-menu"
                className="filter-menu"
                role="dialog"
                aria-modal="false"
                aria-labelledby="filter-menu-title"
                hidden
              >
                <div className="filter-menu-header">
                  <button
                    id="filter-menu-back"
                    className="icon-button"
                    type="button"
                    aria-label="Back to filter fields"
                    hidden
                  >
                    ←
                  </button>
                  <strong id="filter-menu-title">Add filter</strong>
                  <button
                    id="filter-menu-close"
                    className="icon-button"
                    type="button"
                    aria-label="Close filter menu"
                  >
                    ×
                  </button>
                </div>
                <input
                  id="filter-menu-search"
                  className="filter-menu-search"
                  type="search"
                  autoComplete="off"
                  placeholder="Find a filter…"
                  aria-label="Search available filters"
                  aria-controls="filter-menu-list"
                />
                <div id="filter-menu-list" className="filter-menu-list" role="menu" />
              </div>
            </div>
          </div>
        </section>

        <section id="filter-bar" className="filter-bar" aria-label="Active filters">
          <div id="active-filters" className="active-filters" />
          <button
            id="add-filter"
            className="add-filter"
            type="button"
            aria-label="Add another filter"
            aria-haspopup="dialog"
            aria-controls="filter-menu"
            aria-expanded="false"
          >
            +
          </button>
        </section>

        <div id="notice" className="notice" role="status" aria-live="polite" />
        <div id="groups" className="groups" aria-busy="true" />
      </main>

      <input
        id="attachment-picker"
        type="file"
        accept=".md,.markdown,.txt,text/markdown,text/plain"
        disabled
        hidden
      />
      <div
        id="status-modal"
        className="status-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="status-heading"
        hidden
      >
        <section className="status-dialog">
          <header className="status-header">
            <div>
              <p id="status-heading">Change status</p>
              <strong id="status-task-title" />
            </div>
            <button
              id="status-close"
              className="icon-button"
              type="button"
              aria-label="Close status picker"
            >
              ×
            </button>
          </header>
          <label className="visually-hidden" htmlFor="status-search">
            Find a status
          </label>
          <input
            id="status-search"
            className="status-search"
            type="search"
            autoComplete="off"
            placeholder="Change status…"
            aria-controls="status-options"
          />
          <div
            id="status-options"
            className="status-options"
            role="listbox"
            aria-label="Available statuses"
          />
          <p className="status-guidance">
            Done updates the ledger directly without running close hooks. Drop ends work
            without completing it.
          </p>
          <p id="status-error" className="status-error" role="status" aria-live="polite" />
        </section>
      </div>

      <script src="/app.js" defer />
    </>
  );
}
