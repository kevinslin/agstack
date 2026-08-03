"use strict";

const assert = require("node:assert/strict");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.attributes = new Map();
    this._text = "";
    this.className = "";
    this.hidden = false;
    this.value = "";
    this.title = "";
    this.type = "";
    this.files = [];
    this.clickCount = 0;
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  get textContent() {
    return this._text + this.children.map(child => child.textContent).join("");
  }

  append(...children) {
    for (const child of children) {
      child.parentNode = this;
      this.children.push(child);
    }
  }

  replaceChildren(...children) {
    this.children = [];
    this._text = "";
    this.append(...children);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  addEventListener(type, callback) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(callback);
    this.listeners.set(type, listeners);
  }

  dispatchEvent(event) {
    event.target ||= this;
    event.currentTarget = this;
    event.preventDefault ||= () => { event.defaultPrevented = true; };
    event.stopPropagation ||= () => {};
    for (const callback of this.listeners.get(event.type) || []) callback(event);
  }

  click() {
    this.clickCount += 1;
    this.dispatchEvent({type:"click"});
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }

  contains(target) {
    return target === this || this.children.some(child => child.contains(target));
  }

  querySelectorAll(selector) {
    const wantedRoles = Array.from(selector.matchAll(/role="([^"]+)"/g), match => match[1]);
    const matches = [];
    const visit = node => {
      if (wantedRoles.includes(node.getAttribute("role"))) matches.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return matches;
  }
}

class FakeDocument {
  constructor(ids) {
    this.listeners = new Map();
    this.activeElement = null;
    this.elements = Object.fromEntries(ids.map(id => [id, new FakeElement("div", this)]));
  }

  getElementById(id) {
    return this.elements[id];
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }

  addEventListener(type, callback) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(callback);
    this.listeners.set(type, listeners);
  }

  dispatchEvent(event) {
    event.preventDefault ||= () => { event.defaultPrevented = true; };
    event.stopPropagation ||= () => {};
    for (const callback of this.listeners.get(event.type) || []) callback(event);
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function snapshotFor(base, requestUrl) {
  const query = new URL(requestUrl, "http://dashboard.test/").searchParams;
  const snapshot = clone(base);
  const projects = query.getAll("project");
  const parents = query.getAll("parent_session_id");
  const root = query.get("root_parent") === "1";
  const statuses = query.getAll("status");
  const search = (query.get("search") || "").toLocaleLowerCase();
  const viewId = query.get("view");
  const savedView = base.views.find(view => view.id === viewId);
  const excludedStatuses = new Set(savedView?.filters.exclude_statuses || []);
  const allThreads = base.groups.flatMap(group => group.threads);
  const visible = allThreads.filter(thread =>
    (!projects.length || projects.includes(thread.project)) &&
    ((!parents.length && !root) || parents.includes(thread.parent_session_id) || (root && thread.parent_session_id === null)) &&
    (!statuses.length || statuses.includes(thread.status)) &&
    !excludedStatuses.has(thread.status) &&
    (!search || [thread.title,thread.id,thread.session_id,thread.parent_session_id || ""].some(
      value => value.toLocaleLowerCase().includes(search)
    ))
  );
  const groupOrder = statuses.length ? ["todo","active","blocked","merging","done","drop"].filter(status => statuses.includes(status)) : ["todo","active","blocked","merging","done","drop"].filter(status => !excludedStatuses.has(status));
  snapshot.filters = {projects,parent_session_ids:parents,include_root:root,statuses};
  snapshot.search = query.get("search") || "";
  snapshot.selected_view = viewId;
  snapshot.sort = {field:query.get("sort") || "updated",direction:query.get("direction") || "desc"};
  snapshot.visible_count = visible.length;
  snapshot.groups = groupOrder.map(status => ({status,count:visible.filter(thread => thread.status === status).length,threads:visible.filter(thread => thread.status === status)}));
  return snapshot;
}

function menuButton(document, label) {
  const list = document.getElementById("filter-menu-list");
  const buttons = list.querySelectorAll('[role="menuitem"],[role="menuitemcheckbox"]');
  return buttons.find(button => button.children[0]?.textContent === label);
}

function statusButton(document, label) {
  const options = document.getElementById("status-options");
  return options.querySelectorAll('[role="option"]').find(
    button => button.textContent.includes(label)
  );
}

function titleLink(row) {
  return row.children.find(cell => cell.className === "task-title-cell").children[0];
}

function allNodes(root) {
  return [root,...root.children.flatMap(allNodes)];
}

async function settle() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}

async function main() {
  const input = JSON.parse(await new Promise(resolve => {
    let value = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => { value += chunk; });
    process.stdin.on("end", () => resolve(value));
  }));
  const ids = [
    "view-tabs", "search", "sort", "direction", "refresh", "filter-trigger", "filter-menu",
    "filter-menu-title", "filter-menu-back", "filter-menu-close", "filter-menu-search",
    "filter-menu-list", "filter-bar", "active-filters", "add-filter", "notice",
    "groups", "summary", "status-modal", "status-task-title", "status-close",
    "status-search", "status-options", "status-error", "attachment-picker"
  ];
  const document = new FakeDocument(ids);
  document.getElementById("filter-menu").hidden = true;
  document.getElementById("filter-menu-back").hidden = true;
  document.getElementById("status-modal").hidden = true;
  document.getElementById("sort").value = "updated";
  document.getElementById("direction").value = "desc";
  const location = {
    search:"",pathname:"/token/",assigned:[],
    assign(value) { this.assigned.push(value); }
  };
  const history = {
    urls:[],
    replaceState(_state,_title,url) {
      this.urls.push(url);
      location.search = url.startsWith("?") ? url : "";
    }
  };
  const requests = [];
  const statusUpdates = [];
  const bulkStatusUpdates = [];
  const attachmentUploads = [];
  const clipboardWrites = [];
  const dashboardSnapshot = clone(input.snapshot);
  let statusFailure = null;
  let deferNextStatus = false;
  let resolveDeferredStatus = null;
  global.document = document;
  global.location = location;
  global.history = history;
  Object.defineProperty(global,"navigator",{
    configurable:true,
    value:{clipboard:{writeText:async value=>{clipboardWrites.push(value);}}}
  });
  global.fetch = async (requestUrl, options={}) => {
    requests.push(requestUrl);
    if(options.method === "POST"){
      const match = requestUrl.match(/^api\/tasks\/~([^/]+)\/attachments$/);
      assert.ok(match,"attachments use the token-scoped task route");
      const sessionId = decodeURIComponent(match[1]);
      const task = dashboardSnapshot.groups.flatMap(group => group.threads).find(
        thread => thread.session_id === sessionId
      );
      assert.ok(task,"attachment upload targets a rendered task");
      assert.deepEqual(Object.keys(options.headers),["Content-Type","X-AgTask-Filename"]);
      const filename = decodeURIComponent(options.headers["X-AgTask-Filename"]);
      assert.equal(options.headers["Content-Type"],"text/markdown");
      assert.equal(options.body.name,filename,"the selected File is the upload body");
      const attachment={created:"2026-01-09T00:00:00.000Z",path:`/managed/${filename}`,name:filename,url:`vscode://file/managed/${encodeURIComponent(filename)}`};
      task.files=[...(task.files||[]),attachment];
      attachmentUploads.push({sessionId,filename});
      return {ok:true,status:201,json:async()=>({attached:true,attachment})};
    }
    if(options.method === "PATCH"){
      if(requestUrl === "api/tasks/status"){
        const payload = JSON.parse(options.body);
        assert.deepEqual(Object.keys(payload),["tasks","status"]);
        assert.ok(payload.tasks.length > 1,"bulk status updates contain multiple tasks");
        const tasks = payload.tasks.map(item => {
          assert.deepEqual(Object.keys(item),["session_id","expected_status"]);
          const task = dashboardSnapshot.groups.flatMap(group => group.threads).find(
            thread => thread.session_id === item.session_id
          );
          assert.ok(task,"bulk status update targets rendered tasks");
          assert.equal(item.expected_status,task.status,"bulk updates guard every rendered row");
          return task;
        });
        if(statusFailure){
          const message = statusFailure;
          statusFailure = null;
          return {ok:false,status:409,json:async()=>({error:message})};
        }
        tasks.forEach(task => {
          task.status = payload.status;
          statusUpdates.push({sessionId:task.session_id,status:payload.status});
        });
        bulkStatusUpdates.push({sessionIds:tasks.map(task=>task.session_id),status:payload.status});
        return {ok:true,status:200,json:async()=>({changed:true,tasks:clone(tasks)})};
      }
      const match = requestUrl.match(/^api\/tasks\/~([^/]+)\/status$/);
      assert.ok(match,"status update uses the token-scoped task status route");
      const sessionId = decodeURIComponent(match[1]);
      const payload = JSON.parse(options.body);
      assert.deepEqual(Object.keys(payload),["expected_status","status"]);
      const task = dashboardSnapshot.groups.flatMap(group => group.threads).find(
        thread => thread.session_id === sessionId
      );
      assert.ok(task,"status update targets a rendered task");
      assert.equal(payload.expected_status,task.status,"status updates guard against stale rows");
      if(statusFailure){
        const message = statusFailure;
        statusFailure = null;
        return {ok:false,status:409,json:async()=>({error:message})};
      }
      const succeed = () => {
        task.status = payload.status;
        statusUpdates.push({sessionId,status:payload.status});
        return {ok:true,status:200,json:async()=>({changed:true,task:clone(task)})};
      };
      if(deferNextStatus){
        deferNextStatus = false;
        return await new Promise(resolve => {
          resolveDeferredStatus = () => resolve(succeed());
        });
      }
      return succeed();
    }
    return {ok:true,status:200,json:async()=>snapshotFor(dashboardSnapshot,requestUrl)};
  };
  vm.runInThisContext(input.source,{filename:"served-dashboard-app.js"});
  await settle();

  const menu = document.getElementById("filter-menu");
  const trigger = document.getElementById("filter-trigger");
  const plus = document.getElementById("add-filter");
  const chips = document.getElementById("active-filters");
  const viewTabs = document.getElementById("view-tabs");
  assert.deepEqual(
    viewTabs.children.map(tab => tab.textContent),
    ["All tasks","Today"],
    "the dashboard renders Linear-style saved view tabs"
  );
  assert.equal(viewTabs.children[0].getAttribute("aria-current"),"page");
  viewTabs.children[1].click();
  await settle();
  assert.equal(history.urls.at(-1),"?view=today","choosing Today applies its saved view");
  assert.equal(viewTabs.children[1].getAttribute("aria-current"),"page");
  assert.equal(
    allNodes(document.getElementById("groups")).some(
      node => node.tagName === "TR" && ["done","drop"].includes(node.getAttribute("data-status"))
    ),
    false,
    "the Today view excludes terminal task rows"
  );
  const todayTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.getAttribute("data-task-id")
  );
  todayTaskRow.click();
  assert.equal(
    location.assigned.at(-1),
    `tasks/~${encodeURIComponent(todayTaskRow.getAttribute("data-session-id"))}?view=today`,
    "opening task detail preserves the selected view in its URL"
  );
  viewTabs.children[0].click();
  await settle();
  assert.equal(history.urls.at(-1),"/token/","All tasks restores the unfiltered dashboard");

  const firstTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.getAttribute("data-task-id")
  );
  assert.ok(firstTaskRow,"dashboard renders task rows");
  assert.equal(firstTaskRow.getAttribute("role"),null,"task row keeps native table semantics");
  const firstTaskLink = titleLink(firstTaskRow);
  assert.equal(firstTaskLink.tagName,"A","task title is a real link");
  assert.equal(
    firstTaskLink.href,
    `codex://threads/${encodeURIComponent(firstTaskRow.getAttribute("data-session-id"))}`,
    "task title links to the Codex session"
  );
  const identityTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.task && node.task.parent_session_id !== null
  );
  const taskIdCopy = identityTaskRow.children[1].children[0];
  const codexShaCopy = identityTaskRow.children[2].children[0];
  const parentIdCopy = identityTaskRow.children[5].children[0];
  assert.equal(taskIdCopy.tagName,"BUTTON","the logical task ID is a keyboard-accessible copy control");
  assert.equal(taskIdCopy.textContent,identityTaskRow.getAttribute("data-task-id").slice(0,8));
  assert.equal(codexShaCopy.textContent,identityTaskRow.getAttribute("data-session-id").slice(0,8));
  assert.equal(parentIdCopy.textContent,identityTaskRow.task.parent_session_id.slice(0,8));
  assert.match(taskIdCopy.getAttribute("aria-label"),new RegExp(identityTaskRow.getAttribute("data-task-id")));
  const beforeIdentityClick = location.assigned.length;
  taskIdCopy.click();
  codexShaCopy.click();
  parentIdCopy.click();
  await settle();
  assert.deepEqual(
    clipboardWrites.slice(-3),
    [identityTaskRow.task.id,identityTaskRow.task.session_id,identityTaskRow.task.parent_session_id],
    "identity controls copy each complete value rather than its compact label"
  );
  identityTaskRow.dispatchEvent({type:"click",target:codexShaCopy});
  assert.equal(location.assigned.length,beforeIdentityClick,"copying an identity does not navigate the task row");
  assert.match(document.getElementById("notice").textContent,/Copied full Parent task ID/);
  const rootTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.task && node.task.parent_session_id === null
  );
  assert.equal(rootTaskRow.children[5].textContent,"—","root tasks retain an em dash parent value");
  assert.equal(rootTaskRow.children[5].children.length,0,"a null parent does not expose a copy control");

  const taskSearch = document.getElementById("search");
  taskSearch.value = identityTaskRow.task.session_id.slice(0,8).toUpperCase();
  taskSearch.dispatchEvent({type:"input"});
  await new Promise(resolve => setTimeout(resolve,220));
  await settle();
  assert.equal(document.getElementById("summary").textContent,"1 visible · 4 total","task search matches a case-insensitive partial Codex SHA");
  taskSearch.value = "";
  taskSearch.dispatchEvent({type:"input"});
  await new Promise(resolve => setTimeout(resolve,220));
  await settle();
  const fileBadge = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "A" && node.className === "file-badge"
  );
  assert.ok(fileBadge,"an attached task renders a file badge");
  assert.equal(fileBadge.textContent,"file");
  assert.match(fileBadge.href,/^vscode:\/\/file\//);
  assert.match(fileBadge.title,/dashboard task\.md/);
  const fileTaskRow = fileBadge.parentNode.parentNode.parentNode;
  const beforeFileClick = location.assigned.length;
  fileTaskRow.dispatchEvent({type:"click",target:fileBadge});
  assert.equal(
    location.assigned.length,
    beforeFileClick,
    "clicking a file badge does not open the task detail page"
  );
  firstTaskRow.dispatchEvent({type:"click",target:firstTaskRow.children[4]});
  assert.equal(
    location.assigned.at(-1),
    `tasks/~${encodeURIComponent(firstTaskRow.getAttribute("data-session-id"))}`,
    "clicking a non-title cell opens the task detail page"
  );
  firstTaskLink.dispatchEvent({type:"keydown",key:" "});
  assert.equal(location.assigned.at(-1),firstTaskLink.href,"Space on the title link opens the Codex session");

  const statusModal = document.getElementById("status-modal");
  firstTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:firstTaskRow});
  assert.equal(statusModal.hidden,false,"S opens the status picker for the hovered task");
  assert.equal(
    document.getElementById("status-task-title").textContent,
    firstTaskLink.textContent,
    "the picker identifies the hovered task"
  );
  assert.equal(document.activeElement,document.getElementById("status-search"));
  assert.deepEqual(
    ["Todo","Active","Blocked","Done","Drop"].map(label=>Boolean(statusButton(document,label))),
    [true,true,true,true,true],
    "the picker exposes the ledger's user-settable statuses"
  );
  statusButton(document,"Blocked").click();
  await settle();
  await settle();
  assert.deepEqual(
    statusUpdates,
    [{sessionId:firstTaskRow.getAttribute("data-session-id"),status:"blocked"}],
    "choosing a status persists the hovered task selection"
  );
  assert.equal(statusModal.hidden,true,"a successful status update closes the picker");

  let refreshedTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" &&
      node.getAttribute("data-session-id") === firstTaskRow.getAttribute("data-session-id")
  );
  assert.equal(
    refreshedTaskRow.getAttribute("data-status"),
    "blocked",
    "the refreshed dashboard renders the task in its persisted status"
  );
  refreshedTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"S",target:refreshedTaskRow});
  assert.equal(statusModal.hidden,false,"the shortcut is case-insensitive");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});
  assert.equal(statusModal.hidden,true,"Escape dismisses the status picker");

  statusFailure = "task status changed; refresh and try again";
  refreshedTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:refreshedTaskRow});
  statusButton(document,"Todo").click();
  await settle();
  assert.equal(statusModal.hidden,false,"a failed update keeps the picker open");
  assert.match(document.getElementById("status-error").textContent,/refresh and try again/);
  assert.equal(statusUpdates.length,1,"a failed update does not move the task");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});

  deferNextStatus = true;
  refreshedTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:refreshedTaskRow});
  statusButton(document,"Todo").click();
  assert.equal(typeof resolveDeferredStatus,"function","status request is deferred");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});
  const otherTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" &&
      node.getAttribute("data-status") === "active" &&
      node.getAttribute("data-session-id") !== refreshedTaskRow.getAttribute("data-session-id")
  );
  otherTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:otherTaskRow});
  const otherTaskTitle = titleLink(otherTaskRow).textContent;
  assert.equal(document.getElementById("status-task-title").textContent,otherTaskTitle);
  resolveDeferredStatus();
  await settle();
  await settle();
  assert.equal(statusModal.hidden,false,"an older response does not close a newer picker");
  assert.equal(
    document.getElementById("status-task-title").textContent,
    otherTaskTitle,
    "an older response does not overwrite the newer picker"
  );
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});
  refreshedTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" &&
      node.getAttribute("data-session-id") === firstTaskRow.getAttribute("data-session-id")
  );

  refreshedTaskRow.dispatchEvent({type:"mouseenter"});
  document.getElementById("search").focus();
  document.dispatchEvent({
    type:"keydown",key:"s",target:document.getElementById("search")
  });
  assert.equal(statusModal.hidden,true,"typing in a dashboard control does not open the picker");
  const attachmentPicker = document.getElementById("attachment-picker");
  const pickerClicksBeforeTyping = attachmentPicker.clickCount;
  document.dispatchEvent({
    type:"keydown",key:"a",target:document.getElementById("search")
  });
  assert.equal(attachmentPicker.clickCount,pickerClicksBeforeTyping,"A does not open a file picker while typing");
  document.getElementById("search").value = "";

  refreshedTaskRow.dispatchEvent({type:"mouseleave"});
  refreshedTaskRow.dispatchEvent({type:"focusin",target:titleLink(refreshedTaskRow)});
  document.dispatchEvent({
    type:"keydown",key:"s",target:titleLink(refreshedTaskRow)
  });
  assert.equal(statusModal.hidden,false,"a focused task link can use the same shortcut");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});

  const doneTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.getAttribute("data-status") === "done"
  );
  doneTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:doneTaskRow});
  assert.match(
    document.getElementById("status-error").textContent,
    /must be reopened explicitly/,
    "workflow-owned statuses explain why manual status changes are unavailable"
  );
  assert.equal(
    statusButton(document,"Active").disabled,
    true,
    "done tasks cannot bypass the reopen workflow"
  );
  const pickerClicksBeforeModal = attachmentPicker.clickCount;
  document.dispatchEvent({type:"keydown",key:"a",target:doneTaskRow});
  assert.equal(attachmentPicker.clickCount,pickerClicksBeforeModal,"A does not open a file picker over the status modal");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});

  assert.equal(menu.hidden,true,"menu starts closed");
  trigger.click();
  assert.equal(menu.hidden,false,"toolbar trigger opens the filter menu");
  const pickerClicksBeforeMenu = attachmentPicker.clickCount;
  document.dispatchEvent({type:"keydown",key:"a",target:firstTaskRow});
  assert.equal(attachmentPicker.clickCount,pickerClicksBeforeMenu,"A does not open a file picker over the filter menu");
  assert.equal(trigger.getAttribute("aria-expanded"),"true");
  assert.equal(document.activeElement,document.getElementById("filter-menu-search"));
  assert.deepEqual(["Project","Parent task","Status"].map(label=>Boolean(menuButton(document,label))),[true,true,true]);

  menu.dispatchEvent({type:"keydown",key:"ArrowUp"});
  assert.equal(document.activeElement.textContent.startsWith("Status"),true,"ArrowUp enters at the last menu item");
  menu.dispatchEvent({type:"keydown",key:"Home"});
  assert.equal(document.activeElement.textContent.startsWith("Project"),true,"Home focuses the first item");
  menu.dispatchEvent({type:"keydown",key:"End"});
  assert.equal(document.activeElement.textContent.startsWith("Status"),true,"End focuses the last item");
  document.getElementById("filter-menu-search").focus();

  menuButton(document,"Project").click();
  assert.equal(document.getElementById("filter-menu-title").textContent,"Project");
  assert.equal(document.getElementById("filter-menu-search").getAttribute("aria-label"),"Search Project values");
  menu.dispatchEvent({type:"keydown",key:"ArrowLeft"});
  assert.equal(document.getElementById("filter-menu-title").textContent,"Add filter","ArrowLeft returns to fields");
  menuButton(document,"Project").click();
  menuButton(document,"beta").focus();
  menu.dispatchEvent({type:"keydown",key:"Enter"});
  await settle();
  assert.equal(menu.hidden,true,"choosing a value dismisses the menu predictably");
  assert.equal(history.urls.at(-1),"?project=beta");
  assert.match(chips.textContent,/Projectisbeta×/);

  plus.click();
  menuButton(document,"Project").click();
  menuButton(document,"alpha").focus();
  menu.dispatchEvent({type:"keydown",key:" "});
  await settle();
  assert.equal(history.urls.at(-1),"?project=alpha&project=beta","out-of-order selection is canonicalized");
  assert.match(chips.textContent,/Projectis any ofalpha or beta×/);

  plus.click();
  menuButton(document,"Status").click();
  menuButton(document,"Active").click();
  await settle();
  assert.equal(history.urls.at(-1),"?project=alpha&project=beta&status=active","multiple fields synchronize to the canonical query");
  assert.match(chips.textContent,/Projectis any ofalpha or beta×StatusisActive×/);
  assert.equal(document.getElementById("summary").textContent,"1 visible · 4 total","rendered results match the selected filters");

  plus.click();
  menuButton(document,"Status").click();
  menuButton(document,"Merging").click();
  await settle();
  assert.equal(history.urls.at(-1),"?project=alpha&project=beta&status=active&status=merging","merging status is preserved in the canonical query");
  assert.match(chips.textContent,/Statusis any ofActive or Merging×/);

  const removeProject = allNodes(chips).find(node => node.getAttribute("aria-label") === "Remove Project filter");
  removeProject.click();
  await settle();
  assert.equal(history.urls.at(-1),"?status=active&status=merging","chip removal updates the query immediately");
  assert.doesNotMatch(chips.textContent,/Project/);
  assert.match(chips.textContent,/Statusis any ofActive or Merging×/);

  const search = document.getElementById("search");
  search.value = "does-not-exist";
  search.dispatchEvent({type:"input"});
  await new Promise(resolve => setTimeout(resolve,220));
  await settle();
  const groups = document.getElementById("groups");
  assert.match(groups.textContent,/No tasks match this view/);
  const clearView = allNodes(groups).find(node => node.textContent === "Clear filters and search");
  clearView.click();
  await settle();
  assert.equal(history.urls.at(-1),"/token/","the no-results recovery clears filters and search");
  assert.equal(document.getElementById("summary").textContent,"4 visible · 4 total");

  plus.click();
  assert.equal(menu.hidden,false,"the chip-bar plus opens the same menu");
  menu.dispatchEvent({type:"keydown",key:"ArrowDown"});
  assert.equal(document.activeElement.textContent.startsWith("Project"),true,"ArrowDown moves focus into menu items");
  menu.dispatchEvent({type:"keydown",key:"Escape"});
  assert.equal(menu.hidden,true,"Escape dismisses the menu");
  assert.equal(document.activeElement,plus,"Escape restores focus to the invoking plus button");

  trigger.click();
  document.dispatchEvent({type:"pointerdown",target:new FakeElement("div",document)});
  assert.equal(menu.hidden,true,"an outside pointer action dismisses the menu");
  plus.click();
  menu.dispatchEvent({type:"keydown",key:"Tab"});
  assert.equal(menu.hidden,true,"Tab dismisses the menu without trapping focus");

  document.dispatchEvent({type:"keydown",key:"j",target:document.getElementById("groups")});
  const navigatedRows = allNodes(document.getElementById("groups")).filter(
    node => node.tagName === "TR" && node.getAttribute("data-task-id")
  );
  document.dispatchEvent({type:"keydown",key:"k",target:navigatedRows[0]});
  const activeIndex = navigatedRows.findIndex(row=>row.getAttribute("data-active") === "true");
  assert.equal(activeIndex,0,"J starts navigation at the first task row and K clamps there");
  document.dispatchEvent({type:"keydown",key:"j",target:navigatedRows[activeIndex]});
  const nextIndex = 1;
  assert.equal(navigatedRows[nextIndex].getAttribute("data-active"),"true","J moves to the next task row");
  document.dispatchEvent({type:"keydown",key:"k",target:navigatedRows[nextIndex]});
  assert.equal(navigatedRows[activeIndex].getAttribute("data-active"),"true","K moves to the previous task row");

  document.dispatchEvent({type:"keydown",key:"x",target:navigatedRows[activeIndex]});
  assert.equal(navigatedRows[activeIndex].getAttribute("aria-selected"),"true","X selects the active task row");
  assert.equal(navigatedRows[activeIndex].children[0].children[0].getAttribute("aria-pressed"),"true","the row checkbox reflects keyboard selection");
  document.dispatchEvent({type:"keydown",key:"j",target:navigatedRows[activeIndex]});
  document.dispatchEvent({type:"keydown",key:"x",target:navigatedRows[nextIndex]});
  assert.match(document.getElementById("summary").textContent,/2 selected/);
  document.dispatchEvent({type:"keydown",key:"s",target:navigatedRows[nextIndex]});
  assert.equal(document.getElementById("status-task-title").textContent,"2 tasks selected","S opens one picker for the selected rows");
  const beforeBulkUpdates=statusUpdates.length;
  statusButton(document,"Blocked").click();
  await settle();
  await settle();
  assert.deepEqual(
    bulkStatusUpdates.at(-1),
    {sessionIds:[navigatedRows[activeIndex],navigatedRows[nextIndex]].map(row=>row.getAttribute("data-session-id")),status:"blocked"},
    "choosing a status applies one bulk mutation to every selected row"
  );
  assert.equal(statusUpdates.length,beforeBulkUpdates+2);
  assert.doesNotMatch(document.getElementById("summary").textContent,/selected/,"selection clears after the complete bulk mutation succeeds");

  const bulkFailureRows=allNodes(document.getElementById("groups")).filter(
    node => node.tagName === "TR" && node.getAttribute("data-status") === "blocked"
  ).slice(0,2);
  bulkFailureRows[0].dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"x",target:bulkFailureRows[0]});
  document.dispatchEvent({type:"keydown",key:"j",target:bulkFailureRows[0]});
  document.dispatchEvent({type:"keydown",key:"x",target:bulkFailureRows[1]});
  statusFailure="task status changed; refresh and try again";
  document.dispatchEvent({type:"keydown",key:"s",target:bulkFailureRows[1]});
  statusButton(document,"Todo").click();
  await settle();
  assert.equal(statusModal.hidden,false,"a bulk conflict keeps the picker open");
  assert.match(document.getElementById("status-error").textContent,/refresh and try again/);
  assert.match(document.getElementById("summary").textContent,/2 selected/,"a bulk conflict preserves the selected rows");
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});
  document.dispatchEvent({type:"keydown",key:"x",target:bulkFailureRows[1]});
  document.dispatchEvent({type:"keydown",key:"k",target:bulkFailureRows[1]});
  document.dispatchEvent({type:"keydown",key:"x",target:bulkFailureRows[0]});

  const completableTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && ["todo","active","blocked"].includes(node.getAttribute("data-status"))
  );
  completableTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:completableTaskRow});
  statusButton(document,"Done").click();
  await settle();
  await settle();
  assert.equal(statusUpdates.at(-1).status,"done","Done is sent through the dashboard status endpoint");
  assert.ok(
    allNodes(document.getElementById("groups")).some(
      node => node.tagName === "TR" &&
        node.getAttribute("data-session-id") === completableTaskRow.getAttribute("data-session-id") &&
        node.getAttribute("data-status") === "done"
    ),
    "the dashboard renders the directly completed task in the Done group"
  );

  const droppableTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && ["todo","active","blocked"].includes(node.getAttribute("data-status"))
  );
  droppableTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:droppableTaskRow});
  statusButton(document,"Drop").click();
  await settle();
  await settle();
  assert.equal(statusUpdates.at(-1).status,"drop","Drop is persisted as a completion status");
  const droppedTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.getAttribute("data-status") === "drop"
  );
  assert.ok(droppedTaskRow,"the dashboard renders a Drop group");
  droppedTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"s",target:droppedTaskRow});
  assert.match(
    document.getElementById("status-error").textContent,
    /must be reopened explicitly/,
    "dropped tasks stay terminal until reopened"
  );
  assert.equal(statusButton(document,"Active").disabled,true);
  statusModal.dispatchEvent({type:"keydown",key:"Escape"});

  const attachableTaskRow = allNodes(document.getElementById("groups")).find(
    node => node.tagName === "TR" && node.getAttribute("data-task-id")
  );
  attachableTaskRow.dispatchEvent({type:"mouseenter"});
  document.dispatchEvent({type:"keydown",key:"A",target:attachableTaskRow});
  assert.equal(attachmentPicker.clickCount,pickerClicksBeforeMenu+1,"A opens the native picker for the active or hovered row");
  attachmentPicker.files=[{name:"picked note.md",type:"text/markdown"}];
  attachmentPicker.dispatchEvent({type:"change",target:attachmentPicker});
  await settle();
  await settle();
  assert.deepEqual(
    attachmentUploads.at(-1),
    {sessionId:attachableTaskRow.getAttribute("data-session-id"),filename:"picked note.md"},
    "the selected file uploads to the active task"
  );
  assert.match(document.getElementById("notice").textContent,/Attached picked note\.md/);
  assert.ok(
    allNodes(document.getElementById("groups")).some(
      node => node.tagName === "A" && node.className === "file-badge" && /picked note\.md/.test(node.title)
    ),
    "a successful upload refreshes the dashboard attachment projection"
  );

  assert.ok(requests.length >= 5,"interactions issued fresh dashboard requests");
  process.stdout.write("dashboard client interactions passed\n");
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
