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

  addEventListener(type,listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type,listeners);
  }

  dispatchEvent(event) {
    for (const listener of this.listeners.get(event.type) || [])listener(event);
  }
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
    "detail-content", "task-title", "task-description", "task-created",
    "task-updated", "task-session-id", "task-files-property", "task-files",
    "timeline", "detail-notice"
  ]);
  const requests = [];
  const navigations = [];
  global.document = document;
  global.location = {
    pathname:"/token/tasks/~alpha-active",
    assign:path => { navigations.push(path); }
  };
  global.fetch = async url => {
    requests.push(url);
    return {ok:true,status:200,json:async()=>input.detail};
  };

  vm.runInThisContext(input.source,{filename:"served-task-detail.js"});
  await settle();

  assert.deepEqual(requests,["../api/tasks/~alpha-active"]);
  assert.equal(document.title,"Polish Dashboard · agtask");
  assert.equal(document.getElementById("task-title").textContent,"Polish Dashboard");
  assert.equal(document.getElementById("task-description").textContent,"dashboard fixture");
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
  assert.match(timeline.children[0].textContent,/assistant:Newest timeline entry/);
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
  assert.deepEqual(navigations,["../"]);
  process.stdout.write("task detail client passed\n");
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
