import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Task detail · agtask",
};

export default function TaskDetail() {
  return (
    <>
      <header className="detail-topbar">
        <a id="back-link" className="back-link" href="../">
          ← All tasks
        </a>
      </header>

      <main className="detail-layout">
        <article id="detail-content" className="detail-content" aria-busy="true">
          <h1 id="task-title">Loading task…</h1>
          <div id="task-description" className="task-description markdown-body" />

          <section className="timeline-section" aria-labelledby="timeline-heading">
            <h2 id="timeline-heading">Timeline</h2>
            <ol id="timeline" className="timeline" />
          </section>
        </article>

        <aside className="properties" aria-labelledby="properties-heading">
          <h2 id="properties-heading">Properties</h2>
          <dl>
            <div>
              <dt>Created</dt>
              <dd id="task-created">—</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd id="task-updated">—</dd>
            </div>
            <div>
              <dt>Session ID</dt>
              <dd>
                <a id="task-session-id" className="session-link" href="../">
                  —
                </a>
              </dd>
            </div>
            <div id="task-files-property" hidden>
              <dt>Files</dt>
              <dd id="task-files" className="file-badges" />
            </div>
          </dl>
        </aside>

        <p id="detail-notice" className="detail-notice" role="status" aria-live="polite" />
      </main>

      <script src="/vendor/marked.js" defer />
      <script src="/task.js" defer />
    </>
  );
}
