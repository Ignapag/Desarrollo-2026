// DOM mínimo para ejecutar el reconciliador y hooks de React reales en Node.
// Los tests invocan los handlers publicados por React; no simulan eventos del navegador.
export function installMinimalDom() {
  const previous = new Map();
  const setGlobal = (key, value) => { previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, { configurable: true, writable: true, value }); };
  class Node {
    constructor(nodeType, nodeName, ownerDocument) {
      Object.assign(this, { nodeType, nodeName, ownerDocument, parentNode: null, childNodes: [] });
    }
    appendChild(child) { if (child.parentNode) child.parentNode.removeChild(child); this.childNodes.push(child); child.parentNode = this; return child; }
    removeChild(child) { this.childNodes.splice(this.childNodes.indexOf(child), 1); child.parentNode = null; return child; }
    insertBefore(child, before) { if (child.parentNode) child.parentNode.removeChild(child); this.childNodes.splice(this.childNodes.indexOf(before), 0, child); child.parentNode = this; return child; }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes.at(-1) || null; }
    get nextSibling() { return this.parentNode?.childNodes[this.parentNode.childNodes.indexOf(this) + 1] || null; }
    get textContent() { return this.childNodes.map((child) => child.textContent).join(''); }
    set textContent(value) { this.childNodes = []; if (value !== '') this.appendChild(this.ownerDocument.createTextNode(String(value))); }
    addEventListener() {}
    removeEventListener() {}
    contains(node) { return this === node || this.childNodes.some((child) => child.contains?.(node)); }
  }
  class Element extends Node {
    constructor(tag, ownerDocument, namespaceURI = 'http://www.w3.org/1999/xhtml') {
      super(1, tag.toUpperCase(), ownerDocument);
      Object.assign(this, { tagName: this.nodeName, localName: tag.toLowerCase(), namespaceURI, attributes: new Map(), style: { setProperty(key, value) { this[key] = value; }, removeProperty(key) { delete this[key]; } }, value: '', checked: false, disabled: false, selected: false, multiple: false, open: false });
    }
    setAttribute(key, value) { this.attributes.set(key, String(value)); if (key === 'disabled') this.disabled = true; }
    removeAttribute(key) { this.attributes.delete(key); if (key === 'disabled') this.disabled = false; }
    getAttribute(key) { return this.attributes.get(key) ?? null; }
    hasAttribute(key) { return this.attributes.has(key); }
    setAttributeNS(_ns, key, value) { this.setAttribute(key, value); }
    removeAttributeNS(_ns, key) { this.removeAttribute(key); }
    get options() { return this.childNodes.flatMap((child) => child.localName === 'option' ? [child] : child.options || []); }
    focus() { this.ownerDocument.activeElement = this; }
    blur() { if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body; }
    showModal() { this.open = true; }
    close() { this.open = false; }
  }
  class Text extends Node {
    constructor(value, ownerDocument) { super(3, '#text', ownerDocument); this.nodeValue = value; }
    get textContent() { return this.nodeValue; }
    set textContent(value) { this.nodeValue = String(value); }
  }
  class Document extends Node {
    constructor() {
      super(9, '#document', null);
      this.ownerDocument = this;
      this.documentElement = new Element('html', this);
      this.body = new Element('body', this);
      this.documentElement.appendChild(this.body);
      this.appendChild(this.documentElement);
      this.activeElement = this.body;
      this.hidden = false;
    }
    createElement(tag) { return new Element(tag, this); }
    createElementNS(ns, tag) { return new Element(tag, this, ns); }
    createTextNode(value) { return new Text(String(value), this); }
  }
  const document = new Document();
  const window = { document, Node, HTMLElement: Element, HTMLIFrameElement: class extends Element {}, setInterval, clearInterval, setTimeout, clearTimeout, addEventListener() {}, removeEventListener() {} };
  document.defaultView = window;
  setGlobal('window', window);
  setGlobal('document', document);
  setGlobal('HTMLElement', Element);
  setGlobal('Node', Node);
  setGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  return {
    document,
    restore() { for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } },
  };
}

export function elements(node, predicate) {
  return [node, ...(node.childNodes || []).flatMap((child) => elements(child, predicate))].filter(predicate);
}

export function reactProps(node) {
  return node[Object.keys(node).find((key) => key.startsWith('__reactProps$'))] || {};
}

export function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}
