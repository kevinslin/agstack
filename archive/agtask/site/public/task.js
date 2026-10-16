(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const dashboardPath = `../${location.search}`;
  byId("back-link").href=dashboardPath;
  const pathParts = location.pathname.split("/").filter(Boolean);
  let sessionId;
  const markedSessionId = pathParts.at(-1)||"";
  try {
    if(!markedSessionId.startsWith("~"))throw new Error("missing task marker");
    sessionId = decodeURIComponent(markedSessionId.slice(1));
  }
  catch { showError("Invalid task URL."); return; }

  function formatTime(value) { return value ? value.slice(0,19).replace("T"," ")+" Z" : "—"; }
  function showError(message) {
    byId("task-title").textContent="Task unavailable";
    byId("detail-notice").textContent=message;
    byId("detail-content").setAttribute("aria-busy","false");
  }
  function appendText(parent,value) { parent.append(document.createTextNode(String(value||""))); }
  function safeLink(rawHref) {
    if(typeof rawHref!=="string")return null;
    const href=rawHref.trim();
    if(!href||Array.from(href).some(character=>character.charCodeAt(0)<=31||character.charCodeAt(0)===127))return null;
    let parsed;
    try { parsed=new URL(href,location.href); } catch { return null; }
    if(!["http:","https:","mailto:"].includes(parsed.protocol))return null;
    return {href,external:(parsed.protocol==="http:"||parsed.protocol==="https:")&&parsed.origin!==location.origin};
  }
  function renderInline(tokens,parent) {
    for(const token of tokens||[]){
      if(token.type==="text"||token.type==="escape"){
        if(token.tokens)renderInline(token.tokens,parent);else appendText(parent,token.text); continue;
      }
      if(token.type==="strong"||token.type==="em"||token.type==="del"){
        const node=document.createElement(token.type==="del"?"del":token.type); renderInline(token.tokens,node); parent.append(node); continue;
      }
      if(token.type==="codespan"){
        const code=document.createElement("code"); code.textContent=token.text; parent.append(code); continue;
      }
      if(token.type==="br"){parent.append(document.createElement("br"));continue;}
      if(token.type==="link"){
        const link= safeLink(token.href);
        if(!link){renderInline(token.tokens,parent);continue;}
        const anchor=document.createElement("a"); anchor.setAttribute("href",link.href); renderInline(token.tokens,anchor);
        if(link.external){anchor.setAttribute("target","_blank");anchor.setAttribute("rel","noopener noreferrer");}
        parent.append(anchor); continue;
      }
      if(token.type==="image"){appendText(parent,token.text||"");continue;}
      appendText(parent,token.text??token.raw??"");
    }
  }
  function renderBlocks(tokens,parent) {
    for(const token of tokens||[]){
      if(token.type==="space")continue;
      if(token.type==="paragraph"||token.type==="text"){
        const paragraph=document.createElement("p");
        if(token.tokens)renderInline(token.tokens,paragraph);else appendText(paragraph,token.text??token.raw);
        parent.append(paragraph); continue;
      }
      if(token.type==="heading"){
        const heading=document.createElement(`h${Math.min(6,Math.max(1,token.depth||1))}`); renderInline(token.tokens,heading); parent.append(heading); continue;
      }
      if(token.type==="code"){
        const pre=document.createElement("pre"); const code=document.createElement("code"); code.textContent=token.text||""; pre.append(code); parent.append(pre); continue;
      }
      if(token.type==="blockquote"){
        const quote=document.createElement("blockquote"); renderBlocks(token.tokens,quote); parent.append(quote); continue;
      }
      if(token.type==="list"){
        const list=document.createElement(token.ordered?"ol":"ul");
        if(token.ordered&&Number.isInteger(token.start)&&token.start!==1)list.setAttribute("start",token.start);
        for(const item of token.items||[]){const entry=document.createElement("li");renderBlocks(item.tokens,entry);list.append(entry);}
        parent.append(list); continue;
      }
      if(token.type==="hr"){parent.append(document.createElement("hr"));continue;}
      const fallback=document.createElement("p"); appendText(fallback,token.raw??token.text??""); parent.append(fallback);
    }
  }
  function renderMarkdown(target,source) {
    if(!globalThis.marked||typeof globalThis.marked.lexer!=="function")throw new Error("Markdown renderer unavailable");
    const fragment=document.createDocumentFragment();
    renderBlocks(globalThis.marked.lexer(String(source||""),{gfm:true}),fragment);
    target.replaceChildren(...fragment.childNodes);
  }
  function timelineItem(rollout) {
    const item=document.createElement("li"); item.className="timeline-item";
    const time=document.createElement("time"); time.className="timeline-time"; time.dateTime=rollout.created; time.textContent=formatTime(rollout.created);
    const role=document.createElement("span"); role.className="timeline-role"; role.textContent=`${rollout.role}:`;
    const message=document.createElement("div"); message.className="timeline-message markdown-body"; renderMarkdown(message,rollout.message);
    item.append(time,role,message); return item;
  }
  function fileBadge(file) {
    const badge=document.createElement("a"); badge.className="file-badge"; badge.href=file.url; badge.textContent="file"; badge.title=`Open ${file.path} in VS Code`; return badge;
  }
  function render(task) {
    document.title=`${task.title} · agtask`;
    byId("task-title").textContent=task.title;
    renderMarkdown(byId("task-description"),task.description||"No description provided.");
    byId("task-created").textContent=formatTime(task.created);
    byId("task-updated").textContent=formatTime(task.updated);
    const sessionLink=byId("task-session-id");
    sessionLink.textContent=task.session_id;
    sessionLink.href=`codex://threads/${encodeURIComponent(task.session_id)}`;
    sessionLink.title="Open task in Codex";
    const files=task.files||[];
    byId("task-files-property").hidden=!files.length;
    byId("task-files").replaceChildren(...files.map(fileBadge));
    const items=task.rollouts.map(timelineItem);
    if(!items.length){const empty=document.createElement("li");empty.className="timeline-empty";empty.textContent="No rollout items yet.";items.push(empty);}
    byId("timeline").replaceChildren(...items);
    byId("detail-content").setAttribute("aria-busy","false");
  }
  async function load() {
    try {
      const response=await fetch(`../api/tasks/~${encodeURIComponent(sessionId)}`,{cache:"no-store"});
      const payload=await response.json();
      if(!response.ok)throw new Error(payload.error||`Task request failed (${response.status})`);
      render(payload);
    } catch (error) { showError(error.message); }
  }
  document.addEventListener("keydown",event=>{
    if(event.key!=="Escape")return;
    event.preventDefault();
    location.assign(dashboardPath);
  });
  load();
})();
