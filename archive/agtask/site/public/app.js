(() => {
  "use strict";
  const ROOT_PARENT = "__root__";
  const ids = [
    "view-tabs", "search", "sort", "direction", "refresh", "filter-trigger", "filter-menu",
    "filter-menu-title", "filter-menu-back", "filter-menu-close", "filter-menu-search",
    "filter-menu-list", "filter-bar", "active-filters", "add-filter", "notice",
    "groups", "summary", "status-modal", "status-task-title", "status-close",
    "status-search", "status-options", "status-error", "attachment-picker"
  ];
  const el = Object.fromEntries(ids.map(id => [id.replace(/-([a-z])/g,(_match,letter)=>letter.toUpperCase()), document.getElementById(id)]));
  let lastSnapshot = null;
  let currentState = stateFromUrl();
  let debounceTimer = null;
  let requestGeneration = 0;
  let menuField = null;
  let menuInvoker = null;
  let hoveredTask = null;
  let activeTask = null;
  let selectedTasks = new Map();
  let renderedRows = [];
  let statusTasks = [];
  let statusInvoker = null;
  let statusSaving = false;
  let statusModalGeneration = 0;
  let attachmentTask = null;
  let attachmentSaving = false;

  const STATUS_LABELS = {todo:"Todo",active:"Active",blocked:"Blocked",merging:"Merging",done:"Done",drop:"Drop"};
  const STATUS_OPTIONS = [
    {value:"todo",label:"Todo",symbol:"○",shortcut:"1"},
    {value:"active",label:"Active",symbol:"◐",shortcut:"2"},
    {value:"blocked",label:"Blocked",symbol:"!",shortcut:"3"},
    {value:"done",label:"Done",symbol:"✓",shortcut:"4"},
    {value:"drop",label:"Drop",symbol:"×",shortcut:"5"}
  ];
  const FILTER_DEFS = [
    {
      id:"project", label:"Project",
      values:state => state.projects,
      withValues:(state,values) => ({...state,projects:values}),
      options:snapshot => snapshot.facets.projects.map(item => ({value:item.value,label:item.value,count:item.count}))
    },
    {
      id:"parent", label:"Parent task",
      values:state => [...state.parents,...(state.root?[ROOT_PARENT]:[])],
      withValues:(state,values) => ({...state,parents:values.filter(value=>value!==ROOT_PARENT),root:values.includes(ROOT_PARENT)}),
      options:snapshot => snapshot.facets.parents.map(item => ({value:item.value===null?ROOT_PARENT:item.value,label:item.value===null?"Root tasks":item.value,count:item.count}))
    },
    {
      id:"status", label:"Status",
      values:state => state.statuses,
      withValues:(state,values) => ({...state,statuses:values}),
      options:snapshot => snapshot.facets.statuses.map(item => ({value:item.value,label:STATUS_LABELS[item.value]||item.value,count:item.count}))
    }
  ];

  function stateFromUrl() {
    const query = new URLSearchParams(location.search);
    return {
      projects:query.getAll("project"), parents:query.getAll("parent_session_id"),
      root:query.get("root_parent")==="1", statuses:query.getAll("status"),
      sort:query.get("sort")||"updated", direction:query.get("direction")||"desc",
      search:query.get("search")||"", view:query.get("view")||null
    };
  }

  function stateFromSnapshot(snapshot) {
    return {
      projects:snapshot.filters.projects, parents:snapshot.filters.parent_session_ids,
      root:snapshot.filters.include_root, statuses:snapshot.filters.statuses,
      sort:snapshot.sort.field, direction:snapshot.sort.direction, search:snapshot.search,
      view:snapshot.selected_view
    };
  }

  function queryFor(state) {
    const query = new URLSearchParams();
    const sorted = values => [...new Set(values)].sort((left,right)=>left.localeCompare(right,undefined,{sensitivity:"base"})||left.localeCompare(right));
    sorted(state.projects).forEach(value=>query.append("project",value));
    sorted(state.parents).forEach(value=>query.append("parent_session_id",value));
    if(state.root)query.set("root_parent","1");
    ["todo","active","blocked","merging","done","drop"].filter(value=>state.statuses.includes(value)).forEach(value=>query.append("status",value));
    if(state.sort!=="updated")query.set("sort",state.sort);
    if(state.direction!=="desc")query.set("direction",state.direction);
    if(state.search)query.set("search",state.search);
    if(state.view)query.set("view",state.view);
    return query.toString();
  }

  function acceptedQueryFor(state) {
    const query = new URLSearchParams();
    state.projects.forEach(value=>query.append("project",value));
    state.parents.forEach(value=>query.append("parent_session_id",value));
    if(state.root)query.set("root_parent","1");
    state.statuses.forEach(value=>query.append("status",value));
    if(state.sort!=="updated")query.set("sort",state.sort);
    if(state.direction!=="desc")query.set("direction",state.direction);
    if(state.search)query.set("search",state.search);
    if(state.view)query.set("view",state.view);
    return query.toString();
  }

  function filterDef(id) { return FILTER_DEFS.find(definition=>definition.id===id); }
  function filterValues(definition,state=currentState) { return definition.values(state); }
  function valueLabel(definition,value) {
    if(value===ROOT_PARENT)return "Root tasks";
    if(definition.id==="status")return STATUS_LABELS[value]||value;
    return value;
  }

  function formatFilterValue(definition,values) {
    return values.map(value=>valueLabel(definition,value)).join(" or ");
  }

  function renderActiveFilters() {
    const chips = FILTER_DEFS.flatMap(definition => {
      const values = filterValues(definition);
      if(!values.length)return [];
      const chip = document.createElement("div");
      chip.className = "filter-chip";
      chip.setAttribute("role","group");
      chip.setAttribute("aria-label",`${definition.label} filter`);
      const field = document.createElement("span"); field.className="chip-segment chip-field"; field.textContent=definition.label;
      const operator = document.createElement("span"); operator.className="chip-segment chip-operator"; operator.textContent=values.length>1?"is any of":"is";
      const value = document.createElement("span"); value.className="chip-segment chip-value"; value.textContent=formatFilterValue(definition,values); value.title=value.textContent;
      const remove = document.createElement("button"); remove.className="chip-remove"; remove.type="button"; remove.textContent="×"; remove.setAttribute("aria-label",`Remove ${definition.label} filter`);
      remove.addEventListener("click",()=>{
        currentState=definition.withValues(currentState,[]);
        renderActiveFilters();
        closeFilterMenu(false);
        el.addFilter.focus();
        load(currentState);
      });
      chip.append(field,operator,value,remove);
      return [chip];
    });
    if(!chips.length){
      const empty=document.createElement("span"); empty.className="filter-empty-label"; empty.textContent="No filters applied";
      el.activeFilters.replaceChildren(empty);
    }else el.activeFilters.replaceChildren(...chips);
  }

  function renderViewTabs(snapshot) {
    const tabs=[{id:null,name:"All tasks"},...snapshot.views].map(view=>{
      const button=document.createElement("button");
      button.type="button"; button.className="view-tab"; button.textContent=view.name;
      if(view.id===currentState.view)button.setAttribute("aria-current","page");
      button.addEventListener("click",()=>{
        if(currentState.view===view.id)return;
        currentState={...currentState,view:view.id};
        load(currentState);
      });
      return button;
    });
    el.viewTabs.replaceChildren(...tabs);
  }

  function availableOptions(definition) {
    if(!lastSnapshot)return [];
    const options=definition.options(lastSnapshot);
    const known=new Set(options.map(option=>option.value));
    filterValues(definition).forEach(value=>{
      if(!known.has(value))options.push({value,label:valueLabel(definition,value),count:0});
    });
    return options;
  }

  function menuItem(label,meta,attributes,onChoose) {
    const button=document.createElement("button");
    button.type="button"; button.className="filter-menu-item"; button.setAttribute("role",attributes.role||"menuitem");
    Object.entries(attributes).forEach(([name,value])=>{if(name!=="role")button.setAttribute(name,String(value));});
    const name=document.createElement("span"); name.textContent=label;
    const detail=document.createElement("span"); detail.className="filter-menu-meta"; detail.textContent=meta;
    button.append(name,detail); button.addEventListener("click",onChoose); return button;
  }

  function renderFilterMenu() {
    if(el.filterMenu.hidden)return;
    const term=el.filterMenuSearch.value.trim().toLocaleLowerCase();
    el.filterMenuBack.hidden=menuField===null;
    el.filterMenuTitle.textContent=menuField?filterDef(menuField).label:"Add filter";
    el.filterMenuSearch.placeholder=menuField?"Find a value…":"Find a filter…";
    el.filterMenuSearch.setAttribute("aria-label",menuField?`Search ${filterDef(menuField).label} values`:"Search available filters");
    const items=[];
    if(menuField===null){
      FILTER_DEFS.filter(definition=>definition.label.toLocaleLowerCase().includes(term)).forEach(definition=>{
        const count=filterValues(definition).length;
        items.push(menuItem(definition.label,count?`${count} active  ›`:"Choose values  ›",{"data-menu-key":definition.id,"aria-current":count?"true":"false"},()=>showFilterValues(definition.id)));
      });
    }else{
      const definition=filterDef(menuField); const selected=new Set(filterValues(definition));
      availableOptions(definition).filter(option=>option.label.toLocaleLowerCase().includes(term)).forEach(option=>{
        const active=selected.has(option.value);
        items.push(menuItem(option.label,active?"✓ Added":`${option.count} tasks`,{role:"menuitemcheckbox","aria-checked":active?"true":"false","data-menu-key":option.value},()=>toggleFilterValue(definition,option.value)));
      });
    }
    if(!items.length){const empty=document.createElement("p");empty.className="filter-menu-empty";empty.textContent=menuField?"No available values":"No matching filters";items.push(empty);}
    el.filterMenuList.replaceChildren(...items);
  }

  function showFilterValues(id) {
    menuField=id; el.filterMenuSearch.value=""; renderFilterMenu(); el.filterMenuSearch.focus();
  }

  function toggleFilterValue(definition,value) {
    const values=filterValues(definition); const active=values.includes(value);
    const next=active?values.filter(item=>item!==value):[...values,value];
    currentState=definition.withValues(currentState,next);
    renderActiveFilters(); closeFilterMenu(); load(currentState);
  }

  function openFilterMenu(invoker) {
    menuInvoker=invoker; menuField=null; el.filterMenuSearch.value=""; el.filterMenu.hidden=false;
    el.filterTrigger.setAttribute("aria-expanded","true"); el.addFilter.setAttribute("aria-expanded","true");
    renderFilterMenu(); el.filterMenuSearch.focus();
  }

  function closeFilterMenu(restoreFocus=true) {
    if(el.filterMenu.hidden)return;
    el.filterMenu.hidden=true; el.filterTrigger.setAttribute("aria-expanded","false"); el.addFilter.setAttribute("aria-expanded","false");
    const invoker=menuInvoker; menuInvoker=null; menuField=null; if(restoreFocus&&invoker)invoker.focus();
  }

  function focusMenuItem(position) {
    const items=Array.from(el.filterMenuList.querySelectorAll('[role="menuitem"],[role="menuitemcheckbox"]'));
    if(!items.length)return;
    let index=items.indexOf(document.activeElement);
    if(position==="first")index=0; else if(position==="last")index=items.length-1;
    else if(index<0)index=position==="next"?0:items.length-1;
    else index=(index+(position==="next"?1:-1)+items.length)%items.length;
    items[index].focus();
  }

  function menuKeydown(event) {
    if(el.filterMenu.hidden)return;
    if(event.key==="Escape"){event.preventDefault();closeFilterMenu();return;}
    if(event.key==="Tab"){closeFilterMenu(false);return;}
    if(event.key==="ArrowDown"){event.preventDefault();focusMenuItem("next");}
    else if(event.key==="ArrowUp"){event.preventDefault();focusMenuItem("previous");}
    else if(event.key==="Home"){event.preventDefault();focusMenuItem("first");}
    else if(event.key==="End"){event.preventDefault();focusMenuItem("last");}
    else if((event.key==="Enter"||event.key===" ")&&document.activeElement&&["menuitem","menuitemcheckbox"].includes(document.activeElement.getAttribute("role"))){event.preventDefault();document.activeElement.click();}
    else if(event.key==="ArrowLeft"&&menuField){event.preventDefault();menuField=null;el.filterMenuSearch.value="";renderFilterMenu();el.filterMenuSearch.focus();}
  }

  function isTypingTarget(target) {
    return Boolean(target&&(target===el.search||target===el.filterMenuSearch||target===el.statusSearch||["INPUT","TEXTAREA","SELECT"].includes(target.tagName)||target.getAttribute&&target.getAttribute("contenteditable")==="true"));
  }

  function statusButtons() {
    return Array.from(el.statusOptions.querySelectorAll('[role="option"]')).filter(item=>!item.disabled);
  }

  function statusLockMessage(tasks) {
    const task=tasks.find(item=>["done","drop","merging"].includes(item.status));
    if(!task)return "";
    const prefix=tasks.length>1?`${task.title}: `:"";
    if(task.status==="done")return `${prefix}Done tasks must be reopened explicitly.`;
    if(task.status==="drop")return `${prefix}Dropped tasks must be reopened explicitly.`;
    if(task.status==="merging")return `${prefix}Merging tasks must be closed or released explicitly.`;
    return "";
  }

  function renderStatusOptions() {
    if(el.statusModal.hidden||!statusTasks.length)return;
    const term=el.statusSearch.value.trim().toLocaleLowerCase();
    const options=STATUS_OPTIONS.filter(option=>option.label.toLocaleLowerCase().includes(term));
    const currentStatus=statusTasks.every(task=>task.status===statusTasks[0].status)?statusTasks[0].status:null;
    const items=options.map(option=>{
      const button=document.createElement("button"); button.type="button"; button.className="status-option";
      button.setAttribute("role","option"); button.setAttribute("aria-selected",currentStatus===option.value?"true":"false");
      button.disabled=statusSaving||Boolean(statusLockMessage(statusTasks));
      const symbol=document.createElement("span"); symbol.className=`status-symbol ${option.value}`; symbol.textContent=option.symbol; symbol.setAttribute("aria-hidden","true");
      const label=document.createElement("span"); label.textContent=option.label;
      const current=document.createElement("span"); current.className="status-current"; current.textContent=currentStatus===option.value?"Current":"";
      const shortcut=document.createElement("span"); shortcut.className="status-shortcut"; shortcut.textContent=option.shortcut; shortcut.setAttribute("aria-hidden","true");
      button.append(symbol,label,current,shortcut); button.addEventListener("click",()=>updateStatus(option.value)); return button;
    });
    if(!items.length){const empty=document.createElement("p");empty.className="filter-menu-empty";empty.textContent="No matching statuses";items.push(empty);}
    el.statusOptions.replaceChildren(...items);
  }

  function openStatusModal(tasks) {
    closeFilterMenu(false);
    statusModalGeneration+=1;
    statusTasks=[...tasks]; statusInvoker=document.activeElement; statusSaving=false;
    el.statusTaskTitle.textContent=tasks.length===1?tasks[0].title:`${tasks.length} tasks selected`; el.statusSearch.value=""; el.statusError.textContent=statusLockMessage(tasks);
    el.statusModal.hidden=false; renderStatusOptions(); el.statusSearch.focus();
  }

  function closeStatusModal(restoreFocus=true) {
    if(el.statusModal.hidden)return;
    statusModalGeneration+=1;
    el.statusModal.hidden=true; el.statusError.textContent="";
    const invoker=statusInvoker; statusTasks=[]; statusInvoker=null; statusSaving=false;
    if(restoreFocus&&invoker&&invoker.focus)invoker.focus();
  }

  async function updateStatus(status) {
    if(!statusTasks.length||statusSaving)return;
    const lockMessage=statusLockMessage(statusTasks);
    if(lockMessage){el.statusError.textContent=lockMessage;return;}
    const tasks=[...statusTasks]; const generation=statusModalGeneration;
    statusSaving=true; el.statusError.textContent=""; renderStatusOptions();
    try {
      const bulk=tasks.length>1;
      const response=await fetch(bulk?"api/tasks/status":`api/tasks/~${encodeURIComponent(tasks[0].session_id)}/status`,{
        method:"PATCH",cache:"no-store",headers:{"Content-Type":"application/json"},
        body:JSON.stringify(bulk?{tasks:tasks.map(task=>({session_id:task.session_id,expected_status:task.status})),status}:{expected_status:tasks[0].status,status})
      });
      const payload=await response.json();
      if(!response.ok)throw new Error(payload.error||`Status update failed (${response.status})`);
      tasks.forEach(task=>selectedTasks.delete(task.session_id));
      const refreshed=await load(currentState);
      if(generation===statusModalGeneration&&!el.statusModal.hidden){
        closeStatusModal(false);
        if(refreshed){el.notice.textContent=tasks.length===1?`Set ${tasks[0].title} to ${STATUS_LABELS[status]||status}.`:`Set ${tasks.length} tasks to ${STATUS_LABELS[status]||status}.`; el.notice.className="notice";}
      }
    } catch (error) {
      if(generation===statusModalGeneration&&!el.statusModal.hidden)el.statusError.textContent=error.message;
    } finally {
      if(generation===statusModalGeneration){statusSaving=false;if(!el.statusModal.hidden)renderStatusOptions();}
    }
  }

  function focusStatusOption(position) {
    const items=statusButtons(); if(!items.length)return;
    let index=items.indexOf(document.activeElement);
    if(position==="first")index=0; else if(position==="last")index=items.length-1;
    else if(index<0)index=position==="next"?0:items.length-1;
    else index=(index+(position==="next"?1:-1)+items.length)%items.length;
    items[index].focus();
  }

  function statusKeydown(event) {
    if(el.statusModal.hidden)return;
    if(event.key==="Escape"){event.preventDefault();closeStatusModal();return;}
    if(event.key==="ArrowDown"){event.preventDefault();focusStatusOption("next");return;}
    if(event.key==="ArrowUp"){event.preventDefault();focusStatusOption("previous");return;}
    if(event.key==="Home"){event.preventDefault();focusStatusOption("first");return;}
    if(event.key==="End"){event.preventDefault();focusStatusOption("last");return;}
    if(event.key==="Tab"){
      const focusable=[el.statusClose,el.statusSearch,...statusButtons()];
      const index=focusable.indexOf(document.activeElement);
      if((event.shiftKey&&index<=0)||(!event.shiftKey&&index===focusable.length-1)){
        event.preventDefault();focusable[event.shiftKey?focusable.length-1:0].focus();
      }
      return;
    }
    const option=STATUS_OPTIONS.find(item=>item.shortcut===event.key);
    if(option&&!event.metaKey&&!event.ctrlKey&&!event.altKey){event.preventDefault();updateStatus(option.value);return;}
    if(event.key==="Enter"&&document.activeElement===el.statusSearch){
      const first=statusButtons()[0]; if(first){event.preventDefault();first.click();}
    }
  }

  function formatTime(value) { return value ? value.slice(0,16).replace("T"," ")+"Z" : "—"; }
  function cell(value,className) { const node=document.createElement("td"); if(className)node.className=className; node.textContent=value; return node; }
  function taskPath(sessionId) { return `tasks/~${encodeURIComponent(sessionId)}${location.search}`; }
  function taskSessionPath(sessionId) { return `codex://threads/${encodeURIComponent(sessionId)}`; }
  function updateSummary() {
    if(!lastSnapshot)return;
    const selected=selectedTasks.size?` · ${selectedTasks.size} selected`:"";
    el.summary.textContent=`${lastSnapshot.visible_count} visible · ${lastSnapshot.total_count} total${selected}`;
  }
  function syncTaskRow(row,thread) {
    const selected=selectedTasks.has(thread.session_id);
    row.setAttribute("aria-selected",selected?"true":"false");
    row.setAttribute("data-active",activeTask&&activeTask.session_id===thread.session_id?"true":"false");
    row.selectionToggle.setAttribute("aria-pressed",selected?"true":"false");
    row.selectionToggle.textContent=selected?"✓":"";
  }
  function setActiveTask(task,focus=false) {
    activeTask=task;
    renderedRows.forEach(row=>syncTaskRow(row,row.task));
    if(!focus)return;
    const row=renderedRows.find(item=>item.task.session_id===task.session_id);
    if(row){row.focus();if(row.scrollIntoView)row.scrollIntoView({block:"nearest"});}
  }
  function toggleTaskSelection(task) {
    if(selectedTasks.has(task.session_id))selectedTasks.delete(task.session_id);
    else selectedTasks.set(task.session_id,task);
    renderedRows.forEach(row=>syncTaskRow(row,row.task));
    updateSummary();
  }
  function moveActiveTask(direction) {
    if(!renderedRows.length)return;
    let index=renderedRows.findIndex(row=>activeTask&&row.task.session_id===activeTask.session_id);
    if(index<0)index=direction==="next"?0:renderedRows.length-1;
    else index=direction==="next"?Math.min(index+1,renderedRows.length-1):Math.max(index-1,0);
    setActiveTask(renderedRows[index].task,true);
  }
  function attachmentMediaType(file) {
    const suffix=file.name.toLocaleLowerCase();
    if(suffix.endsWith(".md")||suffix.endsWith(".markdown"))return "text/markdown";
    if(suffix.endsWith(".txt"))return "text/plain";
    return file.type==="text/markdown"||file.type==="text/plain"?file.type:"";
  }
  function chooseAttachment(task) {
    if(attachmentSaving)return;
    attachmentTask=task;
    el.attachmentPicker.value="";
    el.attachmentPicker.click();
  }
  async function uploadAttachment() {
    const task=attachmentTask; const file=el.attachmentPicker.files&&el.attachmentPicker.files[0];
    attachmentTask=null;
    if(!task||!file)return;
    const mediaType=attachmentMediaType(file);
    if(!mediaType){el.notice.textContent="Choose a Markdown or plain-text file.";el.notice.className="notice error";return;}
    attachmentSaving=true;
    try {
      const response=await fetch(`api/tasks/~${encodeURIComponent(task.session_id)}/attachments`,{
        method:"POST",cache:"no-store",headers:{"Content-Type":mediaType,"X-AgTask-Filename":encodeURIComponent(file.name)},body:file
      });
      const payload=await response.json();
      if(!response.ok)throw new Error(payload.error||`Attachment failed (${response.status})`);
      const refreshed=await load(currentState);
      if(refreshed){el.notice.textContent=`Attached ${file.name} to ${task.title}.`;el.notice.className="notice";}
    } catch (error) {
      el.notice.textContent=error.message; el.notice.className="notice error";
    } finally { attachmentSaving=false; el.attachmentPicker.value=""; }
  }
  function taskSelectionCell(thread) {
    const node=document.createElement("td"); node.className="selection-cell";
    const toggle=document.createElement("button"); toggle.type="button"; toggle.className="selection-toggle";
    toggle.setAttribute("aria-label",`Select ${thread.title}`);
    toggle.addEventListener("click",event=>{event.stopPropagation();setActiveTask(thread);toggleTaskSelection(thread);});
    node.append(toggle); return {node,toggle};
  }
  function taskTitleCell(thread) {
    const node=document.createElement("td"); const link=document.createElement("a");
    node.className="task-title-cell";
    link.className="task-link"; link.href=taskSessionPath(thread.session_id); link.textContent=thread.title;
    link.title="Open task in Codex";
    link.addEventListener("keydown",event=>{if(event.key===" "){event.preventDefault();location.assign(link.href);}});
    const links=[link]; node.append(link);
    if((thread.files||[]).length){
      const badges=document.createElement("span"); badges.className="task-file-badges";
      thread.files.forEach(file=>{
        const badge=document.createElement("a"); badge.className="file-badge"; badge.href=file.url; badge.textContent="file"; badge.title=`Open ${file.path} in VS Code`;
        badges.append(badge); links.push(badge);
      });
      node.append(badges);
    }
    return {node,links};
  }
  function taskIdentityCell(value,label,className="") {
    const node=document.createElement("td"); node.className=className;
    if(!value){node.textContent="—";return {node,button:null};}
    const button=document.createElement("button"); button.type="button"; button.className="identity-copy";
    button.textContent=value.slice(0,8); button.title=`Copy full ${label}`; button.setAttribute("aria-label",`Copy full ${label} ${value}`);
    button.addEventListener("click",async event=>{
      event.stopPropagation();
      try {
        if(!navigator.clipboard||typeof navigator.clipboard.writeText!=="function")throw new Error("Clipboard access is unavailable.");
        await navigator.clipboard.writeText(value);
        el.notice.textContent=`Copied full ${label}.`; el.notice.className="notice";
      } catch (error) {
        el.notice.textContent=error.message||`Could not copy ${label}.`; el.notice.className="notice error";
      }
    });
    node.append(button); return {node,button};
  }
  function taskRow(thread,links,selectionToggle) {
    const row=document.createElement("tr"); row.className="task-row"; row.setAttribute("data-task-id",thread.id); row.setAttribute("data-session-id",thread.session_id); row.setAttribute("data-status",thread.status);
    row.tabIndex=-1; row.task=thread; row.selectionToggle=selectionToggle;
    row.addEventListener("click",event=>{if(!links.some(link=>link.contains(event.target)))location.assign(taskPath(thread.session_id));});
    row.addEventListener("mouseenter",()=>{hoveredTask=thread;setActiveTask(thread);});
    row.addEventListener("mouseleave",()=>{if(hoveredTask&&hoveredTask.session_id===thread.session_id)hoveredTask=null;});
    row.addEventListener("focusin",()=>{setActiveTask(thread);});
    row.addEventListener("focusout",event=>{if(!row.contains(event.relatedTarget)&&hoveredTask&&hoveredTask.session_id===thread.session_id)hoveredTask=null;});
    renderedRows.push(row); syncTaskRow(row,thread);
    return row;
  }

  function emptyState(title,message,buttonLabel,onChoose) {
    const section=document.createElement("section"); section.className="empty-state";
    const heading=document.createElement("h2"); heading.textContent=title;
    const copy=document.createElement("p"); copy.textContent=message;
    const button=document.createElement("button"); button.type="button"; button.textContent=buttonLabel; button.addEventListener("click",onChoose);
    section.append(heading,copy,button); return section;
  }

  function clearFiltersAndSearch() {
    currentState={...currentState,projects:[],parents:[],root:false,statuses:[],search:""};
    el.search.value=""; renderActiveFilters(); closeFilterMenu(false); load(currentState);
  }

  function renderGroups(snapshot) {
    hoveredTask=null;
    renderedRows=[];
    const visibleTasks=snapshot.groups.flatMap(group=>group.threads);
    const visibleBySession=new Map(visibleTasks.map(task=>[task.session_id,task]));
    selectedTasks=new Map([...selectedTasks].flatMap(([sessionId])=>visibleBySession.has(sessionId)?[[sessionId,visibleBySession.get(sessionId)]]:[]));
    activeTask=activeTask&&visibleBySession.get(activeTask.session_id)||null;
    if(snapshot.total_count===0){
      el.groups.replaceChildren(emptyState("No tracked tasks yet","Create or register a task, then refresh this dashboard.","Refresh",()=>load(currentState)));
      return;
    }
    if(snapshot.visible_count===0&&(FILTER_DEFS.some(definition=>filterValues(definition).length)||currentState.search)){
      el.groups.replaceChildren(emptyState("No tasks match this view","Try another filter or clear the current filters and task search.","Clear filters and search",clearFiltersAndSearch));
      return;
    }
    const sections=snapshot.groups.map(group=>{
      const section=document.createElement("section");section.className="group";section.setAttribute("aria-labelledby",`status-${group.status}`);
      const header=document.createElement("div");header.className="group-header";const heading=document.createElement("h2");heading.id=`status-${group.status}`;heading.textContent=STATUS_LABELS[group.status]||group.status;
      const badge=document.createElement("span");badge.className="badge";badge.textContent=String(group.count);header.append(heading,badge);section.append(header);
      if(!group.threads.length){const empty=document.createElement("p");empty.className="empty";empty.textContent="No tasks in this status.";section.append(empty);return section;}
      const wrapper=document.createElement("div");wrapper.className="table-wrap";const table=document.createElement("table");const thead=document.createElement("thead");const headingRow=document.createElement("tr");
      [["","selection-cell"],["Task ID",""],["Codex SHA",""],["Title",""],["Project",""],["Parent task","optional-parent"],["Created","optional-time"],["Updated","optional-time"],["Closed","optional-time"]].forEach(([label,className])=>{const th=document.createElement("th");th.scope="col";th.className=className;th.textContent=label;if(!label)th.setAttribute("aria-label","Task selection");headingRow.append(th);});thead.append(headingRow);table.append(thead);
      const tbody=document.createElement("tbody");group.threads.forEach(thread=>{const selection=taskSelectionCell(thread);const taskId=taskIdentityCell(thread.id,"Task ID");const sessionId=taskIdentityCell(thread.session_id,"Codex SHA");const title=taskTitleCell(thread);const parentId=taskIdentityCell(thread.parent_session_id,"Parent task ID","optional-parent");const row=taskRow(thread,[selection.toggle,taskId.button,sessionId.button,parentId.button,...title.links].filter(Boolean),selection.toggle);row.append(selection.node,taskId.node,sessionId.node,title.node,cell(thread.project),parentId.node,cell(formatTime(thread.created),"optional-time"),cell(formatTime(thread.updated),"optional-time"),cell(formatTime(thread.closed),"optional-time"));tbody.append(row);});table.append(tbody);wrapper.append(table);section.append(wrapper);return section;
    });
    el.groups.replaceChildren(...sections);
  }

  function render(snapshot) {
    currentState=stateFromSnapshot(snapshot); lastSnapshot=snapshot;
    const acceptedQuery=acceptedQueryFor(currentState);
    history.replaceState(null,"",acceptedQuery?`?${acceptedQuery}`:location.pathname);
    el.search.value=currentState.search; el.sort.value=currentState.sort; el.direction.value=currentState.direction;
    renderViewTabs(snapshot); renderActiveFilters(); renderGroups(snapshot); if(!el.filterMenu.hidden)renderFilterMenu(); el.groups.setAttribute("aria-busy","false");
    updateSummary();
    el.notice.textContent=`Updated ${new Date().toLocaleTimeString()}`; el.notice.className="notice";
  }

  async function load(state,updateUrl=true,initialQuery=null) {
    const query=initialQuery===null?queryFor(state):initialQuery; const generation=++requestGeneration;
    if(updateUrl)history.replaceState(null,"",query?`?${query}`:location.pathname);
    el.groups.setAttribute("aria-busy","true");
    try{
      const response=await fetch(`api/dashboard${query?`?${query}`:""}`,{cache:"no-store"}); const payload=await response.json();
      if(!response.ok)throw new Error(payload.error||`Dashboard request failed (${response.status})`);
      if(generation===requestGeneration){render(payload);return true;}
      return false;
    }catch(error){
      if(generation!==requestGeneration)return false; el.groups.setAttribute("aria-busy","false");
      el.notice.textContent=`${lastSnapshot?"Showing the last successful snapshot. ":""}${error.message}`; el.notice.className="notice error";
      return false;
    }
  }

  el.filterTrigger.addEventListener("click",()=>el.filterMenu.hidden?openFilterMenu(el.filterTrigger):closeFilterMenu());
  el.addFilter.addEventListener("click",()=>el.filterMenu.hidden?openFilterMenu(el.addFilter):closeFilterMenu());
  el.filterMenuBack.addEventListener("click",()=>{menuField=null;el.filterMenuSearch.value="";renderFilterMenu();el.filterMenuSearch.focus();});
  el.filterMenuClose.addEventListener("click",()=>closeFilterMenu());
  el.filterMenuSearch.addEventListener("input",renderFilterMenu);
  el.filterMenu.addEventListener("keydown",menuKeydown);
  document.addEventListener("pointerdown",event=>{if(!el.filterMenu.hidden&&!el.filterMenu.contains(event.target)&&!el.filterTrigger.contains(event.target)&&!el.addFilter.contains(event.target))closeFilterMenu(false);});
  el.statusClose.addEventListener("click",()=>closeStatusModal());
  el.statusSearch.addEventListener("input",renderStatusOptions);
  el.statusModal.addEventListener("keydown",statusKeydown);
  el.statusModal.addEventListener("pointerdown",event=>{if(event.target===el.statusModal)closeStatusModal();});
  el.attachmentPicker.addEventListener("change",uploadAttachment);
  document.addEventListener("keydown",event=>{
    const key=event.key.toLocaleLowerCase();
    if(event.metaKey||event.ctrlKey||event.altKey||event.defaultPrevented)return;
    if(!el.statusModal.hidden||!el.filterMenu.hidden||isTypingTarget(event.target))return;
    if(key==="j"||key==="k"){event.preventDefault();moveActiveTask(key==="j"?"next":"previous");return;}
    const target=activeTask||hoveredTask;
    if(key==="x"&&target){event.preventDefault();toggleTaskSelection(target);return;}
    if(key==="a"&&target){event.preventDefault();chooseAttachment(target);return;}
    if(key==="s"){
      const tasks=selectedTasks.size?[...selectedTasks.values()]:(target?[target]:[]);
      if(tasks.length){event.preventDefault();openStatusModal(tasks);}
    }
  });
  el.refresh.addEventListener("click",()=>load(currentState));
  el.sort.addEventListener("change",()=>{currentState={...currentState,sort:el.sort.value};load(currentState);});
  el.direction.addEventListener("change",()=>{currentState={...currentState,direction:el.direction.value};load(currentState);});
  el.search.addEventListener("input",()=>{currentState={...currentState,search:el.search.value};clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>load(currentState),180);});
  renderActiveFilters(); el.search.value=currentState.search; el.sort.value=currentState.sort; el.direction.value=currentState.direction;
  load(currentState,false,location.search.slice(1));
})();
