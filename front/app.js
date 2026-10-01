const yen = (value) => `¥${Math.abs(value).toLocaleString('ja-JP')}`;
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const categories = [
  { name: '食費', color: '#415eee', budget: 60000 },
  { name: '住まい', color: '#92addf', budget: 90000 },
  { name: '日用品', color: '#b9a6ff', budget: 25000 },
  { name: '交通', color: '#ffab94', budget: 25000 },
  { name: '娯楽', color: '#e8b76b', budget: 30000 },
  { name: 'その他', color: '#86b6a9', budget: 20000 },
];
const totalBudget = categories.reduce((total, category) => total + category.budget, 0);
const storageKey = 'kakei-transactions-v1';
const now = new Date();
const sampleMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
let visibleMonth = new Date(sampleMonth);
let toastTimeout;
let listReturnState = null;
let showingDetail = false;
let currentDetailId = null;
let dataReady = false;
let loadingData = false;

function sampleTransactions() {
  return KakeiSampleData.createSampleTransactions(sampleMonth);
}

function isValidTransaction(item) {
  return item && typeof item.id === 'string' && typeof item.title === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.date) && Number.isFinite(item.amount) && item.amount > 0 && ['income', 'expense'].includes(item.type) && typeof item.category === 'string';
}

let transactions = [];
function monthKey(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`; }
function monthTransactions() { return transactions.filter((item) => item.date.startsWith(monthKey(visibleMonth))).sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id)); }
function sums(items) { return items.reduce((result, item) => { result[item.type] += item.amount; return result; }, { income: 0, expense: 0 }); }
function showToast(message) { const toast = document.getElementById('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(toastTimeout); toastTimeout = setTimeout(() => toast.classList.remove('show'), 3500); }

function renderSummary(items) {
  const { income, expense } = sums(items);
  const balance = income - expense;
  document.getElementById('balance-amount').textContent = `${balance < 0 ? '−' : ''}${yen(balance)}`;
  document.getElementById('balance-message').textContent = items.length ? (balance >= 0 ? '収入が支出を上回っています' : '支出が収入を上回っています') : '取引を追加して収支を確認しましょう';
  document.getElementById('income-total').textContent = yen(income);
  document.getElementById('expense-total').textContent = yen(expense);
  const remaining = totalBudget - expense;
  document.getElementById('remaining-budget').textContent = `${remaining < 0 ? '−' : ''}${yen(remaining)}`;
  document.getElementById('budget-used').textContent = `${yen(expense)} 使用済み`;
  document.getElementById('budget-limit').textContent = `予算 ${yen(totalBudget)}`;
  const progress = document.getElementById('budget-progress');
  progress.style.width = `${Math.min(100, expense / totalBudget * 100)}%`;
  progress.classList.toggle('over', expense > totalBudget);
}

function renderInsights(items) {
  const expenses = items.filter((item) => item.type === 'expense');
  const total = expenses.reduce((sum, item) => sum + item.amount, 0);
  const values = categories.map((category) => ({ ...category, amount: expenses.filter((item) => item.category === category.name).reduce((sum, item) => sum + item.amount, 0) }));
  const visible = values.filter((item) => item.amount > 0).sort((a, b) => b.amount - a.amount);
  document.getElementById('donut-total').textContent = yen(total);
  const donut = document.getElementById('donut');
  if (total) {
    let point = 0;
    const stops = visible.map((item) => { const start = point; point += item.amount / total * 100; return `${item.color} ${start}% ${point}%`; });
    donut.style.background = `conic-gradient(${stops.join(',')})`;
    donut.setAttribute('aria-label', `支出合計 ${yen(total)}。${visible.map((item) => `${item.name} ${yen(item.amount)}`).join('、')}`);
  } else {
    donut.style.background = '#dce2eb';
    donut.setAttribute('aria-label', 'この月の支出はまだありません');
  }
  document.getElementById('category-list').innerHTML = visible.length ? visible.map((item) => `<div class="category-row"><span class="category-name"><span class="category-dot" style="background:${item.color}"></span>${item.name}</span><span class="category-value">${yen(item.amount)} <span class="category-percent">${Math.round(item.amount / total * 100)}%</span></span></div>`).join('') : '<p class="category-empty">支出を記録すると、ここに内訳が表示されます。</p>';
  document.getElementById('budget-list').innerHTML = values.map((item) => { const ratio = item.amount / item.budget; const tone = ratio > 1 ? 'over' : ratio >= .8 ? 'warning' : 'safe'; return `<div class="budget-line"><div class="budget-line-top"><strong>${item.name}</strong><span>${yen(item.amount)} / ${yen(item.budget)}</span></div><div class="progress-track" role="meter" aria-label="${item.name}の予算使用率" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.min(100, Math.round(ratio * 100))}" aria-valuetext="${Math.round(ratio * 100)}パーセント"><span class="${tone}" style="width:${Math.min(100, ratio * 100)}%"></span></div></div>`; }).join('');
}

function renderWeekly(items) {
  const amounts = [0, 0, 0, 0, 0];
  items.filter((item) => item.type === 'expense').forEach((item) => { const week = Math.min(4, Math.floor((Number(item.date.slice(-2)) - 1) / 7)); amounts[week] += item.amount; });
  const max = Math.max(...amounts, 1);
  const weeks = ['1–7日', '8–14日', '15–21日', '22–28日', '29日–'];
  const chart = document.getElementById('weekly-chart');
  chart.innerHTML = amounts.map((amount, index) => `<div class="week-column"><span class="week-value">${yen(amount)}</span><span class="week-bar" style="height:${Math.max(3, amount / max * 102)}px"></span><span class="week-label">${weeks[index]}</span></div>`).join('');
  chart.setAttribute('aria-label', `週ごとの支出。${amounts.map((amount, index) => `${weeks[index]} ${yen(amount)}`).join('、')}`);
}

function renderTransactions(items) {
  const query = document.getElementById('transaction-search').value.trim().toLocaleLowerCase('ja-JP');
  const type = document.getElementById('type-filter').value;
  const filtered = items.filter((item) => (type === 'all' || item.type === type) && (!query || `${item.title} ${item.category}`.toLocaleLowerCase('ja-JP').includes(query)));
  document.getElementById('transaction-count').textContent = String(items.length);
  document.getElementById('transaction-rows').innerHTML = filtered.map((item) => `
    <tr>
      <td><div class="transaction-name"><span class="transaction-icon ${item.type === 'income' ? 'income' : ''}"><svg aria-hidden="true"><use href="#i-${item.type === 'income' ? 'arrow-down' : 'arrow-up'}"/></svg></span><a class="transaction-link" href="${KakeiDetail.detailHref(item.id)}" data-id="${escapeHtml(item.id)}">${escapeHtml(item.title)}</a></div></td>
      <td><span class="category-pill">${escapeHtml(item.category)}</span></td>
      <td>${Number(item.date.slice(5, 7))}月${Number(item.date.slice(8, 10))}日</td>
      <td class="amount-col"><span class="amount ${item.type === 'income' ? 'income' : ''}">${item.type === 'income' ? '+' : '−'}${yen(item.amount)}</span></td>
    </tr>`).join('');
  document.getElementById('transaction-empty').hidden = filtered.length > 0;
  document.querySelector('.table-scroll').hidden = filtered.length === 0;
}

function render() {
  if (!dataReady) return;
  const items = monthTransactions();
  document.getElementById('demo-note').hidden = !transactions.some((item) => item.id.startsWith('sample-'));
  document.getElementById('month-label').textContent = `${visibleMonth.getFullYear()}年${visibleMonth.getMonth() + 1}月`;
  document.getElementById('budget-period').textContent = `${visibleMonth.getMonth() + 1}月の利用状況`;
  renderSummary(items); renderInsights(items); renderWeekly(items); renderTransactions(items);
}

function setActiveNavigation(hash, isDetail) {
  const current = isDetail || hash === '#transactions' ? '#transactions' : hash === '#budget' ? '#budget' : hash === '#insights' ? '#insights' : '#overview';
  document.querySelectorAll('.side-nav .nav-link').forEach((link) => {
    const active = link.getAttribute('href') === current;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function renderRoute() {
  if (!dataReady) return;
  const hash = window.location.hash;
  const isDetail = hash === '#transaction' || hash.startsWith('#transaction/');
  const dashboard = document.getElementById('dashboard-view');
  const detail = document.getElementById('detail-view');
  setActiveNavigation(hash, isDetail);

  if (!isDetail) {
    dashboard.hidden = false;
    detail.hidden = true;
    document.body.classList.remove('detail-route');
    document.getElementById('current-page-label').textContent = '家計の概要';
    document.title = '家計の概要 | Kakei';
    if (showingDetail) {
      const saved = listReturnState && listReturnState.id === currentDetailId ? listReturnState : null;
      requestAnimationFrame(() => {
        if (saved) {
          window.scrollTo(0, saved.scrollY);
          const link = [...document.querySelectorAll('.transaction-link')].find((entry) => entry.dataset.id === saved.id);
          link?.focus({ preventScroll: true });
        } else if (hash === '#transactions') {
          document.getElementById('transactions').scrollIntoView();
          document.getElementById('transactions-title').focus({ preventScroll: true });
        } else if (hash === '#overview') {
          window.scrollTo(0, 0);
        } else if (hash === '#budget' || hash === '#insights') {
          document.querySelector(hash).scrollIntoView();
        }
      });
    }
    showingDetail = false;
    currentDetailId = null;
    return;
  }

  const id = KakeiDetail.detailIdFromHash(hash);
  const item = transactions.find((entry) => entry.id === id);
  currentDetailId = id;
  showingDetail = true;
  dashboard.hidden = true;
  detail.hidden = false;
  document.body.classList.add('detail-route');
  document.getElementById('current-page-label').textContent = '取引詳細';
  document.getElementById('detail-present').hidden = !item;
  document.getElementById('detail-missing').hidden = !!item;

  if (item) {
    document.getElementById('detail-type').textContent = item.type === 'income' ? '収入' : '支出';
    document.getElementById('detail-type').classList.toggle('income', item.type === 'income');
    document.getElementById('detail-amount').textContent = `${item.type === 'income' ? '+' : '−'}${yen(item.amount)}`;
    document.getElementById('detail-title').textContent = item.title;
    document.getElementById('detail-date').textContent = `${item.date.slice(0, 4)}年${Number(item.date.slice(5, 7))}月${Number(item.date.slice(8, 10))}日`;
    document.getElementById('detail-category').textContent = item.category;
    document.getElementById('detail-sample').hidden = !item.id.startsWith('sample-');
    const expenseFields = document.getElementById('detail-expense-fields');
    expenseFields.hidden = item.type !== 'expense';
    if (item.type === 'expense') {
      const details = KakeiTransactionData.readExpenseDetails(item);
      document.getElementById('detail-merchant').textContent = details.merchant || '未登録';
      document.getElementById('detail-payment-method').textContent = KakeiTransactionData.PAYMENT_METHOD_LABELS[details.paymentMethod] || '未登録';
      const itemList = document.getElementById('detail-items');
      itemList.replaceChildren();
      if (details.items.length) {
        const list = document.createElement('ul');
        list.className = 'detail-item-list';
        details.items.forEach((entry) => {
          const row = document.createElement('li');
          const name = document.createElement('span');
          const amount = document.createElement('strong');
          name.textContent = entry.name;
          amount.textContent = yen(entry.amount);
          row.append(name, amount);
          list.append(row);
        });
        itemList.append(list);
      } else {
        const empty = document.createElement('p');
        empty.className = 'detail-item-empty';
        empty.textContent = '品目は登録されていません';
        itemList.append(empty);
      }
    }
    document.title = `${item.title} | Kakei`;
  } else {
    document.title = '取引が見つかりません | Kakei';
  }
  requestAnimationFrame(() => {
    window.scrollTo(0, 0);
    document.getElementById('detail-heading').focus({ preventScroll: true });
  });
}

let manualAmountBeforeItems = '';
let itemRowSequence = 0;

function clearFormErrors() {
  document.querySelectorAll('#transaction-form .field-error').forEach((element) => { element.hidden = true; element.textContent = ''; });
  document.querySelectorAll('#transaction-form [aria-invalid]').forEach((element) => element.removeAttribute('aria-invalid'));
}

function showFieldError(field, message) {
  const errorIds = { title: 'title-error', date: 'date-error', amount: 'amount-error', merchant: 'merchant-error', paymentMethod: 'payment-method-error', itemRows: 'items-error' };
  const inputIds = { title: '[name="title"]', date: '#date-input', amount: '#amount-input', merchant: '#merchant-input', paymentMethod: '#payment-method-input', itemRows: '[data-item-name]' };
  const error = document.getElementById(errorIds[field]);
  let input = document.querySelector(`#transaction-form ${inputIds[field]}`);
  if (field === 'itemRows') {
    const rows = [...document.querySelectorAll('#item-rows .item-row')];
    const row = rows.find((entry) => {
      const name = entry.querySelector('[data-item-name]').value.trim();
      const amount = entry.querySelector('[data-item-amount]').value.trim();
      return !name || !/^\d+$/.test(amount) || Number(amount) < 1 || Number(amount) > 999999999;
    }) || rows.at(-1);
    if (row) input = row.querySelector(row.querySelector('[data-item-name]').value.trim() ? '[data-item-amount]' : '[data-item-name]');
  }
  error.textContent = message;
  error.hidden = false;
  if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
}

function itemRowsFromForm() {
  return [...document.querySelectorAll('#item-rows .item-row')].map((row) => ({
    name: row.querySelector('[data-item-name]').value,
    amount: row.querySelector('[data-item-amount]').value,
  }));
}

function syncAmountFromItems() {
  const amountInput = document.getElementById('amount-input');
  const rows = itemRowsFromForm();
  const itemized = document.querySelector('input[name="type"]:checked').value === 'expense' && rows.length > 0;
  amountInput.readOnly = itemized;
  amountInput.required = !itemized;
  if (!itemized) return;
  const amounts = rows.map((row) => Number(row.amount));
  const valid = rows.every((row, index) => row.name.trim() && /^\d+$/.test(row.amount.trim()) && Number.isInteger(amounts[index]) && amounts[index] > 0);
  const total = amounts.reduce((sum, amount) => sum + amount, 0);
  amountInput.value = valid && total <= 999999999 ? String(total) : '';
}

function syncExpenseFields() {
  const expense = document.querySelector('input[name="type"]:checked').value === 'expense';
  const fields = document.getElementById('expense-fields');
  fields.hidden = !expense;
  fields.querySelectorAll('input,select,button').forEach((element) => { element.disabled = !expense; });
  if (expense) syncAmountFromItems();
  else {
    const amountInput = document.getElementById('amount-input');
    if (itemRowsFromForm().length) amountInput.value = manualAmountBeforeItems;
    amountInput.readOnly = false;
    amountInput.required = true;
  }
}

function openDialog() {
  const dialog = document.getElementById('transaction-dialog');
  const form = document.getElementById('transaction-form');
  form.reset();
  document.getElementById('item-rows').replaceChildren();
  manualAmountBeforeItems = '';
  clearFormErrors();
  const today = new Date();
  document.getElementById('date-input').value = monthKey(visibleMonth) === monthKey(today) ? `${monthKey(today)}-${String(today.getDate()).padStart(2, '0')}` : `${monthKey(visibleMonth)}-01`;
  updateCategoryOptions();
  dialog.showModal();
  form.elements.title.focus();
}
function updateCategoryOptions() {
  const type = document.querySelector('input[name="type"]:checked').value;
  document.getElementById('category-input').innerHTML = (type === 'income' ? ['収入'] : categories.map((item) => item.name)).map((name) => `<option value="${name}">${name}</option>`).join('');
  syncExpenseFields();
}
document.getElementById('add-item').addEventListener('click', () => {
  const rows = document.getElementById('item-rows');
  if (!rows.children.length) manualAmountBeforeItems = document.getElementById('amount-input').value;
  itemRowSequence += 1;
  const row = document.createElement('div');
  row.className = 'item-row';
  row.innerHTML = `<label><span>品目名</span><input data-item-name type="text" maxlength="60" aria-label="品目${itemRowSequence}の名前" aria-describedby="items-error" placeholder="例：パン" /></label><label><span>金額</span><input data-item-amount type="number" inputmode="numeric" min="1" max="999999999" aria-label="品目${itemRowSequence}の金額（円）" aria-describedby="items-error" placeholder="0" /></label><button class="remove-item" type="button" aria-label="品目${itemRowSequence}を削除">×</button>`;
  rows.append(row);
  syncAmountFromItems();
  row.querySelector('[data-item-name]').focus();
});
document.getElementById('item-rows').addEventListener('input', () => {
  syncAmountFromItems();
  document.getElementById('items-error').hidden = true;
});
document.getElementById('item-rows').addEventListener('click', (event) => {
  const button = event.target.closest('.remove-item');
  if (!button) return;
  button.closest('.item-row').remove();
  if (!document.getElementById('item-rows').children.length) document.getElementById('amount-input').value = manualAmountBeforeItems;
  syncAmountFromItems();
  document.getElementById('add-item').focus();
});
document.querySelectorAll('.add-trigger').forEach((button) => button.addEventListener('click', openDialog));
document.querySelectorAll('.close-dialog').forEach((button) => button.addEventListener('click', () => document.getElementById('transaction-dialog').close()));
document.querySelectorAll('input[name="type"]').forEach((input) => input.addEventListener('change', updateCategoryOptions));
document.getElementById('transaction-dialog').addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
document.getElementById('prev-month').addEventListener('click', () => { visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1); document.getElementById('month-label').textContent = `${visibleMonth.getFullYear()}年${visibleMonth.getMonth() + 1}月`; render(); });
document.getElementById('next-month').addEventListener('click', () => { visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1); document.getElementById('month-label').textContent = `${visibleMonth.getFullYear()}年${visibleMonth.getMonth() + 1}月`; render(); });
document.getElementById('transaction-search').addEventListener('input', () => renderTransactions(monthTransactions()));
document.getElementById('type-filter').addEventListener('change', () => renderTransactions(monthTransactions()));
document.getElementById('transaction-rows').addEventListener('click', (event) => {
  const link = event.target.closest('.transaction-link');
  if (link) listReturnState = { id: link.dataset.id, scrollY: window.scrollY };
});
document.querySelectorAll('.sidebar a[href^="#"]').forEach((link) => link.addEventListener('click', () => {
  if (showingDetail && link.hash !== '#transactions') listReturnState = null;
}));
document.getElementById('transaction-form').addEventListener('submit', (event) => {
  event.preventDefault();
  clearFormErrors();
  const data = new FormData(event.currentTarget);
  const title = String(data.get('title')).trim();
  const date = String(data.get('date'));
  const type = String(data.get('type'));
  const category = String(data.get('category'));
  const parsedDate = new Date(`${date}T12:00:00`);
  if (!title) { showFieldError('title', '内容を入力してください。'); return; }
  if (Number.isNaN(parsedDate.getTime()) || date !== `${parsedDate.getFullYear()}-${String(parsedDate.getMonth() + 1).padStart(2, '0')}-${String(parsedDate.getDate()).padStart(2, '0')}`) { showFieldError('date', '正しい日付を入力してください。'); return; }
  let amount;
  let details = {};
  if (type === 'expense') {
    try {
      details = KakeiTransactionData.parseExpenseDraft({
        merchant: data.get('merchant'), paymentMethod: data.get('paymentMethod'),
        itemRows: itemRowsFromForm(), manualAmount: document.getElementById('amount-input').value,
      });
      amount = details.amount;
    } catch (error) {
      if (error instanceof KakeiTransactionData.ValidationError) { showFieldError(error.field, error.message); return; }
      throw error;
    }
  } else {
    const rawAmount = document.getElementById('amount-input').value.trim();
    amount = Number(rawAmount);
    if (!/^\d+$/.test(rawAmount) || !Number.isInteger(amount) || amount < 1 || amount > 999999999) { showFieldError('amount', '1円から999,999,999円までの整数を入力してください。'); return; }
  }
  const newRecord = { id: globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `entry-${Date.now()}`, title, amount, date, type, category, ...details };
  try {
    transactions = KakeiTransactionData.persistAddedTransaction(transactions, newRecord, localStorage, storageKey, isValidTransaction);
  } catch (_) {
    const error = document.getElementById('form-error');
    error.textContent = '保存できませんでした。ブラウザの保存設定をご確認ください。';
    error.hidden = false;
    return;
  }
  visibleMonth = new Date(parsedDate.getFullYear(), parsedDate.getMonth(), 1);
  document.getElementById('transaction-dialog').close();
  render();
  showToast('取引を追加しました。');
});
document.getElementById('detail-delete').addEventListener('click', () => {
  const id = KakeiDetail.detailIdFromHash(window.location.hash);
  const item = transactions.find((entry) => entry.id === id);
  if (!item) { renderRoute(); return; }
  if (!confirm(`「${item.title}」を削除しますか？`)) return;
  try {
    transactions = KakeiDetail.removePersistedTransaction(transactions, id, localStorage, storageKey, isValidTransaction);
  } catch (_) {
    showToast('保存できませんでした。ブラウザの保存設定をご確認ください。');
    return;
  }
  listReturnState = null;
  render();
  window.location.hash = '#transactions';
  showToast('取引を削除しました。');
});
document.getElementById('clear-demo').addEventListener('click', () => {
  if (!confirm('サンプルデータをすべて削除しますか？')) return;
  try {
    transactions = KakeiDetail.removePersistedSamples(transactions, localStorage, storageKey, isValidTransaction);
  } catch (_) {
    showToast('保存できませんでした。ブラウザの保存設定をご確認ください。');
    return;
  }
  render();
  showToast('サンプルデータを削除しました。');
});
window.addEventListener('storage', (event) => {
  if (event.key !== storageKey) return;
  try {
    const updated = event.newValue === null ? [] : JSON.parse(event.newValue);
    if (!Array.isArray(updated)) return;
    transactions = updated.filter(isValidTransaction);
    render();
    renderRoute();
  } catch (_) { /* Ignore malformed updates from another tab. */ }
});
document.getElementById('export-button').addEventListener('click', () => {
  const items = monthTransactions();
  if (!items.length) { showToast('この月に保存できる取引はありません。'); return; }
  const csv = KakeiTransactionData.serializeTransactionsCsv(items);
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = `kakei-${monthKey(visibleMonth)}.csv`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast('CSVを保存しました。');
});
window.addEventListener('hashchange', renderRoute);
document.getElementById('today-label').textContent = new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }).format(now);
document.getElementById('month-label').textContent = `${visibleMonth.getFullYear()}年${visibleMonth.getMonth() + 1}月`;

async function loadFromServer() {
  if (loadingData) return;
  loadingData = true;
  const dashboard = document.getElementById('dashboard-view');
  const status = document.getElementById('data-status');
  dashboard.setAttribute('aria-busy', 'true');
  status.hidden = true;
  document.getElementById('balance-amount').textContent = '—';
  document.getElementById('balance-message').textContent = '取引を読み込んでいます';
  document.querySelectorAll('.add-trigger').forEach((button) => { button.disabled = true; });
  document.getElementById('export-button').disabled = true;
  try {
    transactions = await KakeiApi.loadInitialTransactions({ fetchImpl: fetch, storage: localStorage, sampleFactory: sampleTransactions });
    dataReady = true;
    dashboard.classList.add('data-ready');
    dashboard.removeAttribute('aria-busy');
    document.querySelectorAll('.add-trigger').forEach((button) => { button.disabled = false; });
    document.getElementById('export-button').disabled = false;
    render();
    renderRoute();
  } catch (error) {
    dashboard.removeAttribute('aria-busy');
    document.getElementById('balance-message').textContent = '取引を読み込めませんでした';
    document.getElementById('data-status-message').textContent = error.message || 'サーバーへの接続を確認してください。';
    status.hidden = false;
  } finally {
    loadingData = false;
  }
}

document.getElementById('retry-load').addEventListener('click', loadFromServer);
loadFromServer();
