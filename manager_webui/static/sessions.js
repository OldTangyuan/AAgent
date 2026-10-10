import { createSession, deleteSession, fetchSession, fetchSessions, updateSession } from './api.js';

const elements = Object.fromEntries([
  'createButton', 'searchInput', 'searchButton', 'sessionList', 'listStatus', 'moreButton',
  'detailTitle', 'timestamp', 'copyButton', 'refreshButton', 'deleteButton', 'sessionForm',
  'valueType', 'valueInput', 'valueHint', 'formStatus', 'cancelButton', 'emptyDetail',
].map((id) => [id, document.getElementById(id)]));

let current = null;
let creating = false;
let nextCursor = null;
let query = '';
let listGeneration = 0;
let detailGeneration = 0;
let busy = false;

function report(message) { elements.formStatus.textContent = message; }
function setBusy(value) { busy = value; elements.sessionForm.dataset.busy = String(value); }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : ''; }
function updateSelection() {
  for (const button of elements.sessionList.querySelectorAll('[data-id]')) {
    button.classList.toggle('selected', button.dataset.id === current?.id && !creating);
  }
}
function showDetail() {
  elements.sessionForm.hidden = !current && !creating;
  elements.emptyDetail.hidden = Boolean(current || creating);
  elements.detailTitle.textContent = creating ? '新建 Session' : current?.id || '选择 Session';
  elements.timestamp.textContent = current ? `创建 ${formatDate(current.created_at)}  ·  更新 ${formatDate(current.updated_at)}` : '';
  elements.copyButton.disabled = !current || creating;
  elements.refreshButton.disabled = !current || creating;
  elements.deleteButton.disabled = !current || creating;
  elements.valueType.disabled = Boolean(current);
  elements.valueHint.textContent = elements.valueType.value === 'content' ? '文本' : 'JSON';
  updateSelection();
}
function displayValue(valueType, value) {
  return valueType === 'content' ? value : JSON.stringify(value, null, 2);
}
function parseValue() {
  if (elements.valueType.value === 'content') return elements.valueInput.value;
  try { return JSON.parse(elements.valueInput.value); }
  catch { throw new Error('请输入有效的 JSON 值'); }
}
async function loadList(append = false) {
  const generation = ++listGeneration;
  const cursor = append ? nextCursor : '';
  if (append && !cursor) return;
  elements.listStatus.textContent = '读取中';
  elements.moreButton.hidden = true;
  try {
    const page = await fetchSessions(cursor, query);
    if (generation !== listGeneration) return;
    if (!append) elements.sessionList.replaceChildren();
    for (const item of page.items) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'session-item';
      button.dataset.id = item.id;
      const title = document.createElement('strong');
      title.textContent = item.id;
      const meta = document.createElement('small');
      meta.textContent = `${item.value_type}  ·  ${formatDate(item.updated_at)}`;
      button.append(title, meta);
      button.addEventListener('click', () => openSession(item.id));
      elements.sessionList.append(button);
    }
    nextCursor = page.next_cursor;
    elements.moreButton.hidden = !nextCursor;
    elements.listStatus.textContent = `${elements.sessionList.children.length} 条${nextCursor ? '（更多可加载）' : ''}`;
    updateSelection();
  } catch (error) {
    if (generation === listGeneration) {
      elements.listStatus.textContent = error.message;
      elements.moreButton.hidden = !nextCursor;
    }
  }
}
async function openSession(id) {
  if (busy) return;
  const generation = ++detailGeneration;
  elements.listStatus.textContent = '读取中';
  report('读取中');
  try {
    const document = await fetchSession(id);
    if (generation !== detailGeneration) return;
    current = document;
    creating = false;
    elements.valueType.value = document.value_type;
    elements.valueInput.value = displayValue(document.value_type, document.value);
    report('');
    showDetail();
    elements.listStatus.textContent = '';
  } catch (error) {
    if (generation === detailGeneration) { report(error.message); elements.listStatus.textContent = error.message; }
  }
}

elements.searchButton.addEventListener('click', () => {
  query = elements.searchInput.value.trim();
  nextCursor = null;
  loadList();
});
elements.searchInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); elements.searchButton.click(); }
});
elements.moreButton.addEventListener('click', () => loadList(true));
elements.createButton.addEventListener('click', () => {
  if (busy) return;
  ++detailGeneration;
  current = null;
  creating = true;
  elements.valueType.value = 'content';
  elements.valueInput.value = '';
  report('');
  showDetail();
  elements.valueInput.focus();
});
elements.valueType.addEventListener('change', () => {
  elements.valueHint.textContent = elements.valueType.value === 'content' ? '文本' : 'JSON';
  if (creating) elements.valueInput.value = elements.valueType.value === 'content' ? '' : elements.valueType.value.startsWith('list-') ? '[]' : '{}';
});
elements.cancelButton.addEventListener('click', () => {
  if (busy) return;
  if (creating) { creating = false; showDetail(); return; }
  if (current) elements.valueInput.value = displayValue(current.value_type, current.value);
  report('');
});
elements.copyButton.addEventListener('click', async () => {
  if (!current) return;
  try { await navigator.clipboard.writeText(current.id); report('ID 已复制'); }
  catch { report('复制失败'); }
});
elements.refreshButton.addEventListener('click', () => { if (current && !busy) openSession(current.id); });
elements.deleteButton.addEventListener('click', async () => {
  if (!current || busy || !window.confirm(`删除 Session ${current.id}？此操作不可撤销。`)) return;
  setBusy(true);
  try {
    await deleteSession(current.id);
    ++detailGeneration;
    current = null;
    report('');
    showDetail();
    await loadList();
  } catch (error) { report(error.message); }
  finally { setBusy(false); }
});
elements.sessionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  let value;
  try { value = parseValue(); }
  catch (error) { report(error.message); return; }
  setBusy(true);
  report('保存中');
  try {
    const document = creating
      ? await createSession(elements.valueType.value, value)
      : await updateSession(current.id, current.value_type, value, current.updated_at);
    current = document;
    creating = false;
    elements.valueInput.value = displayValue(document.value_type, document.value);
    showDetail();
    report('已保存');
    await loadList();
  } catch (error) { report(error.message); }
  finally { setBusy(false); }
});

showDetail();
loadList();