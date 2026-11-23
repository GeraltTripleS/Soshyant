'use strict';
const $ = id => document.getElementById(id);
const state = {account: null, csrf: '', status: null, conversation: null, messages: [], job: null, setup: false, view: 'chat'};
const titles = {dashboard: 'Knowledge overview', watched: 'Watched folders', groups: 'Access groups', reviews: 'Answer review', chat: 'گفت‌وگو با دانش شما', documents: 'کتابخانه اسناد', domain: 'تنظیم تخصص', users: 'مدیریت کاربران', maintenance: 'نگهداری و حساب', capacity: 'Hardware planner', models:'Language models'};
const statusNames = {pending: 'در انتظار نمایه', indexing: 'در حال پردازش', indexed: 'آماده پاسخ', failed: 'نیاز به بررسی', restricted: 'Restricted access', stopped: 'در انتظار پرسش', loading: 'در حال بارگذاری', ready: 'آماده', clarify: 'نیاز به توضیح', insufficient: 'اطلاعات ناکافی', answered: 'پاسخ مستند'};
let toastTimer;
let pendingDocumentDelete = null, documentDeleting = false;

function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {$('toast').hidden = true;}, 6000);
}

async function api(path, {method = 'GET', data, raw} = {}) {
  const headers = {};
  if (method !== 'GET') headers['X-CSRF-Token'] = state.csrf;
  let body;
  if (raw !== undefined) {
    headers['Content-Type'] = 'application/octet-stream';
    body = raw;
  } else if (data !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(data);
  }
  const response = await fetch(path, {method, headers, body, credentials: 'same-origin'});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || t('درخواست انجام نشد. دوباره تلاش کنید.'));
  return result;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(text, action, className = 'quiet') {
  const node = element('button', className, text);
  node.type = 'button';
  node.onclick = async () => {
    node.disabled = true;
    try {await action(node);} catch (error) {toast(error.message);}
    finally {node.disabled = false;}
  };
  return node;
}

function showView(name) {
  document.body.classList.remove('navigation-open');
  $('menuToggle').setAttribute('aria-expanded', 'false');
  if (name !== 'chat') window.expertSpeech?.cancel();
  state.view = name;
  for (const view of document.querySelectorAll('.view')) view.hidden = view.id !== 'view-' + name;
  for (const tab of document.querySelectorAll('[data-view]')) tab.classList.toggle('active', tab.dataset.view === name);
  $('viewTitle').textContent = t(titles[name]);
  for (const tab of document.querySelectorAll('[data-view]')) {
    if (tab.dataset.view === name) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  }
  const selectedSettings = document.querySelector('.nav-settings [data-view="' + name + '"]');
  if (selectedSettings) selectedSettings.closest('details').open = true;
  if (name === 'dashboard') loadDashboard().catch(error => toast(error.message));
  if (name === 'watched') loadWatched().catch(error => toast(error.message));
  if (name === 'reviews') loadReviews().catch(error => toast(error.message));
  if (name === 'documents') loadDocuments().catch(error => toast(error.message));
  if (name === 'groups') loadAccessGroups().catch(error => toast(error.message));
  if (name === 'users') loadUsers().catch(error => toast(error.message));
  if (name === 'maintenance') refreshStatus().catch(error => toast(error.message));
  if (name === 'capacity') window.initializeCapacity?.();
  if (name === 'models') window.loadLocalModels?.();
}

async function initialize() {
  try {
    const bootstrap = await api('/api/bootstrap');
    state.setup = bootstrap.setup_required;
    if (state.setup) {
      $('setupCodeLabel').hidden = false;
      $('authTitle').textContent = t('ساخت حساب مدیر اولیه');
      $('authEyebrow').textContent = t('اولین راه‌اندازی');
      $('authDescription').textContent = t('با کد محلی سرور، مالک این فضای دانش شوید.');
      $('authSubmit').textContent = t('ساخت حساب مدیر');
      $('setupCode').required = true;
      $('password').autocomplete = 'new-password';
      return;
    }
    try {
      state.account = await api('/api/me');
      state.csrf = state.account.csrf;
      await enterWorkspace();
    } catch { /* The sign-in screen is the normal state without a session. */ }
  } catch (error) {$('authError').textContent = error.message;}
}

$('authForm').onsubmit = async event => {
  event.preventDefault();
  $('authSubmit').disabled = true;
  $('authError').textContent = '';
  try {
    const credentials = {username: $('username').value, password: $('password').value};
    if (state.setup) {
      await api('/api/setup', {method: 'POST', data: {...credentials, code: $('setupCode').value.trim()}});
      state.setup = false;
      $('setupCode').value = '';
      $('setupCodeLabel').hidden = true;
      $('setupCode').required = false;
    }
    await api('/api/login', {method: 'POST', data: credentials});
    $('password').value = '';
    state.account = await api('/api/me');
    state.csrf = state.account.csrf;
    await enterWorkspace();
  } catch (error) {$('authError').textContent = error.message;}
  finally {$('authSubmit').disabled = false;}
};

async function enterWorkspace() {
  $('auth').hidden = true;
  $('shell').hidden = false;
  $('accountName').textContent = state.account.username + (state.account.role === 'admin' ? t(' · مدیر') : '');
  for (const node of document.querySelectorAll('[data-admin]')) node.hidden = state.account.role !== 'admin';
  await refreshStatus();
  await loadDocuments();
  const conversations = await loadConversations();
  if (conversations.length) await selectConversation(conversations[0].id);
  else renderMessages();
  if (state.account.role === 'admin') showView('dashboard');
}

async function refreshStatus() {
  if (!state.account) return;
  state.status = await api('/api/status');
  const domain = state.status.domain;
  $('workspaceName').textContent = domain.name;
  $('serverVersion').textContent = 'Soshyant Expert ' + state.status.version;
  if (!$('domainForm').contains(document.activeElement)) {
    $('domainName').value = domain.name;
    $('domainDescription').value = domain.description;
    $('domainScope').value = domain.scope;
    $('domainLanguage').value = domain.language || 'auto';
    $('domainStyle').value = domain.answer_style;
    $('domainGlossary').value = Object.entries(domain.glossary).map(([key, value]) => key + ' = ' + value).join('\n');
    $('domainFields').value = domain.clarification_fields.join('\n');
  }
  $('systemStatus').replaceChildren();
  for (const [label, value, detail] of [
    [t('مدل زبانی'), state.status.model.installed ? t(statusNames[state.status.model.state]) || state.status.model.state : t('فایل مدل موجود نیست'), state.status.model.kind==='cloud' ? t('API provider') : t('اجرا روی همین سرور')],
    [t('جست‌وجوی اسناد'), state.status.search.installed ? t('مدل جست‌وجو موجود است') : t('مدل جست‌وجو موجود نیست'), state.status.search.mode === 'hybrid' ? t('ترکیبی: واژگانی و معنایی') : t('واژگانی')],
    [t('نسخه دانش'), state.status.knowledge_version, state.status.secure ? t('اتصال رمزگذاری‌شده') : t('اتصال محلی روی خود سرور')]
  ]) {
    const card = element('div', 'stat');
    card.append(element('small', '', label), element('strong', '', value), element('small', '', detail));
    $('systemStatus').append(card);
  }
  renderOcr();
  window.expertSpeech?.refresh();
  const missing = !state.status.model.installed || (state.status.search.mode === 'hybrid' && !state.status.search.installed);
  const cloud=state.status.model.kind==='cloud';
  $('notice').hidden = !missing && !cloud;
  $('notice').textContent = cloud?t('API model active: questions, relevant document passages, domain settings, and recent conversation are sent to the selected provider.')+' '+state.status.model.name+' · '+state.status.model.base_url+(missing?' · '+t('The selected model or search assets are unavailable.'):''):
    t('بعضی فایل‌های اجرای محلی موجود نیستند. پیش از استفاده، ابزار بررسی نصب را روی سرور اجرا کنید.');
}

function ocrSummary() {
  const ocr = state.status?.ocr;
  if (!ocr) return '';
  if (!ocr.installed) return t('OCR model files are not installed on this server.');
  if (!ocr.enabled) return t('OCR is off. Scanned pages without text are not indexed.');
  return t(ocr.device === 'gpu' ? 'On · runs on this server’s GPU · English only' : 'On · runs on this server’s CPU · English only');
}
function renderOcr() {
  const ocr = state.status?.ocr;
  if (!ocr) return;
  $('ocrEnabled').checked = ocr.enabled && ocr.installed;
  $('ocrEnabled').disabled = !ocr.installed;
  $('ocrStatus').textContent = ocrSummary();
}
$('ocrEnabled').addEventListener('change', async event => {
  const enabled = event.target.checked;
  try {
    state.status.ocr = await api('/api/ocr', {method: 'POST', data: {enabled}});
    toast(t(enabled ? 'English OCR turned on.' : 'English OCR turned off.'));
  } catch (error) {toast(error.message);}
  renderOcr();
});
function translatePhase(phase) {
  const page = /^Reading scanned page (\d+) of (\d+) with OCR$/.exec(phase || '');
  if (page && currentLanguage() === 'fa') return `خواندن صفحه اسکن‌شده ${page[1]} از ${page[2]} با OCR`;
  return t(phase);
}

let chatRows = [];
function renderConversations() {
  const query = $('chatSearch').value.trim().toLocaleLowerCase();
  $('conversationList').replaceChildren();
  for (const conversation of chatRows.filter(row => row.title.toLocaleLowerCase().includes(query))) {
    const row = element('div', 'conversation-row');
    const node = button(conversation.title, () => selectConversation(conversation.id), 'conversation-open');
    node.title = conversation.title;
    node.classList.toggle('selected', conversation.id === state.conversation);
    row.append(node, button(t('Rename'), () => manageConversation('rename', conversation), 'conversation-option'), button(t('Delete'), () => manageConversation('delete', conversation), 'conversation-option destructive'));
    $('conversationList').append(row);
  }
  if (!$('conversationList').childElementCount) $('conversationList').append(element('small', '', t('No conversations found.')));
}
async function loadConversations() {
  chatRows = await api('/api/conversations');renderConversations();return chatRows;
}
$('chatSearch').oninput = renderConversations;
let managedChat = null;
function manageConversation(action, row) {
  if (state.job || $('question').disabled) {toast(t('Wait for the current answer to finish.'));return;}
  if (!row) return;
  managedChat = {action, row};
  $('chatManageTitle').textContent = t(action === 'delete' ? 'Delete this chat?' : 'Rename chat');
  $('chatManageDescription').textContent = action === 'delete' ? t('This permanently removes the chat, answers and feedback from your account. Existing backups and shared copies remain.') : row.title;
  $('chatRenameLabel').hidden = action === 'delete';$('chatRenameValue').required = action !== 'delete';$('chatRenameValue').value = row.title;
  $('chatManageSubmit').textContent = t(action === 'delete' ? 'Delete permanently' : 'Save');
  $('chatManageSubmit').className = action === 'delete' ? 'danger-button' : 'primary';
  $('chatManageError').textContent = '';$('chatManageDialog').showModal();
}
$('chatManageCancel').onclick = () => $('chatManageDialog').close();
$('renameChat').onclick = () => manageConversation('rename', chatRows.find(row => row.id === state.conversation));
$('deleteChat').onclick = () => manageConversation('delete', chatRows.find(row => row.id === state.conversation));
$('chatManageForm').onsubmit = async event => {
  event.preventDefault();if (!managedChat) return;
  const {action, row} = managedChat;
  const title = $('chatRenameValue').value.trim();if (action === 'rename' && !title) {$('chatRenameValue').setCustomValidity(t('Enter a title.'));$('chatRenameValue').reportValidity();return;}
  $('chatManageSubmit').disabled = true;$('chatManageCancel').disabled = true;
  try {
    await api('/api/conversations/' + row.id + '/' + action, {method:'POST',data:action === 'delete' ? {confirm:true} : {title}});
    if (action === 'delete' && state.conversation === row.id) {state.conversation=null;state.messages=[];renderMessages();}
    await loadConversations();$('chatManageDialog').close();toast(t(action === 'delete' ? 'Chat deleted.' : 'Chat renamed.'));
  } catch(error) {$('chatManageError').textContent=error.message;}
  finally {$('chatManageSubmit').disabled=false;$('chatManageCancel').disabled=false;}
};
$('chatRenameValue').oninput = () => $('chatRenameValue').setCustomValidity('');

async function selectConversation(identity) {
  window.expertSpeech?.cancel();
  if (state.job) {toast(t('ابتدا پاسخ فعلی را متوقف کنید یا منتظر پایان آن بمانید.')); return;}
  state.conversation = identity;
  state.messages = await api('/api/conversations/' + identity + '/messages');
  renderMessages();
  await loadConversations();
  showView('chat');
}

$('newConversation').onclick = async () => {
  window.expertSpeech?.cancel();
  if (state.job) return;
  try {
    const conversation = await api('/api/conversations', {method: 'POST', data: {}});
    $('chatSearch').value = '';
    await selectConversation(conversation.id);
    $('question').focus();
  } catch (error) {toast(error.message);}
};

function renderMessages() {
  const container = $('messages');
  container.replaceChildren();
  $('renameChat').disabled = $('deleteChat').disabled = !state.conversation || Boolean(state.job) || $('question').disabled;
  if (!state.messages.length) {
    const empty = element('div', 'empty-state');
    empty.append(element('div', 'empty-symbol', '✳'), element('div', 'eyebrow', t('پرسش شما، در میان منابع شما')),
      element('h2', '', t('A little curiosity.\nA lot of knowledge.')), element('p', '', t('Ask your documents a question. Follow the evidence to the answer.')));
    const suggestions = element('div', 'suggestions');
    for (const question of [t('موضوع اصلی اسناد چیست؟'), t('کدام نکات نیاز به توجه بیشتری دارند؟')]) {
      suggestions.append(button(question, () => {$('question').value = question; $('question').focus();}));
    }
    empty.append(suggestions);
    const steps = element('div', 'knowledge-steps');
    for (const [number, title, description] of [['01', 'Ask naturally', 'Type or speak your question.'], ['02', 'Find the evidence', 'Search the knowledge you can access.'], ['03', 'Check the source', 'Inspect the passage behind each citation.']]) {
      const step = element('div', 'knowledge-step');
      step.append(element('span', 'step-number', number), element('strong', '', t(title)), element('small', '', t(description)));
      steps.append(step);
    }
    empty.append(steps);
    container.append(empty);
    return;
  }
  for (const message of state.messages) {
    const card = element('article', 'message ' + message.role);
    card.dir = 'auto';
    if (message.role === 'user') {
      card.append(element('div', 'message-text', message.content));
    } else {
      const result = message.result || {};
      const label = element('div', 'message-label');
      label.append(element('span', '', 'Soshyant Expert'), element('span', 'status-label', result.status === 'answered' ? t('Sources attached') : t(statusNames[result.status]) || ''));
      card.append(label);
      const text = element('div', 'message-text');
      const sourceNodes = new Map();
      const citations = result.citations || [];
      for (const citation of citations) {
        const details = element('details', 'source');
        details.id = 'source-' + message.id + '-' + citation.n;
        details.dir = 'auto';
        details.append(element('summary', '', `[${citation.n}] ${citation.title} · ${citation.location}`),
          element('blockquote', '', citation.text), element('small', '', t('نسخه سند: ') + citation.document_version + ' · ' + citation.filename));
        const link = element('a', '', t('دریافت سند اصلی ↓'));
        link.href = '/api/documents/' + citation.document_id + '/download?version=' + citation.document_version;
        details.append(link);
        sourceNodes.set(citation.n, details);
      }
      let offset = 0;
      for (const match of message.content.matchAll(/\[(\d+)\]/g)) {
        text.append(document.createTextNode(message.content.slice(offset, match.index)));
        const target = sourceNodes.get(Number(match[1]));
        if (target) {
          const link = element('a', '', match[0]);
          link.href = '#' + target.id;
          link.onclick = event => {event.preventDefault(); target.open = true; target.scrollIntoView({behavior: 'smooth', block: 'nearest'});};
          text.append(link);
        } else text.append(document.createTextNode(match[0]));
        offset = match.index + match[0].length;
      }
      text.append(document.createTextNode(message.content.slice(offset)));
      card.append(text, ...sourceNodes.values());
      const actions = element('div', 'message-actions');
      actions.append(button(t('کپی پاسخ'), async node => {
        const references = citations.map(c => `[${c.n}] ${c.title} · ${c.location}\n${c.text}`).join('\n\n');
        await navigator.clipboard.writeText(message.content + (references ? '\n\n' + references : ''));
        node.textContent = t('کپی شد');
      }));
      for (const [title, rating] of [[t('مفید بود'), 'helpful'], [t('نیاز به اصلاح'), 'incorrect']]) {
        actions.append(button(title, async node => {
          await api('/api/feedback', {method: 'POST', data: {message_id: message.id, rating}});
          node.textContent = t('ثبت شد');
        }));
      }
      card.append(actions, element('small', '', t('نسخه دانش هنگام پاسخ: ') + (result.knowledge_version || '—')));
    }
    if (message.created) card.append(element('small','message-time',new Date(message.created*1000).toLocaleString(currentLanguage() === 'fa' ? 'fa-IR' : 'en-US')));
    container.append(card);
  }
  container.scrollTop = container.scrollHeight;
}

async function watchJob(identity, progress) {
  for (;;) {
    const job = await api('/api/jobs/' + identity);
    progress(translatePhase(job.phase || job.status));
    if (job.status === 'done') return job.result;
    if (job.status === 'failed') throw new Error(job.error || t('پردازش انجام نشد.'));
    if (job.status === 'canceled') throw new Error(t('درخواست متوقف شد.'));
    await new Promise(resolve => setTimeout(resolve, 900));
  }
}

$('askForm').onsubmit = async event => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (!question || state.job || window.expertSpeech?.busy()) return;
  $('askButton').disabled = true;
  $('newConversation').disabled = true;
  $('question').disabled = true;
  let completed = false;
  try {
    if (!state.conversation) {
      const conversation = await api('/api/conversations', {method: 'POST', data: {}});
      state.conversation = conversation.id;
    }
    state.messages.push({role: 'user', content: question});
    renderMessages();
    const job = await api('/api/ask', {method: 'POST', data: {conversation_id: state.conversation, question, response_language: currentLanguage(),model_selection:state.status?.model.selection_id}});
    state.job = job.job_id;
    $('cancelAnswer').hidden = false;
    $('question').value = '';
    await watchJob(state.job, phase => {$('answerPhase').textContent = phase;});
    completed = true;
    state.messages = await api('/api/conversations/' + state.conversation + '/messages');
    renderMessages();
    await loadConversations();
  } catch (error) {
    toast(error.message);
    $('question').value = question;
    if (state.conversation) {
      state.messages = await api('/api/conversations/' + state.conversation + '/messages').catch(() => state.messages);
      renderMessages();
    }
  } finally {
    state.job = null;
    $('cancelAnswer').hidden = true;
    $('askButton').disabled = false;
    $('newConversation').disabled = false;
    $('question').disabled = false;
    $('renameChat').disabled = $('deleteChat').disabled = !state.conversation;
    $('answerPhase').textContent = completed ? t('پاسخ آماده است؛ شواهد را بررسی کنید.') : t('می‌توانید پرسش را اصلاح و دوباره ارسال کنید.');
    $('question').focus();
    refreshStatus().catch(() => {});
  }
};
$('question').onkeydown = event => {if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault(); $('askForm').requestSubmit();}};
$('cancelAnswer').onclick = async () => {
  if (!state.job) return;
  try {await api('/api/jobs/' + state.job + '/cancel', {method: 'POST', data: {}}); $('answerPhase').textContent = t('در حال توقف درخواست…');}
  catch (error) {toast(error.message);}
};

$('exportChat').onclick = () => {
  const text = state.messages.map(message => {
    const sources = message.result?.citations || [];
    return (message.role === 'user' ? t('کاربر: ') : t('دستیار: ')) + message.content + '\n' + sources.map(c => `[${c.n}] ${c.title} · ${c.location}\n${c.text}`).join('\n\n');
  }).join('\n\n');
  const url = URL.createObjectURL(new Blob(['\ufeff' + text], {type: 'text/plain;charset=utf-8'}));
  const link = element('a'); link.href = url; link.download = 'soshyant-conversation.txt'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
};

async function loadDocuments() {
  const rows = await api('/api/documents' + ($('includeArchived').checked ? '?archived=1' : ''));
  $('docCount').textContent = rows.filter(row => row.active).length;
  const container = $('documentList');
  container.replaceChildren();
  if (!rows.length) container.append(element('p', '', t('هنوز سندی اضافه نشده است. مدیر می‌تواند اولین منبع را بارگذاری کند.')));
  for (const document of rows) {
    const card = element('div', 'document');
    card.dataset.search = (document.title + ' ' + document.filename).toLocaleLowerCase();
    const info = element('div', 'doc-info');
    info.append(element('h3', '', document.title), element('p', '', document.filename + t(' · نسخه ') + document.version + ' · ' + document.passages + t(' شاهد · ') + Math.ceil(document.bytes / 1024) + ' KB'));
    info.append(element('small','',t(document.restricted?'Restricted access':'All signed-in users')));
    if (document.error) info.append(element('p', 'doc-error', document.error));
    const actions = element('div', 'doc-actions');
    if (document.active) {
      const download = element('a', 'quiet', t('دریافت')); download.href = '/api/documents/' + document.id + '/download'; actions.append(download);
    }
    if (state.account.role === 'admin') {
      actions.append(button(t('Access'),()=>openDocumentAccess(document)));
      if (document.active) {
        actions.append(button(t('نمایه‌سازی مجدد'), async () => {
          const response = await api('/api/documents/' + document.id + '/index', {method: 'POST', data: {}});
          toast(t('نمایه‌سازی در صف قرار گرفت.'));
          await watchJob(response.job_id, phase => {$('uploadPhase').textContent = phase;});
          await loadDocuments();
        }));
        actions.append(button(t('نسخه جدید'), () => {
          const input = element('input'); input.type = 'file'; input.accept = '.pdf,.docx,.xlsx,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff';
          input.onchange = async () => {
            const file = input.files[0]; if (!file) return;
            try {
              const job = await api('/api/documents/' + document.id + '/replace?filename=' + encodeURIComponent(file.name), {method: 'POST', raw: file});
              await watchJob(job.job_id, phase => {$('uploadPhase').textContent = phase;});
              await loadDocuments(); toast(t('نسخه جدید آماده شد.'));
            } catch (error) {toast(error.message);}
          };
          input.click();
        }));
      }
      actions.append(button(document.active ? t('بایگانی') : t('بازگردانی'), async () => {
        await api('/api/documents/' + document.id + (document.active ? '/archive' : '/restore'), {method: 'POST', data: {}});
        await loadDocuments();
      }));
      if (!document.active) actions.append(button(t('Delete permanently'), () => {
        pendingDocumentDelete = document.id;
        $('deleteDocumentName').textContent = document.title;
        $('deleteDocumentError').textContent = '';
        $('deleteDocumentDialog').showModal();
      }, 'quiet destructive'));
    }
    card.append(element('div', 'doc-symbol', '▤'), info, element('span', 'doc-status ' + document.status, document.active ? t(statusNames[document.status]) || document.status : t('بایگانی')), actions);
    container.append(card);
  }
  filterDocuments();
}
$('includeArchived').onchange = () => loadDocuments().catch(error => toast(error.message));
function filterDocuments() {
  const query = $('documentSearch').value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const card of $('documentList').querySelectorAll('.document')) {
    card.hidden = !card.dataset.search.includes(query);
    if (!card.hidden) visible++;
  }
  $('documentSearchEmpty').hidden = !query || visible > 0;
}
$('documentSearch').oninput = filterDocuments;
$('menuToggle').onclick = () => {
  const opened = document.body.classList.toggle('navigation-open');
  $('menuToggle').setAttribute('aria-expanded', String(opened));
};
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.classList.contains('navigation-open')) {
    document.body.classList.remove('navigation-open');$('menuToggle').setAttribute('aria-expanded','false');$('menuToggle').focus();
  }
});
document.querySelector('main').addEventListener('click', event => {
  if (event.target.closest('#menuToggle')) return;
  document.body.classList.remove('navigation-open');$('menuToggle').setAttribute('aria-expanded','false');
});
$('cancelDeleteDocument').onclick = () => {pendingDocumentDelete=null;$('deleteDocumentDialog').close();};
$('deleteDocumentDialog').addEventListener('cancel', event => {
  if(documentDeleting)event.preventDefault();else pendingDocumentDelete=null;
});
$('confirmDeleteDocument').onclick = async () => {
  if(!pendingDocumentDelete || documentDeleting)return;
  documentDeleting=true;
  $('confirmDeleteDocument').disabled=true;$('cancelDeleteDocument').disabled=true;
  try {
    await api('/api/documents/'+pendingDocumentDelete+'/delete',{method:'POST',data:{confirm:true}});
    pendingDocumentDelete=null;$('deleteDocumentDialog').close();
    toast(t('Archived document deleted.'));
    await loadDocuments();await refreshStatus();
  } catch(error){$('deleteDocumentError').textContent=error.message;}
  finally{documentDeleting=false;$('confirmDeleteDocument').disabled=false;$('cancelDeleteDocument').disabled=false;}
};
$('refreshDocuments').onclick = () => loadDocuments().catch(error => toast(error.message));
$('uploadForm').onsubmit = async event => {
  event.preventDefault();
  const file = $('uploadFile').files[0]; if (!file) return;
  if (file.size > (state.status?.upload_limit_mb || 20) * 1024 * 1024) {toast(t('حجم سند از حد مجاز بیشتر است.')); return;}
  $('uploadButton').disabled = true;
  try {
    const query = new URLSearchParams({filename: file.name, title: $('uploadTitle').value, priority: $('uploadPriority').value, restricted: $('uploadAccess').value});
    const job = await api('/api/documents?' + query, {method: 'POST', raw: file});
    await loadDocuments();
    await watchJob(job.job_id, phase => {$('uploadPhase').textContent = phase;});
    $('uploadPhase').textContent = t('سند آماده استفاده در پاسخ‌هاست.');
    $('uploadForm').reset();
    await loadDocuments(); await refreshStatus();
  } catch (error) {$('uploadPhase').textContent = error.message; await loadDocuments().catch(() => {});}
  finally {$('uploadButton').disabled = false;}
};

$('domainForm').onsubmit = async event => {
  event.preventDefault();
  try {
    const glossary = {};
    for (const line of $('domainGlossary').value.split('\n').filter(line => line.trim())) {
      const separator = line.indexOf('=');
      if (separator < 1) throw new Error(t('هر خط واژه‌نامه باید به شکل اصطلاح = معنی باشد.'));
      glossary[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
    }
    await api('/api/domain', {method: 'POST', data: {
      name: $('domainName').value, description: $('domainDescription').value, scope: $('domainScope').value,
      language: $('domainLanguage').value, answer_style: $('domainStyle').value, glossary,
      clarification_fields: $('domainFields').value.split('\n').map(line => line.trim()).filter(Boolean)
    }});
    $('domainSaved').textContent = t(' ذخیره شد؛ از پرسش بعدی اعمال می‌شود.');
    await refreshStatus();
  } catch (error) {toast(error.message);}
};

async function loadUsers() {
  const users = await api('/api/users');
  $('userList').replaceChildren();
  for (const user of users) {
    const card = element('div', 'document');
    const info = element('div', 'doc-info'); info.append(element('h3', '', user.username), element('p', '', user.role === 'admin' ? t('مدیر') : t('کاربر')));
    card.append(element('div', 'doc-symbol', '♙'), info, element('span', 'doc-status', user.active ? t('فعال') : t('غیرفعال')));
    if (user.id !== state.account.id) card.append(button(user.active ? t('غیرفعال کردن') : t('فعال کردن'), async () => {
      await api('/api/users/' + user.id + '/active', {method: 'POST', data: {active: !user.active}}); await loadUsers();
    }));
    $('userList').append(card);
  }
}
$('userForm').onsubmit = async event => {
  event.preventDefault();
  try {await api('/api/users', {method: 'POST', data: {username: $('newUsername').value, password: $('newPassword').value, role: $('newRole').value}}); $('userForm').reset(); await loadUsers(); toast(t('حساب ساخته شد.'));}
  catch (error) {toast(error.message);}
};
$('createBackup').onclick = async () => {
  $('createBackup').disabled = true;
  try {
    const result = await api('/api/backups', {method: 'POST', data: {}});
    const link = element('a', '', t('دریافت نسخه پشتیبان ↓')); link.href = result.url;
    $('backupResult').replaceChildren(link);
    toast(t('نسخه پشتیبان ساخته شد.'));
  } catch (error) {toast(error.message);}
  finally {$('createBackup').disabled = false;}
};
$('passwordForm').onsubmit = async event => {
  event.preventDefault();
  try {await api('/api/password', {method: 'POST', data: {current: $('currentPassword').value, password: $('changedPassword').value}}); location.reload();}
  catch (error) {toast(error.message);}
};
$('logout').onclick = async () => {
  try {await api('/api/logout', {method: 'POST', data: {}}); location.reload();}
  catch (error) {toast(error.message);}
};
for (const tab of document.querySelectorAll('[data-view]')) tab.onclick = () => showView(tab.dataset.view);
window.addEventListener('expert-language-change', () => {
  $('viewTitle').textContent = t(titles[state.view]);
  if (state.setup) {
    $('authTitle').textContent = t('ساخت حساب مدیر اولیه');
    $('authEyebrow').textContent = t('اولین راه‌اندازی');
    $('authDescription').textContent = t('با کد محلی سرور، مالک این فضای دانش شوید.');
    $('authSubmit').textContent = t('ساخت حساب مدیر');
  }
  if (state.account) {
    $('accountName').textContent = state.account.username + (state.account.role === 'admin' ? t(' · مدیر') : '');
    renderMessages();renderConversations();renderOcr();
    $('watchPhase').textContent=t($('watchPhase').textContent);
    if (state.view === 'watched') loadWatched().catch(error => toast(error.message));
    if (state.view === 'reviews') loadReviews().catch(error => toast(error.message));
    if (state.view === 'dashboard') loadDashboard().catch(error => toast(error.message));
    if (state.view === 'documents') loadDocuments().catch(error => toast(error.message));
    if (state.view === 'groups') loadAccessGroups().catch(error => toast(error.message));
    if (state.view === 'users') loadUsers().catch(error => toast(error.message));
    if (state.view === 'maintenance') refreshStatus().catch(error => toast(error.message));
  }
  if (!state.job) $('answerPhase').textContent = t('پاسخ‌ها را با منابع همراه آن‌ها بررسی کنید.');
});
async function loadDashboard() {
  if (state.account?.role !== 'admin') return;
  const [overview] = await Promise.all([api('/api/dashboard'), refreshStatus()]);
  $('dashboardStats').replaceChildren();
  const pending = overview.jobs.filter(row=>row.status==='queued').reduce((n,row)=>n+row.count,0);
  const running = overview.jobs.filter(row=>row.status==='running').reduce((n,row)=>n+row.count,0);
  const date = overview.backup.latest ? new Date(overview.backup.latest*1000).toLocaleString(currentLanguage()==='fa'?'fa-IR':'en-US') : t('No backup yet');
  for (const [label,value,detail] of [
    ['Active documents',overview.documents.active,t('Indexed')+': '+(overview.documents.by_status.indexed||0)],
    ['Searchable passages',overview.documents.passages,t('Archived')+': '+overview.documents.archived],
    ['Work in progress',running,t('Queued')+': '+pending],
    ['Active users',overview.users.active,t('Total accounts')+': '+overview.users.total],
    ['Local backups',overview.backup.count,date],
    ['Knowledge version',state.status.knowledge_version,state.status.model.name]
  ]) {const card=element('div','stat');card.append(element('small','',t(label)),element('strong','',String(value)),element('small','',detail));$('dashboardStats').append(card);}
  const ready=$('dashboardReadiness');ready.replaceChildren();
  const checks=[
    [state.status.model.installed,'Selected model available',state.status.model.name+' · '+(t(statusNames[state.status.model.state])||state.status.model.state)],
    [state.status.search.mode!=='hybrid'||state.status.search.installed,'Document search available',state.status.search.mode],
    [(overview.documents.by_status.indexed||0)>0,'Indexed knowledge available',t('Upload and index documents to support answers.')],
    [state.status.ocr.installed||!state.status.ocr.enabled,'English OCR for scans',ocrSummary()],
    [Boolean(overview.backup.latest),'Backup available',date]
  ];
  for(const [ok,label,detail] of checks){const row=element('div','readiness-row');row.append(element('span',ok?'health-good':'health-warn',t(ok?'Available':'Needs attention')),element('div','',t(label)),element('small','',detail));ready.append(row);}
  const attention=$('dashboardAttention');attention.replaceChildren();
  for(const doc of overview.attention){const row=element('div','document');const info=element('div','doc-info');info.append(element('h3','',doc.title||doc.filename),element('p',doc.error?'doc-error':'',doc.error||t(statusNames[doc.status])||doc.status));row.append(info,button(t('Open documents'),()=>showView('documents')));attention.append(row);}
  if(!overview.attention.length)attention.append(element('p','',t('No failed or pending documents.')));
  $('dashboardTime').textContent=t('Updated')+' '+new Date(overview.checked_at*1000).toLocaleTimeString(currentLanguage()==='fa'?'fa-IR':'en-US');
}
$('refreshDashboard').onclick=async()=>{try{await loadDashboard();}catch(error){toast(error.message);}};
$('dashboardDocuments').onclick=()=>showView('documents');$('dashboardModels').onclick=()=>showView('models');$('dashboardBackup').onclick=()=>showView('maintenance');$('dashboardChat').onclick=()=>showView('chat');
setInterval(()=>{if(state.account?.role==='admin'&&state.view==='dashboard'&&!document.hidden)loadDashboard().catch(error=>{$('dashboardTime').textContent=error.message;});},20000);
// Administrator document discovery and answer triage. No provider calls are made here.
let watchBusy=false, watchBrowser=null, watchApproval=null;
function watchControls() {for(const id of ['watchAdd','watchBrowse','watchPath','watchRecursive','watchAccess','watchRefresh'])$(id).disabled=watchBusy;}
async function loadWatched() {
  if(state.account?.role!=='admin')return;
  const data=await api('/api/watched-folders');
  $('watchFolders').replaceChildren();$('watchChanges').replaceChildren();
  for(const folder of data.folders){
    const card=element('div','document');const info=element('div','doc-info');
    info.append(element('h3','model-path',folder.path),element('p','',t(folder.enabled?'Monitoring enabled':'Monitoring paused')+' · '+t(folder.recursive?'Includes subfolders':'This folder only')));
    info.append(element('small','',t(folder.restricted?'New files: administrators only':'New files: all signed-in users')));
    const visibility=element('select');visibility.setAttribute('aria-label',t('New file access'));for(const [value,label] of [['0','All signed-in users'],['1','Administrators only']]){const option=element('option','',t(label));option.value=value;visibility.append(option);}visibility.value=folder.restricted?'1':'0';info.append(visibility,button(t('Save new file access'),async()=>{await api('/api/watched-folders/'+folder.id+'/access',{method:'POST',data:{restricted:visibility.value==='1'}});await loadWatched();toast(t('Document access saved.'));}));
    if(folder.scanned)info.append(element('small','',t('Last scan')+': '+new Date(folder.scanned*1000).toLocaleString(currentLanguage()==='fa'?'fa-IR':'en-US')));
    if(folder.error)info.append(element('p','doc-error',folder.error));card.append(info);
    const actions=element('div','doc-actions');
    actions.append(button(t('Scan now'),async()=>{if(watchBusy)return;watchBusy=true;watchControls();try{$('watchPhase').textContent=t('Checking for document changes…');await api('/api/watched-folders/'+folder.id+'/scan',{method:'POST',data:{}});await loadWatched();$('watchPhase').textContent=t('Scan complete. Review the changes below.');}finally{watchBusy=false;watchControls();}}));
    actions.append(button(t(folder.enabled?'Pause':'Resume monitoring'),async()=>{await api('/api/watched-folders/'+folder.id+'/enabled',{method:'POST',data:{enabled:!folder.enabled}});await loadWatched();}));
    card.append(actions);$('watchFolders').append(card);
  }
  if(!data.folders.length)$('watchFolders').append(element('p','',t('No watched folders yet.')));
  const labels={new:'New file',changed:'Changed file',missing:'Source file missing',indexing:'Indexing approved update',unreadable:'Needs attention',archived:'Archived in library',deleted:'Removed from library',conflict:'Library changed separately'};
  for(const change of data.changes){
    const card=element('div','document');const info=element('div','doc-info');
    info.append(element('h3','',change.relative),element('p','model-path',change.path),element('span','doc-status',t(labels[change.kind])));
    if(change.error)info.append(element('p','doc-error',change.error));
    if(['archived','deleted','conflict'].includes(change.kind))info.append(element('p','',t('Review this document in Documents before importing another version.')));
    card.append(info);const actions=element('div','doc-actions');
    if(['new','changed','missing'].includes(change.kind))actions.append(button(t(change.kind==='missing'?'Review archive':'Review & approve'),()=>openWatchApproval(change)));
    if(!['indexing','unreadable'].includes(change.kind))actions.append(button(t('Ignore this version'),async()=>{if(watchBusy)return;await api('/api/watched-changes/'+change.id+'/ignore',{method:'POST',data:{sha:change.present?change.sha:'missing'}});await loadWatched();}));
    card.append(actions);$('watchChanges').append(card);
  }
  if(!data.changes.length)$('watchChanges').append(element('p','',t('No changes awaiting review.')));
}
$('watchForm').onsubmit=async event=>{
  event.preventDefault();if(watchBusy)return;watchBusy=true;watchControls();
  try {const result=await api('/api/watched-folders',{method:'POST',data:{path:$('watchPath').value,recursive:$('watchRecursive').checked,restricted:$('watchAccess').value==='1'}});$('watchPhase').textContent=t('Checking for document changes…');await api('/api/watched-folders/'+result.id+'/scan',{method:'POST',data:{}});$('watchPhase').textContent=t('Scan complete. Review the changes below.');}
  catch(error){$('watchPhase').textContent=error.message;}
  finally {await loadWatched().catch(error=>toast(error.message));watchBusy=false;watchControls();}
};
$('watchRefresh').onclick=()=>loadWatched().catch(error=>toast(error.message));
function openWatchApproval(change){
  if(watchBusy)return;watchApproval=change;
  $('watchApprovalTitle').textContent=t(change.kind==='missing'?'Archive missing document?':'Approve document update?');
  $('watchApprovalFile').textContent=change.relative;
  $('watchApprovalText').textContent=t(change.kind==='missing'?'The source file is missing. Archiving removes this document from new answers. Its saved versions and existing citations remain.':'This exact file version will be indexed locally. The current published document remains available if indexing fails.');
  $('watchApprovalConfirm').textContent=t(change.kind==='missing'?'Archive document':'Approve & index');$('watchApprovalError').textContent='';$('watchApprovalDialog').showModal();
}
$('watchApprovalCancel').onclick=()=>$('watchApprovalDialog').close();
$('watchApprovalConfirm').onclick=async()=>{
  if(watchBusy||!watchApproval)return;watchBusy=true;watchControls();$('watchApprovalConfirm').disabled=true;$('watchApprovalCancel').disabled=true;
  try{const change=watchApproval;const result=await api('/api/watched-changes/'+change.id+'/approve',{method:'POST',data:{sha:change.present?change.sha:'missing',confirm_archive:change.kind==='missing'}});$('watchApprovalDialog').close();
    if(result.job_id){$('watchPhase').textContent=t('Indexing approved update');await loadWatched();await watchJob(result.job_id,phase=>{$('watchPhase').textContent=phase;});}
    $('watchPhase').textContent=t(result.archived?'Document archived.':'Approved document published.');await refreshStatus();await loadDocuments();await loadWatched();
  }catch(error){$('watchApprovalError').textContent=error.message;$('watchPhase').textContent=error.message;await loadWatched().catch(()=>{});}
  finally{watchBusy=false;watchControls();$('watchApprovalConfirm').disabled=false;$('watchApprovalCancel').disabled=false;}
};
async function browseWatchFolder(path){
  $('watchBrowserError').textContent='';$('watchBrowserChoose').disabled=true;
  try{watchBrowser=await api('/api/models/folders'+(path?'?path='+encodeURIComponent(path):''));$('watchBrowserPath').textContent=watchBrowser.path;
    $('watchDrive').replaceChildren(...watchBrowser.roots.map(root=>{const option=element('option','',root);option.value=root;return option;}));
    const drive=watchBrowser.roots.find(root=>watchBrowser.path.toLowerCase().startsWith(root.toLowerCase()));if(drive)$('watchDrive').value=drive;
    $('watchDirectoryList').replaceChildren(...watchBrowser.directories.map(row=>button('▸ '+row.name,()=>browseWatchFolder(row.path),'folder-browser-item')));
    if(!watchBrowser.directories.length)$('watchDirectoryList').append(element('p','',t('No subfolders. You can select this folder.')));
    $('watchUp').disabled=watchBrowser.parent===watchBrowser.path;$('watchBrowserChoose').disabled=false;
  }catch(error){$('watchBrowserError').textContent=error.message;}
}
$('watchBrowse').onclick=()=>{$('watchFolderDialog').showModal();browseWatchFolder($('watchPath').value);};
$('watchDrive').onchange=()=>browseWatchFolder($('watchDrive').value);$('watchUp').onclick=()=>{if(watchBrowser)browseWatchFolder(watchBrowser.parent);};
$('watchBrowserCancel').onclick=()=>$('watchFolderDialog').close();$('watchBrowserChoose').onclick=()=>{if(watchBrowser){$('watchPath').value=watchBrowser.path;$('watchFolderDialog').close();}};
setInterval(()=>{if(state.account?.role==='admin'&&state.view==='watched'&&!document.hidden&&!watchBusy)loadWatched().catch(error=>{$('watchPhase').textContent=error.message;});},15000);
const reviewDrafts=new Map();
let reviewNext=null, reviewGeneration=0;
async function loadReviews(more=false){
  if(state.account?.role!=='admin')return;const generation=++reviewGeneration;
  const params=new URLSearchParams({kind:$('reviewKind').value,state:$('reviewState').value});if(more&&reviewNext)params.set('before',reviewNext);
  const result=await api('/api/reviews?'+params);if(generation!==reviewGeneration)return;
  if(!more)$('reviewItems').replaceChildren();reviewNext=result.next;$('reviewMore').hidden=!reviewNext;
  for(const row of result.items){
    const card=element('article','card review-card');card.dir='auto';
    card.append(element('div','eyebrow',row.username+' · '+new Date(row.created*1000).toLocaleString(currentLanguage()==='fa'?'fa-IR':'en-US')),element('h3','',row.question||t('Question unavailable')));
    card.append(element('span','doc-status',t(statusNames[row.result.status])||row.result.status||''),element('p','review-answer',row.content));
    for(const feedback of row.feedback){const box=element('div','review-feedback');box.append(element('strong','',t(feedback.rating==='helpful'?'Helpful feedback':'Reported incorrect')));if(feedback.note)box.append(element('p','review-answer',feedback.note));card.append(box);}
    if(row.result.citations?.length){const details=element('details','source');details.append(element('summary','',t('Supporting sources')));for(const source of row.result.citations)details.append(element('strong','',`[${source.n}] ${source.title} · ${source.location}`),element('blockquote','',source.text));card.append(details);}
    const note=element('textarea');note.rows=2;note.maxLength=2000;note.value=reviewDrafts.get(row.id)?.note ?? row.review_note ?? '';const noteLabel=element('label','',t('Resolution note'));noteLabel.append(note);
    const select=element('select');select.setAttribute('aria-label',t('Review decision'));for(const [value,label] of [['open','Open'],['resolved','Resolved']]){const option=element('option','',t(label));option.value=value;select.append(option);}select.value=reviewDrafts.get(row.id)?.status ?? (row.resolved?'resolved':'open');
    note.oninput=select.onchange=()=>reviewDrafts.set(row.id,{note:note.value,status:select.value});const label=element('label','',t('Review status'));label.append(select);
    card.append(noteLabel,label,button(t('Save review'),async()=>{await api('/api/reviews/'+row.id,{method:'POST',data:{status:select.value,note:note.value}});reviewDrafts.delete(row.id);await loadReviews();toast(t('Review saved.'));}));$('reviewItems').append(card);
  }
  if(!$('reviewItems').childElementCount)$('reviewItems').append(element('p','',t('No answers match these filters.')));
  $('reviewPhase').textContent=t('New feedback reopens a resolved review.');
}
for(const id of ['reviewKind','reviewState'])$(id).onchange=()=>loadReviews().catch(error=>toast(error.message));
$('reviewRefresh').onclick=()=>loadReviews().catch(error=>toast(error.message));$('reviewMore').onclick=()=>loadReviews(true).catch(error=>toast(error.message));
let groupEditing=null, accessDocument=null, deleteAccessGroup=null;
async function loadAccessGroups(){
  const [groups,users]=await Promise.all([api('/api/groups'),api('/api/users')]);$('accessGroupList').replaceChildren();
  for(const group of groups){const card=element('div','document');const info=element('div','doc-info');info.append(element('h3','',group.name),element('p','',group.members.map(id=>users.find(user=>user.id===id)?.username||id).join(', ')||t('No members')));card.append(info,button(t('Edit group'),()=>openAccessGroup(group)),button(t('Remove group'),()=>{deleteAccessGroup=group.id;$('deleteAccessGroupName').textContent=group.name;$('deleteAccessGroupError').textContent='';$('deleteAccessGroupDialog').showModal();},'quiet destructive'));$('accessGroupList').append(card);}
  if(!groups.length)$('accessGroupList').append(element('p','',t('No access groups yet.')));
}
async function openAccessGroup(group=null){
  const users=await api('/api/users');groupEditing=group?.id||null;$('accessGroupName').value=group?.name||'';$('accessGroupMembers').replaceChildren();$('accessGroupError').textContent='';
  for(const user of users){const label=element('label','checkbox');const input=element('input');input.type='checkbox';input.value=user.id;input.checked=Boolean(group?.members.includes(user.id));label.append(input,document.createTextNode(user.username+' · '+t(user.role==='admin'?'Admin':'User')+(user.active?'':' · '+t('Inactive'))));$('accessGroupMembers').append(label);}
  $('accessGroupDialog').showModal();
}
$('newAccessGroup').onclick=()=>openAccessGroup().catch(error=>toast(error.message));$('accessGroupCancel').onclick=()=>$('accessGroupDialog').close();
$('accessGroupForm').onsubmit=async event=>{
  event.preventDefault();$('accessGroupSave').disabled=true;$('accessGroupCancel').disabled=true;
  try{await api('/api/groups'+(groupEditing?'/'+groupEditing:''),{method:'POST',data:{name:$('accessGroupName').value,members:[...$('accessGroupMembers').querySelectorAll('input:checked')].map(input=>input.value)}});$('accessGroupDialog').close();await loadAccessGroups();toast(t('Group saved.'));}
  catch(error){$('accessGroupError').textContent=error.message;}finally{$('accessGroupSave').disabled=false;$('accessGroupCancel').disabled=false;}
};
async function openDocumentAccess(doc){
  const [access,groups]=await Promise.all([api('/api/documents/'+doc.id+'/access'),api('/api/groups')]);accessDocument=doc.id;$('documentAccessName').textContent=doc.title;$('documentAccessScope').value=access.restricted?'restricted':'shared';$('documentAccessError').textContent='';$('documentAccessGroups').replaceChildren();
  for(const group of groups){const label=element('label','checkbox');const input=element('input');input.type='checkbox';input.value=group.id;input.checked=access.groups.includes(group.id);label.append(input,document.createTextNode(group.name));$('documentAccessGroups').append(label);}
  if(!groups.length)$('documentAccessGroups').append(element('p','',t('Create groups in Access groups to grant team access.')));
  $('documentAccessGroups').hidden=!access.restricted;$('documentAccessDialog').showModal();
}
$('documentAccessScope').onchange=()=>{$('documentAccessGroups').hidden=$('documentAccessScope').value!=='restricted';};$('documentAccessCancel').onclick=()=>$('documentAccessDialog').close();
$('documentAccessForm').onsubmit=async event=>{
  event.preventDefault();if(!accessDocument)return;$('documentAccessSave').disabled=true;$('documentAccessCancel').disabled=true;
  try{await api('/api/documents/'+accessDocument+'/access',{method:'POST',data:{restricted:$('documentAccessScope').value==='restricted',groups:[...$('documentAccessGroups').querySelectorAll('input:checked')].map(input=>input.value)}});$('documentAccessDialog').close();await loadDocuments();await refreshStatus();toast(t('Document access saved.'));}
  catch(error){$('documentAccessError').textContent=error.message;}finally{$('documentAccessSave').disabled=false;$('documentAccessCancel').disabled=false;}
};
$('deleteAccessGroupCancel').onclick=()=>$('deleteAccessGroupDialog').close();
$('deleteAccessGroupConfirm').onclick=async()=>{if(!deleteAccessGroup)return;$('deleteAccessGroupConfirm').disabled=true;try{await api('/api/groups/'+deleteAccessGroup+'/delete',{method:'POST',data:{confirm:true}});$('deleteAccessGroupDialog').close();await loadAccessGroups();toast(t('Group removed.'));}catch(error){$('deleteAccessGroupError').textContent=error.message;}finally{$('deleteAccessGroupConfirm').disabled=false;}};
initialize();
