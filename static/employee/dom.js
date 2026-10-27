/** Small DOM helpers shared by employee modules. */
export function createElement(tagName, options = {}, children = []) {
    const node = document.createElement(tagName);
    const { className, text, attrs, dataset } = options;
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    Object.entries(attrs || {}).forEach(([name, value]) => {
        if (value !== undefined && value !== null && value !== false) node.setAttribute(name, value === true ? '' : String(value));
    });
    Object.entries(dataset || {}).forEach(([name, value]) => {
        if (value !== undefined && value !== null) node.dataset[name] = String(value);
    });
    const list = Array.isArray(children) ? children : [children];
    list.filter(child => child !== undefined && child !== null).forEach(child => {
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return node;
}

export function appendLabeledValue(parent, label, value) {
    const row = createElement('div');
    row.append(createElement('strong', { text: `${label}:` }), document.createTextNode(` ${value}`));
    parent.append(row);
    return row;
}

export function showMessage(node, message, type = 'muted') {
    node.replaceChildren(createElement('p', { className: `message message-${type}`, text: message }));
}
