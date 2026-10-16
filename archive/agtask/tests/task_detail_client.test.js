"use strict";

const assert = require("node:assert/strict");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this._text = "";
    this.className = "";
    this.dateTime = "";
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  get textContent() {
    return this._text + this.children.map(child => child.textContent).join("");
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
    this._text = "";
  }

  setAttribute(name,value) {
    this.attributes.set(name,String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }
}

class FakeTextNode {
  constructor(value) {
    this._text = String(value);
    this.children = [];
  }

  get textContent() {
    return this._text;
  }
}

class FakeDocumentFragment extends FakeElement {
  constructor() {
    super("#document-fragment");
  }

  get childNodes() {
    return this.children;
  }
}

class FakeDocument {
  constructor(ids) {
    this.title = "Task detail · agtask";
    this.elements = Object.fromEntries(ids.map(id => [id,new FakeElement("div")]));
    this.listeners = new Map();
  }

  getElementById(id) {
    return this.elements[id];
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }

  createTextNode(value) {
    return new FakeTextNode(value);
  }

  createDocumentFragment() {
    return new FakeDocumentFragment();
  }

  addEventListener(type,listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type,listeners);
  }

  dispatchEvent(event) {
    for (const listener of this.listeners.get(event.type) || [])listener(event);
  }
}

function descendants(root,tagName) {
  const matches = [];
  for (const child of root.children || []) {
    if (child.tagName === tagName.toUpperCase())matches.push(child);
    matches.push(...descendants(child,tagName));
  }
  return matches;
}

async function settle() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}

async function main() {
  const input = JSON.parse(await new Promise(resolve => {
    let value = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data",chunk => { value += chunk; });
    process.stdin.on("end",() => resolve(value));
  }));
  const document = new FakeDocument([
    "back-link", "detail-content", "task-title", "task-description", "task-created",
    "task-updated", "task-session-id", "task-files-property", "task-files",
    "timeline", "detail-notice"
  ]);
  const requests = [];
  const navigations = [];
  global.document = document;
  global.location = {
    pathname:"/token/tasks/~alpha-active",
    search:"?view=today",
    href:"http://127.0.0.1/token/tasks/~alpha-active?view=today",
    origin:"http://127.0.0.1",
    assign:path => { navigations.push(path); }
  };
  global.fetch = async url => {
    requests.push(url);
    return {ok:true,status:200,json:async()=>input.detail};
  };

  input.detail.description = "Read the [guide](https://example.com/guide) and [local notes](../notes), then use `agtask show`.\n\n**Keep** the ledger safe.";
  input.detail.rollouts[0].message = [
    "Rendered *timeline* content:",
    "",
    "- first item",
    "- second item",
    "",
    "> quoted guidance",
    "",
    "```js",
    "const result = '<safe>';",
    "```",
    "",
    "[javascript](javascript:alert(1)) [data](data:text/html;base64,WA==) [vbscript](vbscript:msgbox(1)) <img src=x onerror=alert(1)>"
  ].join("\n");
  vm.runInThisContext(input.markedSource,{filename:"served-marked.js"});
  vm.runInThisContext(input.source,{filename:"served-task-detail.js"});
  await settle();

  assert.deepEqual(requests,["../api/tasks/~alpha-active"]);
  assert.equal(document.getElementById("back-link").href,"../?view=today");
  assert.equal(document.title,"Polish Dashboard · agtask");
  assert.equal(document.getElementById("task-title").textContent,"Polish Dashboard");
  const description = document.getElementById("task-description");
  assert.equal(description.textContent,"Read the guide and local notes, then use agtask show.Keep the ledger safe.");
  assert.equal(descendants(description,"P").length,2);
  assert.equal(descendants(description,"CODE").length,1);
  assert.equal(descendants(description,"STRONG").length,1);
  const [externalLink,localLink] = descendants(description,"A");
  assert.equal(externalLink.getAttribute("href"),"https://example.com/guide");
  assert.equal(externalLink.getAttribute("target"),"_blank");
  assert.equal(externalLink.getAttribute("rel"),"noopener noreferrer");
  assert.equal(localLink.getAttribute("href"),"../notes");
  assert.equal(localLink.getAttribute("target"),null);
  assert.equal(localLink.getAttribute("rel"),null);
  assert.equal(document.getElementById("task-session-id").textContent,"alpha-active");
  assert.equal(document.getElementById("task-session-id").href,"codex://threads/alpha-active");
  assert.equal(document.getElementById("task-session-id").title,"Open task in Codex");
  assert.equal(document.getElementById("task-files-property").hidden,false);
  const fileBadge = document.getElementById("task-files").children[0];
  assert.equal(fileBadge.textContent,"file");
  assert.equal(fileBadge.href,input.detail.files[0].url);
  assert.match(fileBadge.title,/dashboard task\.md/);
  assert.equal(document.getElementById("detail-content").getAttribute("aria-busy"),"false");
  const timeline = document.getElementById("timeline");
  assert.equal(timeline.children.length,input.detail.rollouts.length);
  assert.match(timeline.children[0].textContent,/assistant:Rendered timeline content:/);
  const renderedMessage = timeline.children[0].children[2];
  assert.equal(renderedMessage.tagName,"DIV");
  assert.equal(descendants(renderedMessage,"UL").length,1);
  assert.equal(descendants(renderedMessage,"LI").length,2);
  assert.equal(descendants(renderedMessage,"EM").length,1);
  assert.equal(descendants(renderedMessage,"BLOCKQUOTE").length,1);
  assert.equal(descendants(renderedMessage,"PRE").length,1);
  assert.equal(descendants(renderedMessage,"SCRIPT").length,0);
  assert.equal(descendants(renderedMessage,"IMG").length,0);
  assert.equal(descendants(renderedMessage,"A").length,0);
  assert.match(renderedMessage.textContent,/javascript data vbscript <img src=x onerror=alert\(1\)>/);
  assert.match(timeline.children[1].textContent,/user:First timeline entry/);
  assert.equal(document.getElementById("detail-notice").textContent,"");
  document.dispatchEvent({type:"keydown",key:"Enter"});
  assert.deepEqual(navigations,[]);
  let prevented = false;
  document.dispatchEvent({
    type:"keydown",
    key:"Escape",
    preventDefault:() => { prevented = true; }
  });
  assert.equal(prevented,true);
  assert.deepEqual(navigations,["../?view=today"]);
  process.stdout.write("task detail client passed\n");
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
