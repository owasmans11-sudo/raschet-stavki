// Экспедирование через склад: вкладки Заявки / Склад / Фуры / Склады.
// Все данные берём с сервера одним запросом (/api/state), действия — POST /api/<действие>.
'use strict';

let S = null;                       // состояние с сервера
let tab = 'zayavki';
const ui = { q: '', status: '', manager: '', sklad: null, fura: null };
try { Object.assign(ui, JSON.parse(localStorage.getItem('sklad-ui') || '{}')); tab = ui.tab || tab; } catch (e) {}

const STATUSES = ['ждёт забора', 'на складе', 'в фуре', 'прибыл', 'доставлен'];
const ST_CLASS = { 'ждёт забора': 'st-zhdet', 'на складе': 'st-sklad', 'в фуре': 'st-fura', 'прибыл': 'st-pribyl', 'доставлен': 'st-dost' };
const COMPANIES = ['ООО ВЛ', 'ИП Шерстов', 'ТК МВЛ'];
const PAY_FORMS = ['с НДС', 'без НДС', 'наличные'];

// ---------- помощники ----------
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = v => (v === '' || v == null || isNaN(+v)) ? null : +v;
const rub = v => v == null ? '' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const n1 = (v, d = 2) => v == null ? '' : (+v).toLocaleString('ru-RU', { maximumFractionDigits: d });
const dmy = iso => iso ? iso.split('-').reverse().join('.') : '';
const days = iso => iso ? Math.round((new Date(S.today) - new Date(iso)) / 864e5) : null;
const sklad = id => S.sklady.find(s => s.id === id);
const skName = id => sklad(id)?.name || '';
const fura = id => S.furas.find(f => f.id === id);
const badge = st => `<span class="badge ${ST_CLASS[st] || ''}">${esc(st)}</span>`;
const opts = (list, val, empty = '—') =>
  (empty != null ? `<option value="">${empty}</option>` : '') +
  list.map(([v, t]) => `<option value="${esc(v)}"${String(v) === String(val ?? '') ? ' selected' : ''}>${esc(t)}</option>`).join('');
const skladOpts = (val, empty = '—') => opts(S.sklady.map(s => [s.id, s.name]), val, empty);
const managerNames = () => S.managers.map(m => m.name);
const formOpts = val => opts(PAY_FORMS.map(c => [c, c]), val);

function saveUi() { try { localStorage.setItem('sklad-ui', JSON.stringify({ ...ui, tab })); } catch (e) {} }

function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg; t.className = err ? 'err' : ''; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, err ? 6000 : 2500);
}

async function load() {
  const r = await fetch('/api/state');
  if (r.status === 401) { location.href = '/login'; return; }
  S = await r.json();
  render();
}

async function api(action, data, okMsg) {
  const r = await fetch('/api/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  if (r.status === 401) { location.href = '/login'; throw new Error('нужно войти'); }
  const res = await r.json();
  if (!r.ok) { toast(res.error || 'Ошибка', true); throw new Error(res.error); }
  if (okMsg) toast(okMsg);
  await load();
  return res;
}

// ---------- расчёты ----------
function legsSum(g) { return ['zabor', 'razvoz'].reduce((s, k) => s + (num(g.legs[k]?.rate) || 0), 0); }

const gruzReys = g => S.reys.filter(r => r.gruz_id === g.id);    // фуры груза по порядку (перегруз — несколько)
const gruzById = id => S.gruzy.find(g => g.id === id);

// ----- зарплата с прибыли: правила как в «Зарплата с прибыли по фурам.xlsx» (tools/zarplata_fury.py) -----
const KF = { 'с НДС': 1.22, 'без НДС': 1.06, 'наличные': 1 };          // форма оплаты → коэффициент
const REGIME = { 'ООО ВЛ': 'ОСНО', 'ТК МВЛ': 'ОСНО', 'ИП Шерстов': 'УСН' };  // режим налога компании (Андрей)
const ZP_PCT = 0.20, NNP = 0.25;                                       // зп логиста от остатка; налог на прибыль ОСНО
const vat = (sum, form) => form === 'с НДС' ? (num(sum) || 0) - (num(sum) || 0) / 1.22 : 0;

// общие расходы фуры (фура + склад погрузки + склад приёмки + прочие) и НДС в них
function furaCommon(f) {
  const items = [[f.rate, f.rate_form], [f.sklad_load, f.sklad_load_form], [f.sklad_unload, f.sklad_unload_form], [f.other, f.other_form]];
  return { sum: items.reduce((s, [v]) => s + (num(v) || 0), 0), vat: items.reduce((s, [v, fm]) => s + vat(v, fm), 0) };
}
const furaKg = f => S.reys.filter(r => r.fura_id === f.id).reduce((s, r) => s + (num(gruzById(r.gruz_id)?.kg) || 0), 0);

function furaCalc(f) {
  const rs = S.reys.filter(r => r.fura_id === f.id).map(r => ({ ...r, g: gruzById(r.gruz_id) })).filter(r => r.g);
  const gs = rs.map(r => r.g);
  const kg = furaKg(f);
  const m3 = gs.reduce((s, g) => s + (num(g.m3) || 0), 0);
  const common = furaCommon(f).sum;
  const perKg = kg ? common / kg : 0;
  const share = g => (num(g.kg) || 0) * perKg;
  const income = gs.reduce((s, g) => s + (num(g.rate_client) || 0), 0);
  const legs = gs.reduce((s, g) => s + legsSum(g), 0);
  const multi = gs.some(g => gruzReys(g).length > 1);
  // остаток фуры = сумма остатков её грузов (у груза с перегрузом остаток общий по всем фурам)
  const profit = gs.reduce((s, g) => s + calc(g).profit, 0);
  return { rs, gs, kg, m3, common, perKg, share, income, legs, multi, profit };
}

// Остаток прибыли и зарплата по грузу:
// прибыль до НП = выручка − налог с выручки − свои расходы + НДС своих к вычету − доля общих фур + НДС в доле;
// НДС к вычету — только если клиент «с НДС», компания на ОСНО и расход «с НДС»;
// налог на прибыль 25% — ОСНО, не наличные, прибыль в плюсе; зп = 20% от остатка, начисляется после полной оплаты.
function calc(g) {
  const rev = num(g.rate_client) || 0;
  const kf = KF[g.pay_form];
  const osno = REGIME[g.company] === 'ОСНО';
  const nalog = kf ? rev - rev / kf : 0;
  const legs = [g.legs.zabor, g.legs.razvoz].filter(Boolean);
  const own = legsSum(g) + (num(g.other_cost) || 0);
  const vatOn = g.pay_form === 'с НДС' && osno;
  const ownVat = vatOn ? legs.reduce((s, l) => s + vat(l.rate, l.pay_form), 0) + vat(g.other_cost, g.other_form) : 0;
  let share = 0, shareVat = 0;
  for (const r of gruzReys(g)) {
    const f = fura(r.fura_id), kg = f && furaKg(f);
    if (!kg) continue;
    const c = furaCommon(f), w = num(g.kg) || 0;
    share += w * c.sum / kg;
    if (vatOn) shareVat += w * c.vat / kg;
  }
  const before = rev - nalog - own + ownVat - share + shareVat;
  const np = osno && g.pay_form !== 'наличные' && before > 0 ? before * NNP : 0;
  const profit = before - np;
  const paid = num(g.paid_sum) || 0;
  const payStatus = !rev ? '' : paid >= rev ? 'оплачено' : paid > 0 ? 'частично' : 'не оплачено';
  const zp = Math.max(profit, 0) * ZP_PCT;
  const zpNach = payStatus === 'оплачено' ? zp : 0;
  const problems = [];
  if (!g.manager) problems.push('нет менеджера');
  if (rev && !kf) problems.push('нет формы оплаты клиента');
  if (!rev) problems.push('нет ставки клиента');
  if (gruzReys(g).length && !num(g.kg)) problems.push('нет веса — доля фуры 0');
  if (payStatus === 'оплачено' && !g.paid_date) problems.push('оплачено, но нет даты оплаты');
  return { rev, kf, osno, nalog, own, ownVat, share, shareVat, before, np, profit, paid, payStatus,
           debt: Math.max(rev - paid, 0), zp, zpNach, zpWait: zp - zpNach, problems };
}
const gruzProfit = calc;

function lastLog(g, ...actions) {
  return S.log.filter(l => l.gruz_id === g.id && (!actions.length || actions.includes(l.action))).at(-1);
}

function whereNow(g) {
  if (g.status === 'в фуре') { const f = fura(g.fura_id); return `фура ${esc(f?.nomer_ts || '')}`; }
  if (g.sklad_id) return 'склад ' + esc(skName(g.sklad_id));
  if (g.status === 'доставлен') return 'у клиента';
  return 'у отправителя';
}

// ---------- отрисовка ----------
function render() {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  ({ zayavki: viewZayavki, sklad: viewSklad, fury: viewFury, zp: viewZp, opl: viewOplaty, vod: viewVoditeli, firm: viewFirmy, nastr: viewNastr })[tab]();
}

$('#tabs').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  tab = b.dataset.tab; saveUi(); render();
});

// ===== Вкладка «Заявки» =====
function viewZayavki() {
  const q = ui.q.toLowerCase();
  const NOMAN = '(без менеджера)';
  const list = S.gruzy.filter(g => (!ui.status || g.status === ui.status) &&
    (!ui.manager || (ui.manager === NOMAN ? !g.manager : g.manager === ui.manager)) &&
    (!q || [g.nomer, g.client, g.cargo, g.from_addr, g.to_addr, g.legs.zabor?.carrier, g.legs.razvoz?.carrier]
      .join(' ').toLowerCase().includes(q)));
  const cnt = st => S.gruzy.filter(g => g.status === st).length;
  $('#view').innerHTML = `
    <div class="bar">
      <h2 class="grow">Заявки (грузы клиентов)</h2>
      <input id="q" placeholder="Поиск: клиент, груз, адрес, перевозчик" value="${esc(ui.q)}" style="width:300px">
      <select id="st">${opts(STATUSES.map(s => [s, `${s} (${cnt(s)})`]), ui.status, `все статусы (${S.gruzy.length})`)}</select>
      <select id="mg">${opts([...managerNames(), NOMAN].map(m => [m, `${m} (${S.gruzy.filter(g => m === NOMAN ? !g.manager : g.manager === m).length})`]),
        ui.manager, 'все менеджеры')}</select>
      <button class="btn" id="add">+ Новый груз</button>
      <button class="btn light" id="xls">В Excel</button>
    </div>
    ${list.length ? `<table><thead><tr>
      <th>№</th><th>Менеджер</th><th>Клиент</th><th>Груз</th><th class="num">кг</th><th class="num">м³</th>
      <th>Маршрут по складам</th><th>Статус</th><th>Где сейчас</th><th class="num">Ставка клиента</th><th class="num">Прибыль*</th>
    </tr></thead><tbody>${list.map(g => {
      const p = gruzProfit(g);
      return `<tr class="click" data-id="${g.id}">
        <td>${esc(g.nomer)}</td><td class="${g.manager ? '' : 'gap'}">${esc(g.manager)}</td><td>${esc(g.client)}</td><td>${esc(g.cargo)}</td>
        <td class="num${g.kg ? '' : ' gap'}">${n1(g.kg, 0)}</td><td class="num">${n1(g.m3)}</td>
        <td>${esc(skName(g.sklad_from) || '?')} → ${esc(skName(g.sklad_to) || '?')}</td>
        <td>${badge(g.status)}</td><td>${whereNow(g)}</td>
        <td class="num">${rub(g.rate_client)}</td><td class="num${p.profit < 0 ? ' minus' : ''}">${rub(p.profit)}</td></tr>`;
    }).join('')}</tbody>
    <tfoot><tr><td colspan="9">Итого${ui.manager ? ' — ' + esc(ui.manager) : ''}: ${list.length} заявок</td>
      <td class="num">${rub(list.reduce((s, g) => s + (num(g.rate_client) || 0), 0))}</td>
      <td class="num">${rub(list.reduce((s, g) => s + gruzProfit(g).profit, 0))}</td></tr></tfoot></table>
    <p class="hint">* Остаток прибыли после налогов и всех расходов (разбор — в карточке груза). Зарплата — вкладка «Зарплата».</p>`
    : `<div class="empty">Грузов нет. Нажмите «+ Новый груз».</div>`}`;
  $('#q').oninput = e => { ui.q = e.target.value; saveUi(); viewZayavki(); const i = $('#q'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $('#st').onchange = e => { ui.status = e.target.value; saveUi(); viewZayavki(); };
  $('#mg').onchange = e => { ui.manager = e.target.value; saveUi(); viewZayavki(); };
  $('#add').onclick = () => openGruz(null);
  $('#xls').onclick = () => openExport(ui.manager);
  $('#view').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => openGruz(+tr.dataset.id));
}

// ===== Карточка груза =====
function chainHtml(g) {
  const z = g.legs.zabor || {}, r = g.legs.razvoz || {};
  const accepted = lastLog(g, 'принят на склад');
  // шаг: [название, текст, дата, пройден?]
  const steps = [
    ['Забор', `${esc(z.from_addr || g.from_addr || 'адрес не указан')}<br>${esc(z.carrier || '')} ${z.rate ? rub(z.rate) : ''}`, z.dt, !!accepted],
    ['Склад ' + esc(skName(g.sklad_from) || '?'), accepted ? 'принят' : 'ещё не принят', accepted?.dt, gruzReys(g).length > 0 || g.status === 'доставлен'],
  ];
  const rs = gruzReys(g);
  rs.forEach((rr, i) => {
    const f = fura(rr.fura_id);
    const out = S.log.find(l => l.gruz_id === g.id && l.fura_id === rr.fura_id && l.action.startsWith('выгружен'));
    const final = !rr.point || rr.point === g.sklad_to;
    steps.push([`Фура${rs.length > 1 ? ' ' + (i + 1) : ''}`,
      `${esc(f?.nomer_ts || '')} ${esc(f?.carrier || '')}<br>${esc(f?.status || '')}`, f?.dt_out, !!out]);
    steps.push([`Склад ${esc(skName(rr.point) || '?')}${final ? '' : ' (перегруз)'}`,
      out ? 'выгружен' : 'ещё не прибыл', out?.dt, out && (i < rs.length - 1 || !final || g.status === 'доставлен')]);
  });
  if (!rs.length) {
    steps.push(['Фура', 'не назначена', '', false]);
    steps.push(['Склад ' + esc(skName(g.sklad_to) || '?'), 'ещё не прибыл', '', false]);
  }
  const done = lastLog(g, 'выдан на развоз / доставлен');
  steps.push(['Развоз', `${esc(r.to_addr || g.to_addr || 'адрес не указан')}<br>${esc(r.carrier || '')} ${r.rate ? rub(r.rate) : ''}`, done?.dt || r.dt, !!done]);
  const now = steps.findIndex(s => !s[3]);
  return `<div class="chain">${steps.map(([n, t, d, ok], i) =>
    `<div class="step ${ok ? 'done' : i === now ? 'now' : ''}"><div class="n">${i + 1}. ${n}</div><div>${t}</div><div class="d">${dmy(d)}</div></div>`).join('')}</div>`;
}

// разбор остатка прибыли и зарплаты по грузу — строка за строкой, как в таблице зп
function zpHtml(g, p) {
  const line = (t, v, sign = '', cls = '') => v ? `<tr><td>${t}</td><td class="num ${cls}">${sign}${rub(Math.abs(v))}</td></tr>` : '';
  const pay = { 'оплачено': 'st-pribyl', 'частично': 'st-zhdet', 'не оплачено': 'st-fura' }[p.payStatus] || '';
  return `<fieldset><legend>Остаток прибыли и зарплата менеджера</legend>
    <table style="max-width:560px"><tbody>
      ${line('Выручка (ставка клиента)', p.rev)}
      ${line(`Налог с выручки (${esc(g.pay_form || 'форма не указана')}, Кф ${p.kf || '—'})`, p.nalog, '− ')}
      ${line('Свои расходы (забор, развоз, прочие)', p.own, '− ')}
      ${line('НДС своих перевозчиков к вычету', p.ownVat, '+ ')}
      ${line('Доля общих расходов фур (по кг)', p.share, '− ')}
      ${line('НДС в доле общих к вычету', p.shareVat, '+ ')}
      ${line(`Налог на прибыль ${NNP * 100}% (${esc(g.company)} — ОСНО)`, p.np, '− ')}
      <tr><td><b>Остаток прибыли</b></td><td class="num"><b class="${p.profit < 0 ? 'minus' : ''}">${p.profit < 0 ? '− ' : ''}${rub(Math.abs(p.profit))}</b></td></tr>
      <tr><td>Зарплата ${esc(g.manager || 'менеджера')} (${ZP_PCT * 100}% от остатка)</td><td class="num"><b>${rub(p.zp)}</b></td></tr>
      <tr><td>Оплата клиента: <span class="badge ${pay}">${esc(p.payStatus || '—')}</span>${p.debt && p.paid ? ` долг ${rub(p.debt)}` : ''}</td>
        <td class="num">${p.zpNach ? 'начислено ' + (g.paid_date ? 'за ' + dmy(g.paid_date).slice(3) : '') : p.zp ? 'ждёт оплаты' : ''}</td></tr>
    </tbody></table>
    ${p.problems.length ? `<p class="minus">Мешает расчёту: ${p.problems.map(esc).join('; ')}.</p>` : ''}
  </fieldset>`;
}

function legFields(kind, title, l = {}) {
  const f = (k, lab, type = 'text', cls = '') =>
    `<label class="${cls}">${lab}<input data-leg="${kind}" name="${k}" type="${type}" value="${esc(l[k] ?? '')}"></label>`;
  return `<fieldset><legend>${title}</legend><div class="grid">
    ${f('zayavka', '№ заявки перевозчику')}${f('dt', 'Дата', 'date')}
    ${f('from_addr', 'Откуда', 'text', 'wide')}${f('to_addr', 'Куда', 'text', 'wide')}
    <label class="wide">Перевозчик — из справочника или текстом
      <span style="display:flex;gap:6px"><input data-leg="${kind}" name="carrier" list="firmList" value="${esc(l.carrier ?? '')}" style="flex:1">
      <button type="button" class="btn small light" data-firmfiles="${kind}" title="Реквизиты из карточки предприятия">из файлов</button></span>
      <input type="hidden" data-leg="${kind}" name="carrier_id" value="${esc(l.carrier_id ?? '')}"></label>
    <label class="wide">Водитель — из справочника или текстом
      <span style="display:flex;gap:6px"><input data-leg="${kind}" name="driver" list="vodList" value="${esc(l.driver ?? '')}" style="flex:1">
      <button type="button" class="btn small light" data-vodfiles="${kind}" title="Распознать паспорт, права, СТС">из файлов</button></span>
      <input type="hidden" data-leg="${kind}" name="voditel_id" value="${esc(l.voditel_id ?? '')}"></label>
    ${f('rate', 'Ставка перевозчику, ₽', 'number')}
    <label>Форма оплаты перевозчику<select data-leg="${kind}" name="pay_form">${formOpts(l.pay_form)}</select></label>
  </div></fieldset>`;
}

function openGruz(id) {
  const g = id ? S.gruzy.find(x => x.id === id) : { legs: {}, status: 'ждёт забора', company: 'ООО ВЛ' };
  const f = (k, lab, type = 'text', cls = '') =>
    `<label class="${cls}">${lab}<input name="${k}" type="${type}" ${type === 'number' ? 'step="any"' : ''} value="${esc(g[k] ?? '')}"></label>`;
  const p = id ? gruzProfit(g) : null;
  const myOpl = id ? S.oplaty.filter(o => o.gruz_id === id) : [];
  let act = '';
  if (id && g.status === 'ждёт забора')
    act = `<div class="actions"><b>Груз привезли на склад?</b>
      <select id="aSk">${skladOpts(g.sklad_from, null)}</select><input id="aDt" type="date" value="${S.today}">
      <button class="btn" id="aGo">Принять на склад</button></div>`;
  else if (id && (g.status === 'прибыл' || g.status === 'на складе'))
    act = `<div class="actions"><b>Груз на складе ${esc(skName(g.sklad_id))}.</b>
      ${g.status === 'на складе' ? '<span class="muted">Чтобы отправить фурой — вкладка «Фуры».</span>' : ''}
      <input id="aDt" type="date" value="${S.today}"><button class="btn${g.status === 'на складе' ? ' light' : ''}" id="aGo">Выдать на развоз / клиенту</button></div>`;
  else if (id && g.status === 'в фуре') {
    const rr = gruzReys(g).find(r => r.fura_id === g.fura_id);
    act = `<div class="actions">Груз едет в фуре ${esc(fura(g.fura_id)?.nomer_ts || '')}, выгрузка — склад ${esc(skName(rr?.point) || 'НЕ УКАЗАН')}.</div>`;
  }
  if (id && g.status !== 'в фуре' && g.status !== 'доставлен')
    act += `<div class="actions"><b>Разделить груз:</b> отделить
      <input id="spKg" type="number" step="any" placeholder="кг" style="width:90px" title="из ${n1(g.kg, 0)} кг">
      <input id="spM3" type="number" step="any" placeholder="м³" style="width:80px" title="из ${n1(g.m3)} м³">
      <input id="spPl" type="number" placeholder="мест" style="width:80px" title="из ${n1(g.places, 0)} мест">
      <button class="btn light" id="spGo">Отделить часть</button>
      <span class="hint">сейчас: ${n1(g.kg, 0) || '—'} кг · ${n1(g.m3) || '—'} м³ · ${n1(g.places, 0) || '—'} мест. Ставки поделятся по весу.</span></div>`;
  const kids = id ? S.gruzy.filter(x => x.parent_id === id) : [];
  const parent = g.parent_id && gruzById(g.parent_id);
  if (parent || kids.length)
    act += `<p>Части одного груза: ${[parent, ...kids].filter(Boolean).map(x =>
      `<a href="#" data-goto="${x.id}">${esc(x.nomer)}</a> (${esc(x.status)})`).join(', ')}</p>`;

  openModal(`
    <div class="head"><h2>${id ? esc(g.nomer) + ' · ' + esc(g.client || '') : 'Новый груз'} ${id ? badge(g.status) : ''}</h2><button class="x" data-close>×</button></div>
    ${id ? chainHtml(g) : ''}
    <div class="actions"><button type="button" class="btn" id="fromZ">📄 Заполнить из заявки клиента</button>
      <span class="hint">заказчик с реквизитами + адреса, даты, груз, вес, ставка — только в пустые поля</span></div>
    ${act}
    ${id ? `<div class="actions"><b>Печать заявки (Word):</b>
      <button class="btn light" data-print="klient">с клиентом</button>
      <button class="btn light" data-print="zabor">перевозчику — забор</button>
      <button class="btn light" data-print="razvoz">перевозчику — развоз</button>
      <span class="hint">сначала сохраняет карточку</span></div>` : ''}
    <form id="gf">
      <fieldset><legend>Клиент и груз</legend><div class="grid">
        <label class="wide">Заказчик — из справочника или текстом
          <span style="display:flex;gap:6px"><input name="client" list="firmList" value="${esc(g.client ?? '')}" style="flex:1">
          <button type="button" class="btn small light" data-firmfiles="client" title="Реквизиты из карточки предприятия или заявки">из файлов</button></span>
          <input type="hidden" name="client_id" value="${esc(g.client_id ?? '')}"></label>
        <label>Менеджер (ведёт заявку)<select name="manager">${opts(
          [...new Set([...managerNames(), ...(g.manager ? [g.manager] : [])])].map(m => [m, m]), g.manager, 'не выбран')}</select></label>
        <label>Наша компания<select name="company">${opts(COMPANIES.map(c => [c, c]), g.company, null)}</select></label>
        <label>Форма оплаты клиента<select name="pay_form">${formOpts(g.pay_form)}</select></label>
        ${f('cargo', 'Груз', 'text', 'wide')}${f('kg', 'Вес, кг', 'number')}${f('m3', 'Объём, м³', 'number')}${f('places', 'Мест', 'number')}
        ${f('rate_client', 'Ставка клиента, ₽', 'number')}
        ${f('from_addr', 'Откуда (адрес забора)', 'text', 'wide')}${f('to_addr', 'Куда (адрес доставки)', 'text', 'wide')}
        <label>Склад отправки<select name="sklad_from">${skladOpts(g.sklad_from)}</select></label>
        <label>Склад назначения<select name="sklad_to">${skladOpts(g.sklad_to)}</select></label>
        <label class="full">Примечание<textarea name="note" rows="2">${esc(g.note || '')}</textarea></label>
      </div></fieldset>
      ${vodDatalist()}${firmDatalist()}
      ${legFields('zabor', 'Отрезок 1 — забор (до склада)', g.legs.zabor)}
      ${legFields('razvoz', 'Отрезок 3 — развоз (со склада до клиента)', g.legs.razvoz)}
      <p class="muted">Отрезок 2 (межгород) — это фура, её собирают во вкладке «Фуры».</p>
      <fieldset><legend>Прочие расходы и оплата клиента</legend><div class="grid">
        ${f('other_cost', 'Прочие расходы (СДЭК, кран), ₽', 'number')}
        <label>Форма оплаты прочих<select name="other_form">${formOpts(g.other_form)}</select></label>
        ${f('schet', 'Счёт клиенту №')}
        ${myOpl.length ? `<label>Клиент оплатил, ₽<input name="paid_sum" type="number" value="${esc(g.paid_sum ?? '')}" readonly
            title="Считается из платежей выписки"></label><label>Дата полной оплаты<input name="paid_date" type="date" value="${esc(g.paid_date || '')}" readonly></label>`
          : f('paid_sum', 'Клиент оплатил, ₽', 'number') + f('paid_date', 'Дата полной оплаты', 'date')}
      </div>
      ${myOpl.length ? `<p class="hint">Оплата из банковской выписки${num(g.paid_manual) ? ` + введено руками ${rub(g.paid_manual)}` : ''}:</p>
        <table><tbody>${myOpl.map(o => `<tr><td>${dmy(o.dt)}</td><td>п/п ${esc(o.num)}</td><td>${esc(o.company)}</td><td>${esc(o.payer)}</td>
          <td class="num">${rub(o.sum)}</td><td><button type="button" class="btn small red" data-unlink="${o.id}">отвязать</button></td></tr>`).join('')}</tbody></table>`
        : '<p class="hint">Платежи из выписки привязываются во вкладке «Оплаты». Наличные — вводите руками.</p>'}
      </fieldset>
      ${p ? zpHtml(g, p) : ''}
      <div class="foot">
        <div>${id ? '<button type="button" class="btn red" id="del">Удалить груз</button>' : ''}</div>
        <div><button type="button" class="btn light" data-close>Закрыть</button> <button class="btn">Сохранить</button></div>
      </div>
    </form>`);

  const form = $('#gf');
  const collect = () => {
    const d = { id };
    form.querySelectorAll('[name]:not([data-leg])').forEach(i => d[i.name] = i.value);
    for (const k of ['kg', 'm3', 'places', 'rate_client', 'sklad_from', 'sklad_to', 'other_cost', 'paid_sum', 'client_id']) d[k] = num(d[k]);
    d.legs = {};
    form.querySelectorAll('[data-leg]').forEach(i => {
      (d.legs[i.dataset.leg] ||= {})[i.name] = ['rate', 'voditel_id', 'carrier_id'].includes(i.name) ? num(i.value) : i.value;
    });
    return d;
  };
  form.onsubmit = async e => {
    e.preventDefault();
    const res = await api('gruz_save', collect(), 'Сохранено');
    openGruz(res.id);
  };
  // водитель: выбор из подсказки → id из справочника (и перевозчик, если пусто); «из файлов» → окно распознавания
  form.querySelectorAll('input[name=driver][data-leg]').forEach(i => i.onchange = () => {
    const v = S.voditeli.find(x => vodLabel(x) === i.value);
    form.querySelector(`input[name=voditel_id][data-leg="${i.dataset.leg}"]`).value = v ? v.id : '';
    const car = form.querySelector(`input[name=carrier][data-leg="${i.dataset.leg}"]`);
    if (v && v.carrier && !car.value) car.value = v.carrier;
  });
  // заявка клиента → заказчик и данные груза; заполняем только пустое, ничего введённого не перетираем
  $('#fromZ').onclick = async () => {
    const gid = (await api('gruz_save', collect())).id;
    openFirma(null, async (fm, gz) => {
      const g2 = gruzById(gid), upd = { ...g2 };
      const setIf = (k, v) => { if (v != null && v !== '' && (upd[k] == null || upd[k] === '')) upd[k] = v; };
      if (fm) { setIf('client', fm.name); if (!upd.client_id) upd.client_id = fm.id; }
      setIf('from_addr', gz.from_addr); setIf('to_addr', gz.to_addr); setIf('cargo', gz.cargo); setIf('pay_form', gz.pay_form);
      for (const k of ['kg', 'm3', 'places', 'rate_client']) setIf(k, num(gz[k]));
      if (gz.client_doc && !(upd.note || '').includes(gz.client_doc)) upd.note = [gz.client_doc, upd.note].filter(Boolean).join('. ');
      const z = { ...(g2.legs.zabor || {}) }, rz = { ...(g2.legs.razvoz || {}) };
      if (gz.dt_load && !z.dt) z.dt = gz.dt_load;
      if (gz.from_addr && !z.from_addr) z.from_addr = gz.from_addr;
      if (gz.dt_unload && !rz.dt) rz.dt = gz.dt_unload;
      if (gz.to_addr && !rz.to_addr) rz.to_addr = gz.to_addr;
      upd.legs = { zabor: z, razvoz: rz };
      await api('gruz_save', upd, 'Данные из заявки клиента подставлены');
      openGruz(gid);
    }, () => openGruz(gid), { zayavka: true });
  };
  // заказчик / перевозчик: выбор из подсказки «Название · ИНН …» → в поле только название, id — в скрытое поле
  form.querySelectorAll('input[name=client], input[name=carrier][data-leg]').forEach(i => i.onchange = () => {
    const fm = S.firmy.find(x => firmLabel(x) === i.value);
    const hid = i.name === 'client' ? form.querySelector('input[name=client_id]')
      : form.querySelector(`input[name=carrier_id][data-leg="${i.dataset.leg}"]`);
    if (fm) { i.value = fm.name; hid.value = fm.id; } else if (!S.firmy.some(x => x.id === num(hid.value) && x.name === i.value)) hid.value = '';
  });
  form.querySelectorAll('[data-firmfiles]').forEach(b => b.onclick = async () => {
    const target = b.dataset.firmfiles;  // 'client' или отрезок
    const gid = (await api('gruz_save', collect())).id;
    openFirma(null, async fm => {
      const g2 = gruzById(gid);
      const upd = target === 'client' ? { ...g2, client: fm.name, client_id: fm.id }
        : { ...g2, legs: { [target]: { ...(g2.legs[target] || {}), carrier: fm.name, carrier_id: fm.id } } };
      await api('gruz_save', upd, 'Реквизиты подставлены в заявку');
      openGruz(gid);
    }, () => openGruz(gid));
  });
  form.querySelectorAll('[data-vodfiles]').forEach(b => b.onclick = async () => {
    const kind = b.dataset.vodfiles;
    const gid = (await api('gruz_save', collect())).id;  // сохранить карточку, чтобы не потерять ввод
    openVoditel(null, async v => {
      const g2 = gruzById(gid);
      const leg = { ...(g2.legs[kind] || {}), driver: vodLabel(v), voditel_id: v.id };
      if (!leg.carrier && v.carrier) leg.carrier = v.carrier;
      await api('gruz_save', { ...g2, legs: { [kind]: leg } }, 'Водитель подставлен в заявку');
      openGruz(gid);
    }, () => openGruz(gid));
  });
  $('#modalBox').querySelectorAll('[data-unlink]').forEach(b => b.onclick = async () => {
    if (!confirm('Отвязать этот платёж от груза? Он вернётся во вкладку «Оплаты».')) return;
    await api('gruz_save', collect());
    await api('oplata_unlink', { id: +b.dataset.unlink }, 'Платёж отвязан');
    openGruz(id);
  });
  $('#modalBox').querySelectorAll('[data-print]').forEach(b => b.onclick = async () => {
    await api('gruz_save', collect());
    const r = await api('print_doc', { kind: b.dataset.print, id });
    toast('Открываю в Word: ' + r.file);
    openGruz(id);
  });
  if ($('#del')) $('#del').onclick = async () => {
    if (!confirm(`Удалить ${g.nomer} совсем? Вернуть будет нельзя.`)) return;
    await api('gruz_delete', { id }, 'Удалено'); closeModal();
  };
  $('#modalBox').querySelectorAll('[data-goto]').forEach(a => a.onclick = e => { e.preventDefault(); openGruz(+a.dataset.goto); });
  if ($('#spGo')) $('#spGo').onclick = async () => {
    const d = { id, kg: num($('#spKg').value), m3: num($('#spM3').value), places: num($('#spPl').value) };
    const res = await api('gruz_split', d, 'Часть отделена');
    openGruz(res.id);
  };
  if ($('#aGo')) $('#aGo').onclick = async () => {
    if (g.status === 'ждёт забора') await api('gruz_accept', { id, sklad_id: num($('#aSk').value), dt: $('#aDt').value }, 'Принят на склад');
    else await api('gruz_deliver', { id, dt: $('#aDt').value }, 'Выдан');
    openGruz(id);
  };
}

// ===== Вкладка «Склад» =====
function viewSklad() {
  if (!sklad(ui.sklad)) ui.sklad = S.sklady[0]?.id;
  const sid = ui.sklad;
  const here = S.gruzy.filter(g => g.sklad_id === sid && (g.status === 'на складе' || g.status === 'прибыл'));
  const waitIn = S.gruzy.filter(g => g.status === 'ждёт забора' && g.sklad_from === sid);
  const coming = S.gruzy.filter(g => g.status === 'в фуре' && gruzReys(g).find(r => r.fura_id === g.fura_id)?.point === sid);
  const sum = (l, k) => l.reduce((s, g) => s + (num(g[k]) || 0), 0);
  const since = g => lastLog(g, 'выгружен из фуры на склад', 'выгружен на перегруз', 'принят на склад')?.dt;

  const table = (list, cols, empty) => list.length ? `<table><thead><tr>${cols.map(c => `<th class="${c[2] || ''}">${c[0]}</th>`).join('')}</tr></thead>
    <tbody>${list.map(g => `<tr class="click" data-id="${g.id}">${cols.map(c => `<td class="${c[2] || ''}">${c[1](g)}</td>`).join('')}</tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="${cols.length}">Итого: ${list.length} шт · ${n1(sum(list, 'kg'), 0)} кг · ${n1(sum(list, 'm3'))} м³ · ${n1(sum(list, 'places'), 0)} мест</td></tr></tfoot></table>`
    : `<div class="empty">${empty}</div>`;
  const base = [['№', g => esc(g.nomer)], ['Клиент', g => esc(g.client)], ['Груз', g => esc(g.cargo)],
    ['кг', g => n1(g.kg, 0), 'num'], ['м³', g => n1(g.m3), 'num'], ['мест', g => n1(g.places, 0), 'num']];

  $('#view').innerHTML = `
    <div class="chips">${S.sklady.map(s => {
      const c = S.gruzy.filter(g => g.sklad_id === s.id && ['на складе', 'прибыл'].includes(g.status));
      return `<button class="chip${s.id === sid ? ' on' : ''}" data-sk="${s.id}"><b>${esc(s.name)}</b>
        <span class="muted">${c.length} гр · ${n1(sum(c, 'm3'), 1)} м³</span></button>`;
    }).join('')}</div>
    <h2>Склад ${esc(skName(sid))} — лежит сейчас</h2>
    ${table(here, [...base,
      ['Статус', g => badge(g.status)],
      ['Куда дальше', g => g.status === 'прибыл' ? 'развоз: ' + esc(g.legs.razvoz?.to_addr || g.to_addr || '?')
        : 'фурой на ' + esc(skName(g.sklad_to) || '?') + (gruzReys(g).length ? ' <span class="badge st-fura">перегруз</span>' : '')],
      ['Лежит, дней', g => { const d = days(since(g)); return d == null ? '' : `<span class="${d > 7 ? 'minus' : ''}">${d}</span>`; }, 'num']],
      'На складе пусто.')}
    <h3>Едут сюда в фуре</h3>
    ${table(coming, [...base, ['Фура', g => esc(fura(g.fura_id)?.nomer_ts || '')], ['Статус фуры', g => esc(fura(g.fura_id)?.status || '')]], 'Никто не едет.')}
    <h3>Ждут забора (склад отправки — ${esc(skName(sid))})</h3>
    ${table(waitIn, [...base, ['Откуда', g => esc(g.legs.zabor?.from_addr || g.from_addr)], ['Перевозчик', g => esc(g.legs.zabor?.carrier || '')],
      ['', g => `<button class="btn small" data-accept="${g.id}">Принять</button>`]], 'Никого не ждём.')}`;

  $('#view').querySelectorAll('[data-sk]').forEach(b => b.onclick = () => { ui.sklad = +b.dataset.sk; saveUi(); viewSklad(); });
  $('#view').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = e => {
    if (e.target.dataset.accept) return;
    openGruz(+tr.dataset.id);
  });
  $('#view').querySelectorAll('[data-accept]').forEach(b => b.onclick = () =>
    api('gruz_accept', { id: +b.dataset.accept, sklad_id: sid }, 'Принят на склад'));
}

// ===== Вкладка «Фуры» =====
function meter(label, val, cap, unit) {
  const pct = cap ? val / cap * 100 : 0;
  return `<div class="meter"><div class="lab"><span>${label}: ${n1(val, 1)} из ${n1(cap, 0)} ${unit}</span>
    <span>${cap ? (pct > 100 ? 'перегруз ' : 'свободно ') + n1(Math.abs(cap - val), 1) + ' ' + unit : ''}</span></div>
    <div class="track"><div class="fill${pct > 100 ? ' over' : ''}" style="width:${Math.min(pct, 100)}%"></div></div></div>`;
}

function routeText(f) { return [skName(f.sklad_from) || '?', ...f.route.map(skName)].join(' → '); }

function viewFury() {
  $('#view').innerHTML = `
    <div class="bar"><h2 class="grow">Фуры</h2><button class="btn" id="add">+ Новая фура</button></div>
    ${S.furas.length ? `<div class="cards">${S.furas.map(f => {
      const c = furaCalc(f);
      return `<div class="card" data-id="${f.id}">
        <div class="t"><span>${esc(f.nomer_ts || 'без номера')}</span><span class="badge ${f.status === 'собирается' ? 'st-zhdet' : f.status === 'в пути' ? 'st-fura' : 'st-pribyl'}">${f.status}</span></div>
        <div class="muted">${esc(routeText(f))}</div>
        <div class="muted">${esc(f.carrier)} ${f.dt_out ? '· выезд ' + dmy(f.dt_out) : ''}</div>
        ${meter('Объём', c.m3, f.cap_m3, 'м³')}${meter('Вес', c.kg / 1000, f.cap_t, 'т')}
        <div>${c.gs.length} грузов · клиенты ${rub(c.income)} · остаток <b class="${c.profit < 0 ? 'minus' : ''}">${rub(c.profit)}</b></div>
      </div>`;
    }).join('')}</div>` : '<div class="empty">Фур пока нет. Нажмите «+ Новая фура».</div>'}`;
  $('#add').onclick = () => openFuraForm(null);
  $('#view').querySelectorAll('.card').forEach(c => c.onclick = () => openFura(+c.dataset.id));
}

function openFuraForm(id) {
  const f = id ? fura(id) : { cap_m3: 82, cap_t: 20, route: [], sklad_from: S.sklady[0]?.id };
  const v = (k, lab, type = 'text') => `<label>${lab}<input name="${k}" type="${type}" ${type === 'number' ? 'step="any"' : ''} value="${esc(f[k] ?? '')}"></label>`;
  let route = [...f.route];
  openModal(`
    <div class="head"><h2>${id ? 'Фура ' + esc(f.nomer_ts) : 'Новая фура'}</h2><button class="x" data-close>×</button></div>
    <form id="ff"><div class="grid">
      ${v('nomer_ts', 'Номер машины')}${v('carrier', 'Перевозчик')}
      <label>Водитель — из справочника или текстом
        <span style="display:flex;gap:6px"><input name="driver" list="vodList" value="${esc(f.driver ?? '')}" style="flex:1">
        <button type="button" class="btn small light" id="vodFiles">из файлов</button></span>
        <input type="hidden" name="voditel_id" value="${esc(f.voditel_id ?? '')}"></label>
      ${vodDatalist()}${v('zayavka', '№ заявки перевозчику')}
      <label>Объём кузова<select name="cap_m3">${opts([[82, '82 м³'], [110, '110 м³']], f.cap_m3, null)}</select></label>
      ${v('cap_t', 'Грузоподъёмность, т', 'number')}${v('rate', 'Ставка фуры, ₽', 'number')}
      <label>Форма оплаты фуры<select name="rate_form">${formOpts(f.rate_form)}</select></label>
      ${v('sklad_load', 'Склад погрузки, ₽', 'number')}<label>Форма оплаты склада погр.<select name="sklad_load_form">${formOpts(f.sklad_load_form)}</select></label>
      ${v('sklad_unload', 'Склад приёмки, ₽', 'number')}<label>Форма оплаты склада приёмки<select name="sklad_unload_form">${formOpts(f.sklad_unload_form)}</select></label>
      ${v('other', 'Прочие общие (кран и т.п.), ₽', 'number')}<label>Форма оплаты прочих<select name="other_form">${formOpts(f.other_form)}</select></label>
      <label>Склад погрузки<select name="sklad_from" ${id && f.status !== 'собирается' ? 'disabled' : ''}>${skladOpts(f.sklad_from, null)}</select></label>
      <label class="full">Выгрузка по порядку
        <div class="bar" style="margin:0"><span id="rt"></span>
          <select id="rtAdd">${skladOpts(null, '+ добавить склад')}</select></div></label>
      <label class="full">Примечание<textarea name="note" rows="2">${esc(f.note || '')}</textarea></label>
    </div>
    <div class="foot"><div>${id && f.status === 'собирается' ? '<button type="button" class="btn red" id="del">Удалить фуру</button>' : ''}</div>
      <div><button type="button" class="btn light" data-close>Закрыть</button> <button class="btn">Сохранить</button></div></div></form>`);
  const drawRoute = () => {
    $('#rt').innerHTML = route.length ? route.map((s, i) =>
      `<span class="badge st-sklad">${i + 1}. ${esc(skName(s))} <a href="#" data-rm="${i}" title="убрать">✕</a></span>`).join(' ') : '<span class="muted">не задана</span>';
    $('#rt').querySelectorAll('[data-rm]').forEach(a => a.onclick = e => { e.preventDefault(); route.splice(+a.dataset.rm, 1); drawRoute(); });
  };
  drawRoute();
  $('#rtAdd').onchange = e => { if (e.target.value) route.push(+e.target.value); e.target.value = ''; drawRoute(); };
  const collectF = () => {
    const d = { id, route };
    $('#ff').querySelectorAll('[name]').forEach(i => d[i.name] = i.value);
    for (const k of ['cap_m3', 'cap_t', 'rate', 'sklad_from', 'sklad_load', 'sklad_unload', 'other', 'voditel_id']) d[k] = num(d[k]);
    if (id && f.status !== 'собирается') d.sklad_from = f.sklad_from;
    d.dt_out = f.dt_out || '';
    return d;
  };
  const ff = $('#ff');
  const setVod = v => {  // водитель из справочника: id, перевозчик и номер машины — если пусто
    ff.querySelector('[name=voditel_id]').value = v ? v.id : '';
    if (v && v.carrier && !ff.querySelector('[name=carrier]').value) ff.querySelector('[name=carrier]').value = v.carrier;
    if (v && v.auto_plate && !ff.querySelector('[name=nomer_ts]').value) ff.querySelector('[name=nomer_ts]').value = v.auto_plate;
  };
  ff.querySelector('[name=driver]').onchange = e => setVod(S.voditeli.find(x => vodLabel(x) === e.target.value));
  $('#vodFiles').onclick = async () => {
    const fid = (await api('fura_save', collectF())).id;
    openVoditel(null, async v => {
      const f2 = fura(fid);
      await api('fura_save', { ...f2, driver: vodLabel(v), voditel_id: v.id, carrier: f2.carrier || v.carrier,
        nomer_ts: f2.nomer_ts || v.auto_plate }, 'Водитель подставлен в фуру');
      openFura(fid);
    }, () => openFuraForm(fid));
  };
  ff.onsubmit = async e => {
    e.preventDefault();
    const res = await api('fura_save', collectF(), 'Сохранено');
    openFura(res.id);
  };
  if ($('#del')) $('#del').onclick = async () => {
    if (!confirm('Удалить фуру?')) return;
    await api('fura_delete', { id }, 'Удалено'); closeModal();
  };
}

function openFura(id) {
  const f = fura(id); if (!f) return closeModal();
  const c = furaCalc(f);
  const canLoad = f.status === 'собирается';
  const onSklad = S.gruzy.filter(g => g.status === 'на складе' && g.sklad_id === f.sklad_from
    && !gruzReys(g).some(r => r.fura_id === f.id));
  const riding = c.rs.filter(r => r.g.status === 'в фуре' && r.g.fura_id === f.id);   // ещё в этой фуре
  const stops = f.route.map(sid => ({ sid, n: riding.filter(r => r.point === sid).length }));
  const noPoint = riding.filter(r => !f.route.includes(r.point));

  openModal(`
    <div class="head"><h2>Фура ${esc(f.nomer_ts || 'без номера')} · ${esc(routeText(f))}</h2><button class="x" data-close>×</button></div>
    <p class="muted">${esc(f.carrier)} ${esc(f.driver)} · заявка ${esc(f.zayavka || '—')} · ставка ${rub(f.rate)} · статус <b>${f.status}</b>
      ${f.dt_out ? '· выезд ' + dmy(f.dt_out) : ''} · <a href="#" id="edit">изменить</a>
      · <button class="btn small light" id="printF">Печать заявки на фуру (Word)</button></p>
    ${meter('Объём', c.m3, f.cap_m3, 'м³')}${meter('Вес', c.kg / 1000, f.cap_t, 'т')}

    <div class="actions">
      ${canLoad ? `<input id="dt" type="date" value="${S.today}"><button class="btn" id="send" ${c.gs.length ? '' : 'disabled'}>Отправить фуру</button>` : ''}
      ${f.status === 'в пути' ? `<input id="dt" type="date" value="${S.today}"> ${stops.map(s =>
        `<button class="btn${s.n ? '' : ' light'}" data-unload="${s.sid}">Выгрузить в ${esc(skName(s.sid))} (${s.n})</button>`).join('')}` : ''}
      ${f.status === 'прибыла' ? '<b>Фура прибыла, всё выгружено.</b>' : ''}
      ${noPoint.length ? `<span class="minus">У ${noPoint.length} гр. точка выгрузки не из маршрута фуры — выберите в таблице.</span>` : ''}
    </div>

    <h3>В фуре: ${c.gs.length} грузов · ${n1(c.kg, 0)} кг · ${n1(c.m3)} м³ · 1 кг = ${n1(c.perKg)} ₽</h3>
    ${c.gs.length ? `<table><thead><tr><th>№</th><th>Клиент</th><th>Груз</th><th class="num">кг</th><th class="num">м³</th>
      <th>Выгрузка</th><th>Статус</th><th class="num">Клиент</th><th class="num">Забор+развоз</th><th class="num">Доля фуры</th><th class="num">Остаток</th><th></th></tr></thead>
      <tbody>${c.rs.map(({ g, point }) => {
        const sh = c.share(g), pr = gruzProfit(g).profit, multi = gruzReys(g).length > 1;
        const pointOk = f.route.includes(point), here = g.status === 'в фуре' && g.fura_id === f.id;
        const transit = point && g.sklad_to && point !== g.sklad_to;
        return `<tr data-id="${g.id}"><td><a href="#" data-open="${g.id}">${esc(g.nomer)}</a></td><td>${esc(g.client)}</td><td>${esc(g.cargo)}</td>
          <td class="num${g.kg ? '' : ' gap'}">${n1(g.kg, 0)}</td><td class="num">${n1(g.m3)}</td>
          <td class="${pointOk ? '' : 'gap'}">${here
            ? `<select data-point="${g.id}">${opts(f.route.map(s => [s, skName(s) + (s === g.sklad_to ? '' : ' (перегруз)')]), pointOk ? point : '', 'не указано')}</select>`
            : esc(skName(point))}${transit ? `<div class="hint">дальше на ${esc(skName(g.sklad_to))}</div>` : ''}</td>
          <td>${here ? badge(g.status) : '<span class="badge st-dost">выгружен</span>'}</td><td class="num">${rub(g.rate_client)}</td><td class="num">${rub(legsSum(g))}</td>
          <td class="num">${rub(sh)}</td><td class="num${pr < 0 ? ' minus' : ''}">${rub(pr)}${multi ? '*' : ''}</td>
          <td>${canLoad ? `<button class="btn small light" data-rm="${g.id}">убрать</button>` : ''}</td></tr>`;
      }).join('')}</tbody>
      <tfoot><tr><td colspan="7">Итого (фура ${rub(f.rate)})</td><td class="num">${rub(c.income)}</td><td class="num">${rub(c.legs)}</td>
        <td class="num">${rub(c.gs.reduce((s, g) => s + c.share(g), 0))}</td><td class="num">${rub(c.profit)}</td><td></td></tr></tfoot></table>
      <p class="hint">Доля фуры = вес груза × стоимость 1 кг; 1 кг = (фура + склады + прочие общие) / вес фуры. Груз без веса (жёлтый) доли не получает.
        Остаток — после налогов (НДС/УСН, налог на прибыль у ОСНО), разбор — в карточке груза.
        ${c.multi ? '<br>* Груз едет несколькими фурами (перегруз) — остаток по нему общий: минус доли всех его фур.' : ''}</p>`
      : '<div class="empty">Фура пустая.</div>'}

    ${canLoad ? `<h3>Можно погрузить со склада ${esc(skName(f.sklad_from))}: ${onSklad.length}</h3>
      ${onSklad.length ? `<table><thead><tr><th></th><th>№</th><th>Клиент</th><th>Груз</th><th class="num">кг</th><th class="num">м³</th><th>Склад назначения</th></tr></thead>
        <tbody>${onSklad.map(g => `<tr><td><input type="checkbox" data-pick="${g.id}"></td><td>${esc(g.nomer)}</td><td>${esc(g.client)}</td>
          <td>${esc(g.cargo)}</td><td class="num">${n1(g.kg, 0)}</td><td class="num">${n1(g.m3)}</td>
          <td class="${f.route.includes(g.sklad_to) ? '' : 'gap'}">${esc(skName(g.sklad_to) || 'не указан')}</td></tr>`).join('')}</tbody></table>
        <div class="bar" style="margin-top:8px"><span id="pickInfo" class="muted">Отметьте грузы галочками</span><span class="grow"></span>
          <button class="btn" id="load" disabled>Погрузить отмеченные</button></div>`
        : '<div class="empty">На складе погрузки нет свободных грузов.</div>'}` : ''}
    <div class="foot"><span></span><button class="btn light" data-close>Закрыть</button></div>`);

  $('#edit').onclick = e => { e.preventDefault(); openFuraForm(id); };
  $('#printF').onclick = async () => {
    const r = await api('print_doc', { kind: 'fura', id });
    toast('Открываю в Word: ' + r.file);
  };
  const box = $('#modalBox');
  box.querySelectorAll('[data-open]').forEach(a => a.onclick = e => { e.preventDefault(); openGruz(+a.dataset.open); });
  box.querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => { await api('fura_remove', { fura_id: id, gruz_id: +b.dataset.rm }, 'Убран на склад'); openFura(id); });
  box.querySelectorAll('[data-point]').forEach(s => s.onchange = async () => {
    await api('reys_point', { gruz_id: +s.dataset.point, fura_id: id, point: num(s.value) }, 'Точка выгрузки сохранена'); openFura(id);
  });
  if ($('#send')) $('#send').onclick = async () => {
    if (noPoint.length && !confirm(`У ${noPoint.length} грузов не указано, где выгружать. Всё равно отправить?`)) return;
    await api('fura_send', { id, dt: $('#dt').value }, 'Фура отправлена'); openFura(id);
  };
  box.querySelectorAll('[data-unload]').forEach(b => b.onclick = async () => {
    const r = await api('fura_unload', { fura_id: id, sklad_id: +b.dataset.unload, dt: $('#dt').value });
    toast(`Выгружено ${r.unloaded}, осталось в фуре ${r.left}`); openFura(id);
  });
  const picks = [...box.querySelectorAll('[data-pick]')];
  const upd = () => {
    const sel = onSklad.filter(g => picks.find(p => p.checked && +p.dataset.pick === g.id));
    const kg = sel.reduce((s, g) => s + (num(g.kg) || 0), 0), m3 = sel.reduce((s, g) => s + (num(g.m3) || 0), 0);
    $('#pickInfo').innerHTML = sel.length ? `Отмечено ${sel.length}: ${n1(kg, 0)} кг, ${n1(m3)} м³ → в фуре станет
      <b class="${c.m3 + m3 > f.cap_m3 ? 'minus' : ''}">${n1(c.m3 + m3)} из ${f.cap_m3} м³</b>,
      <b class="${(c.kg + kg) / 1000 > f.cap_t ? 'minus' : ''}">${n1((c.kg + kg) / 1000, 1)} из ${f.cap_t} т</b>` : 'Отметьте грузы галочками';
    $('#load').disabled = !sel.length;
  };
  picks.forEach(p => p.onchange = upd);
  if ($('#load')) $('#load').onclick = async () => {
    await api('fura_add', { fura_id: id, gruz_ids: picks.filter(p => p.checked).map(p => +p.dataset.pick) }, 'Погружено'); openFura(id);
  };
}

// ===== Выгрузка в Excel (по кнопке) =====
// строки считаем здесь тем же calc(), что и вкладка «Зарплата» — цифры в файле совпадают с приложением
const gruzDate = g => g.legs.zabor?.dt || g.created || '';

function exportRows(list) {
  return list.map(g => {
    const c = calc(g), z = g.legs.zabor || {}, r = g.legs.razvoz || {}, fm = g.client_id && firmById(g.client_id);
    return {
      nomer: g.nomer, dt: gruzDate(g), manager: g.manager || '', client: g.client || '', inn: fm?.inn || '',
      from: g.from_addr || '', to: g.to_addr || '', sklady: `${skName(g.sklad_from) || '?'} → ${skName(g.sklad_to) || '?'}`,
      cargo: g.cargo || '', kg: num(g.kg), m3: num(g.m3), places: num(g.places), status: g.status,
      fury: gruzReys(g).map(rr => fura(rr.fura_id)?.nomer_ts).filter(Boolean).join(', '),
      rate: c.rev, pay_form: g.pay_form || '', company: g.company || '',
      z_carrier: z.carrier || '', z_rate: num(z.rate), r_carrier: r.carrier || '', r_rate: num(r.rate), other: num(g.other_cost),
      share: c.share, nalog: c.nalog, vat: c.ownVat + c.shareVat, np: c.np, profit: c.profit, zp: c.zp,
      paid: c.paid, paid_date: g.paid_date || '', pay_status: c.payStatus, debt: c.debt, zp_nach: c.zpNach, zp_wait: c.zpWait,
    };
  });
}

function openExport(manager) {
  const NOMAN = '(без менеджера)';
  const t = S.today, first = t.slice(0, 8) + '01';
  const lastDay = new Date(+t.slice(0, 4), +t.slice(5, 7), 0).getDate();
  openModal(`
    <div class="head"><h2>Заявки в Excel</h2><button class="x" data-close>×</button></div>
    <div class="grid" style="max-width:640px">
      <label>Менеджер<select id="xM">${opts([...managerNames(), NOMAN].map(m => [m, m]), manager || '', 'все менеджеры')}</select></label>
      <label>С (дата погрузки)<input id="xF" type="date" value="${first}"></label>
      <label>По<input id="xT" type="date" value="${t.slice(0, 8)}${String(lastDay).padStart(2, '0')}"></label>
    </div>
    <p class="hint">Период — по дате погрузки (забор); если её нет — по дате создания заявки. Пустые даты — весь период.</p>
    <p id="xInfo"></p>
    <div class="foot"><span></span><div><button class="btn light" data-close>Закрыть</button> <button class="btn" id="xGo">Сформировать Excel</button></div></div>`);
  const pick = () => {
    const m = $('#xM').value, f = $('#xF').value, to = $('#xT').value;
    return S.gruzy.filter(g => (!m || (m === NOMAN ? !g.manager : g.manager === m)) &&
      (!f || gruzDate(g) >= f) && (!to || gruzDate(g) <= to)).sort((a, b) => gruzDate(a).localeCompare(gruzDate(b)));
  };
  const info = () => { const l = pick(); $('#xInfo').innerHTML = `Попадёт заявок: <b>${l.length}</b> · остаток ${rub(l.reduce((s, g) => s + calc(g).profit, 0))}`; };
  ['#xM', '#xF', '#xT'].forEach(s => $(s).onchange = info);
  info();
  $('#xGo').onclick = async () => {
    const list = pick();
    if (!list.length) return toast('За этот период заявок нет', true);
    const r = await api('export_excel', { rows: exportRows(list), manager: $('#xM').value, date_from: $('#xF').value, date_to: $('#xT').value });
    toast('Открываю Excel: ' + r.file);
  };
}

// ===== Вкладка «Зарплата» =====
// Начислено — по месяцу даты полной оплаты клиента; «ждёт оплаты» — зп по заявкам, которые клиент ещё не оплатил полностью.
function viewZp() {
  const year = ui.zpYear || +S.today.slice(0, 4);
  const NOMAN = '(без менеджера)';
  const rows = S.gruzy.map(g => ({ g, c: calc(g), m: g.manager || NOMAN }));
  const years = [...new Set([year, ...rows.filter(r => r.g.paid_date).map(r => +r.g.paid_date.slice(0, 4))])].sort();
  const people = [...new Set([...managerNames(), ...rows.map(r => r.m)])].filter(m => rows.some(r => r.m === m) || managerNames().includes(m));
  const MON = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  const nach = (m, mon) => rows.filter(r => r.m === m && r.c.zpNach && r.g.paid_date?.startsWith(`${year}-${String(mon + 1).padStart(2, '0')}`))
    .reduce((s, r) => s + r.c.zpNach, 0);
  const sum = (list, k) => list.reduce((s, r) => s + r.c[k], 0);
  const sel = ui.zpManager && people.includes(ui.zpManager) ? ui.zpManager : null;
  const mine = sel ? rows.filter(r => r.m === sel) : [];
  const bad = rows.filter(r => r.c.problems.length);

  $('#view').innerHTML = `
    <div class="bar"><h2 class="grow">Зарплата менеджеров — ${ZP_PCT * 100}% от остатка прибыли</h2>
      <select id="yr">${opts(years.map(y => [y, y + ' год']), year, null)}</select>
      <button class="btn light" id="xls">В Excel</button></div>
    <div style="overflow-x:auto"><table><thead><tr><th>Менеджер</th>${MON.map(m => `<th class="num">${m}</th>`).join('')}
      <th class="num">Начислено за год</th><th class="num">Ждёт оплаты</th><th class="num">Остаток прибыли</th><th class="num">Заявок</th></tr></thead>
    <tbody>${people.map(m => {
      const my = rows.filter(r => r.m === m);
      const months = MON.map((_, i) => nach(m, i));
      return `<tr class="click${m === sel ? ' on' : ''}" data-m="${esc(m)}"><td><b>${esc(m)}</b></td>
        ${months.map(v => `<td class="num">${v ? rub(v) : ''}</td>`).join('')}
        <td class="num"><b>${rub(months.reduce((a, b) => a + b, 0))}</b></td><td class="num">${rub(sum(my, 'zpWait'))}</td>
        <td class="num">${rub(sum(my, 'profit'))}</td><td class="num">${my.length}</td></tr>`;
    }).join('')}</tbody></table></div>
    <p class="hint">Щёлкни по менеджеру — ниже его заявки. Зп начисляется, когда «Клиент оплатил» ≥ ставки клиента, в месяц «Даты полной оплаты».
      Остаток в минусе — зп 0.</p>
    ${sel ? `<h3>${esc(sel)}: заявки</h3>
      <table><thead><tr><th>№</th><th>Клиент</th><th class="num">Выручка</th><th class="num">Остаток прибыли</th><th class="num">Зп</th>
        <th>Оплата клиента</th><th>Дата оплаты</th><th>Мешает расчёту</th></tr></thead>
      <tbody>${mine.map(({ g, c }) => `<tr class="click" data-id="${g.id}"><td>${esc(g.nomer)}</td><td>${esc(g.client)}</td>
        <td class="num">${rub(c.rev)}</td><td class="num${c.profit < 0 ? ' minus' : ''}">${rub(c.profit)}</td>
        <td class="num">${c.zpNach ? '<b>' + rub(c.zpNach) + '</b>' : c.zp ? `<span class="muted">${rub(c.zp)} ждёт</span>` : ''}</td>
        <td>${esc(c.payStatus)}${c.payStatus === 'частично' ? ', долг ' + rub(c.debt) : ''}</td><td>${dmy(g.paid_date)}</td>
        <td class="${c.problems.length ? 'gap' : ''}">${c.problems.map(esc).join('; ')}</td></tr>`).join('')}</tbody></table>` : ''}
    ${bad.length ? `<h3>Заявки, где расчёту что-то мешает: ${bad.length}</h3>
      <p class="hint">${bad.slice(0, 30).map(({ g, c }) => `<a href="#" data-id="${g.id}">${esc(g.nomer)}</a> — ${c.problems.map(esc).join(', ')}`).join('<br>')}
      ${bad.length > 30 ? '<br>…' : ''}</p>` : ''}`;

  $('#yr').onchange = e => { ui.zpYear = +e.target.value; saveUi(); viewZp(); };
  $('#xls').onclick = () => openExport(sel && sel !== NOMAN ? sel : '');
  $('#view').querySelectorAll('tr[data-m]').forEach(tr => tr.onclick = () => { ui.zpManager = tr.dataset.m; saveUi(); viewZp(); });
  $('#view').querySelectorAll('[data-id]').forEach(el => el.onclick = e => { e.preventDefault(); openGruz(+el.dataset.id); });
}

// ===== Вкладка «Оплаты»: банковская выписка → оплаты грузов =====
// Сервер хранит поступления (повтор по отпечатку не добавляется) и предлагает груз; человек подтверждает.
async function post(action, data) {  // как api(), но без перезагрузки состояния
  const r = await fetch('/api/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data || {}) });
  if (r.status === 401) { location.href = '/login'; throw new Error('нужно войти'); }
  const res = await r.json();
  if (!r.ok) { toast(res.error || 'Ошибка', true); throw new Error(res.error); }
  return res;
}
let oplLast = '';   // итог последней загрузки — показываем над списками

async function viewOplaty() {
  $('#view').innerHTML = '<p class="muted">Загружаю платежи…</p>';
  const L = await post('oplaty_list', { all: ui.oplAll });
  if (tab !== 'opl') return;
  const gLabel = g => `${g.nomer} · ${g.client || 'без клиента'} · ${g.company} · долг ${rub(calc(g).debt)}`;
  const openG = S.gruzy.filter(g => num(g.rate_client) && calc(g).debt > 0.5);
  const sure = L.items.filter(i => i.kind === 'sure'), check = L.items.filter(i => i.kind === 'check'), none = L.items.filter(i => i.kind === 'none');
  const payCells = p => `<td>${dmy(p.dt)}</td><td>${esc(p.company)}<br><span class="hint">п/п ${esc(p.num)}</span></td>
    <td>${esc(p.payer)}<br><span class="hint">ИНН ${esc(p.inn)}</span></td><td class="num"><b>${rub(p.sum)}</b>${p.rest < p.sum - 0.5 ? `<br><span class="hint">свободно ${rub(p.rest)}</span>` : ''}</td>
    <td class="purp">${esc(p.purp)}</td>`;
  const gSelect = (p, sel) => {
    // все неоплаченные грузы: клиент мог заплатить не на ту фирму, что указана в грузе — своя фирма первой
    const rest = openG.filter(g => !p.cands.includes(g.id));
    const list = [...p.cands.map(gruzById).filter(Boolean), ...rest.filter(g => g.company === p.company), ...rest.filter(g => g.company !== p.company)];
    return `<select data-g="${p.id}" style="max-width:340px">${opts(list.map(g => [g.id, gLabel(g)]), sel, '— выбери груз —')}</select>`;
  };
  const row = p => `<tr>${payCells(p)}<td>${gSelect(p, p.links[0]?.gruz_id)}<div class="hint">${esc(p.why)}</div></td>
    <td><input data-s="${p.id}" type="number" step="any" value="${p.links[0]?.sum ?? p.rest}" style="width:110px"></td>
    <td><button class="btn small" data-link="${p.id}">Привязать</button> <button class="btn small light" data-ign="${p.id}" title="Платёж не за груз — больше не показывать">Не к грузам</button></td></tr>`;
  const head = '<thead><tr><th>Дата</th><th>Наш счёт</th><th>Плательщик</th><th class="num">Сумма</th><th>Назначение</th>';

  $('#view').innerHTML = `
    <div class="bar"><h2 class="grow">Оплаты клиентов из банковской выписки</h2>
      <label class="hint"><input type="checkbox" id="oAll" ${ui.oplAll ? 'checked' : ''}> показать и старые платежи</label>
      <button class="btn" id="oLoad">Загрузить выписку</button><input id="oFile" type="file" multiple accept=".txt" hidden></div>
    <div id="drop" class="drop">Перетащите сюда файл выписки «для 1С» (.txt) — Точка или Альфа, можно несколько сразу.
      Та же выписка второй раз оплаты не задвоит.</div>
    ${oplLast ? `<div class="actions">${oplLast}</div>` : ''}
    <p class="hint">Всего загружено платежей: ${L.total}. ${L.old ? `Ещё ${L.old} — раньше ${dmy(L.since)} (до первого груза), скрыты.` : ''}</p>

    <h3>Уверенно — ${sure.length}</h3>
    ${sure.length ? `<table>${head}<th>Груз</th><th class="num">Сумма к грузу</th><th><input type="checkbox" id="sAll" checked title="все"></th></tr></thead>
      <tbody>${sure.map(p => p.links.map((l, k) => { const g = gruzById(l.gruz_id); return `<tr>${k ? '<td colspan="5" class="hint">тот же платёж</td>' : payCells(p)}
        <td><a href="#" data-id="${l.gruz_id}">${esc(g?.nomer)}</a> · ${esc(g?.client)}<div class="hint">${esc(p.why)}</div></td>
        <td class="num">${rub(l.sum)}</td><td><input type="checkbox" data-sure="${p.id}:${l.gruz_id}:${l.sum}" checked></td></tr>`; }).join('')).join('')}</tbody></table>
      <div class="foot"><span></span><button class="btn" id="sGo">Провести отмеченные</button></div>`
      : '<div class="empty">Уверенных совпадений нет.</div>'}

    <h3>Проверь — ${check.length}</h3>
    <p class="hint">Программа нашла похожий груз, но не уверена (частичная оплата, несколько вариантов, совпала только сумма). Выбери груз и сумму.</p>
    ${check.length ? `<table>${head}<th>Груз</th><th>Сумма к грузу</th><th></th></tr></thead><tbody>${check.map(row).join('')}</tbody></table>` : '<div class="empty">Нечего проверять.</div>'}

    <h3>Не нашли груз — ${none.length}</h3>
    ${none.length ? `<table>${head}<th>Груз</th><th>Сумма к грузу</th><th></th></tr></thead><tbody>${none.map(row).join('')}</tbody></table>` : '<div class="empty">Пусто.</div>'}

    ${L.hidden.length ? `<details><summary class="hint">Скрытые («не к грузам», проценты банка): ${L.hidden.length}</summary>
      <table>${head}<th></th></tr></thead><tbody>${L.hidden.map(p => `<tr>${payCells(p)}<td><button class="btn small light" data-unign="${p.id}">Вернуть</button></td></tr>`).join('')}</tbody></table></details>` : ''}`;

  const doLink = async links => {
    // «Клиент оплатил» уже введено руками и платежей ещё нет — спросить: прибавить или заменить
    const manual = {};
    for (const gid of new Set(links.map(l => l.gruz_id))) {
      const g = gruzById(gid);
      if (num(g.paid_sum) && !S.oplaty.some(o => o.gruz_id === gid))
        manual[gid] = confirm(`В грузе ${g.nomer} уже введено руками «Клиент оплатил» ${rub(g.paid_sum)}.\n\nОК — прибавить платёж к этой сумме (часть была наличными).\nОтмена — заменить: считать только платежи из выписки.`) ? 'add' : 'replace';
    }
    const r = await api('oplata_link', { links, manual });
    toast(`Привязано. Оплата обновлена в грузах: ${r.gruzy}`);
  };
  $('#oAll').onchange = e => { ui.oplAll = e.target.checked; saveUi(); viewOplaty(); };
  const upload = async files => {
    files = [...files].filter(f => f.size); if (!files.length) return;
    const payload = await Promise.all(files.map(f => new Promise(res => {
      const r = new FileReader(); r.onload = () => res({ name: f.name, data: r.result }); r.readAsDataURL(f);
    })));
    const r = await post('vypiska_load', { files: payload });
    oplLast = r.files.map(x => x.error ? `<b>${esc(x.file)}</b>: ${esc(x.error)}` :
      `<b>${esc(x.file)}</b> (${esc(x.company)}, счёт …${esc(x.acc)}): поступлений ${x.total}, <b>новых ${x.new}</b>, уже были ${x.old}` +
      (x.own ? `, переводов между своими пропущено ${x.own}` : '')).join('<br>');
    await load();
  };
  $('#oLoad').onclick = () => $('#oFile').click();
  $('#oFile').onchange = e => upload(e.target.files);
  const drop = $('#drop');
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); upload(e.dataTransfer.files); };
  if ($('#sAll')) $('#sAll').onchange = e => $('#view').querySelectorAll('[data-sure]').forEach(c => c.checked = e.target.checked);
  if ($('#sGo')) $('#sGo').onclick = () => {
    const links = [...$('#view').querySelectorAll('[data-sure]:checked')].map(c => {
      const [platezh_id, gruz_id, sum] = c.dataset.sure.split(':'); return { platezh_id: +platezh_id, gruz_id: +gruz_id, sum: +sum };
    });
    if (!links.length) return toast('Ничего не отмечено', true);
    doLink(links);
  };
  $('#view').querySelectorAll('[data-link]').forEach(b => b.onclick = () => {
    const pid = b.dataset.link, gid = num($(`[data-g="${pid}"]`).value), sum = num($(`[data-s="${pid}"]`).value);
    if (!gid) return toast('Выбери груз', true);
    if (!sum) return toast('Укажи сумму', true);
    doLink([{ platezh_id: +pid, gruz_id: gid, sum }]);
  });
  $('#view').querySelectorAll('[data-ign]').forEach(b => b.onclick = () => api('platezh_ignore', { id: +b.dataset.ign, ignored: true }, 'Скрыто'));
  $('#view').querySelectorAll('[data-unign]').forEach(b => b.onclick = () => api('platezh_ignore', { id: +b.dataset.unign, ignored: false }, 'Возвращено'));
  $('#view').querySelectorAll('a[data-id]').forEach(a => a.onclick = e => { e.preventDefault(); openGruz(+a.dataset.id); });
}

// ===== Водители: справочник и «Водитель из файлов» =====
const vodLabel = v => v ? `${v.fio || 'без ФИО'}${v.auto_plate ? ' · ' + v.auto_plate : ''}` : '';
const vodById = id => S.voditeli.find(v => v.id === id);
const vodDatalist = () => `<datalist id="vodList">${S.voditeli.map(v => `<option value="${esc(vodLabel(v))}">`).join('')}</datalist>`;
const VOD_GROUPS = [
  ['Водитель', [['fio', 'ФИО', 'wide'], ['phone', 'Телефон'], ['birth_date', 'Дата рождения']]],
  ['Паспорт', [['passport', 'Серия и номер'], ['passport_date', 'Дата выдачи'], ['passport_code', 'Код подразделения'],
    ['passport_issued_by', 'Кем выдан', 'full']]],
  ['Водительское удостоверение', [['vu', 'Номер'], ['vu_date', 'Дата выдачи'], ['vu_until', 'Действует до'], ['vu_cats', 'Категории']]],
  ['Тягач / автомобиль', [['auto_brand', 'Марка, модель'], ['auto_plate', 'Госномер'], ['auto_sts', 'СТС']]],
  ['Полуприцеп', [['trailer_brand', 'Марка'], ['trailer_plate', 'Госномер'], ['trailer_sts', 'СТС']]],
  ['Перевозчик (чья машина)', [['carrier', 'Перевозчик', 'wide'], ['carrier_inn', 'ИНН']]],
];

function viewVoditeli() {
  const q = (ui.vq || '').toLowerCase();
  const list = S.voditeli.filter(v => !q || [v.fio, v.phone, v.auto_plate, v.trailer_plate, v.carrier].join(' ').toLowerCase().includes(q));
  $('#view').innerHTML = `
    <div class="bar"><h2 class="grow">Водители</h2>
      <input id="vq" placeholder="Поиск: ФИО, госномер, телефон, перевозчик" value="${esc(ui.vq || '')}" style="width:300px">
      <button class="btn" id="add">+ Водитель из файлов</button></div>
    ${list.length ? `<table><thead><tr><th>ФИО</th><th>Телефон</th><th>Тягач</th><th>Прицеп</th><th>Права до</th><th>Перевозчик</th><th class="num">Файлов</th></tr></thead>
      <tbody>${list.map(v => `<tr class="click" data-id="${v.id}"><td>${esc(v.fio)}</td><td>${esc(v.phone)}</td>
        <td>${esc([v.auto_brand, v.auto_plate].filter(Boolean).join(' '))}</td><td>${esc([v.trailer_brand, v.trailer_plate].filter(Boolean).join(' '))}</td>
        <td>${esc(v.vu_until)}</td><td>${esc(v.carrier)}</td><td class="num">${v.files.length}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">Водителей пока нет. Нажмите «+ Водитель из файлов» и перетащите фото паспорта, прав, СТС.</div>'}`;
  $('#vq').oninput = e => { ui.vq = e.target.value; saveUi(); viewVoditeli(); const i = $('#vq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $('#add').onclick = () => openVoditel(null);
  $('#view').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => openVoditel(+tr.dataset.id));
}

// ----- общее для окон «из файлов»: зона перетаскивания, выбор файлов, Ctrl+V → /api/raspoznat -----
const DROP_HTML = hint => `<div id="drop" class="drop">Перетащите сюда ${hint}<br>или <a href="#" id="pick">выберите файлы</a>,
  или скопируйте картинку и нажмите <b>Ctrl+V</b><input id="fileIn" type="file" multiple hidden
  accept=".jpg,.jpeg,.jfif,.png,.webp,.bmp,.pdf,.docx"></div><div id="ocrState" class="hint"></div><div id="thumbs"></div>`;
const fileUrl = p => '/files/' + p.split('/').map(encodeURIComponent).join('/');
const isImg = p => /\.(jpe?g|jfif|png|webp|bmp)$/i.test(p);

function fillEmpty(form, fields) {  // заполняет только пустые поля — то, что человек уже ввёл, не трогаем
  let n = 0;
  for (const [k, val] of Object.entries(fields)) {
    const i = form.querySelector(`[name="${k}"]`);
    if (i && val && !i.value.trim()) { i.value = val; n++; }
  }
  return n;
}

function bindDrop(kind, onResult) {
  const upload = async list => {
    list = [...list].filter(f => f.size);
    if (!list.length) return;
    const st = $('#ocrState');
    st.textContent = `Распознаю ${list.length} файл(а)… обычно 3–5 секунд на страницу`;
    const payload = await Promise.all(list.map(f => new Promise(res => {
      const r = new FileReader(); r.onload = () => res({ name: f.name || 'вставка.png', data: r.result }); r.readAsDataURL(f);
    })));
    try {
      const resp = await fetch('/api/raspoznat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, files: payload }) });
      const res = await resp.json();
      if (!resp.ok) throw new Error(res.error);
      st.innerHTML = onResult(res);
    } catch (e) { st.textContent = 'Ошибка распознавания: ' + e.message; }
  };
  $('#pick').onclick = e => { e.preventDefault(); $('#fileIn').click(); };
  $('#fileIn').onchange = e => upload(e.target.files);
  const drop = $('#drop');
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); upload(e.dataTransfer.files); };
  document.onpaste = e => {
    if ($('#modal').hidden || !$('#drop')) return;
    const imgs = [...(e.clipboardData?.files || [])];
    if (imgs.length) { e.preventDefault(); upload(imgs); }
  };
}

function thumbsHtml(files, docs, label) {
  return files.map(p => {
    const d = (docs || []).find(x => x.file === p);
    return `<div class="thumb">${isImg(p) ? `<a href="${fileUrl(p)}" target="_blank"><img src="${fileUrl(p)}"></a>` : `<a href="${fileUrl(p)}" target="_blank">📄 ${esc(p.split('/').pop())}</a>`}
      <div class="hint">${d ? (d.error ? 'ошибка — ' + esc(d.error) : label(d)) : esc(p.split('/').pop())}</div></div>`;
  }).join('');
}

// окно водителя: слева — файлы (перетащить / выбрать / Ctrl+V), справа — поля. onSaved(водитель) — вернуть в заявку.
function openVoditel(id, onSaved, onClose) {
  const v = id ? { ...vodById(id) } : { files: [] };
  let files = [...(v.files || [])];   // пути в app-sklad/files
  let doubts = {};

  openModal(`
    <div class="head"><h2>${id ? esc(v.fio || 'Водитель') : 'Новый водитель из файлов'}</h2><button class="x" data-close>×</button></div>
    <div class="vodwrap">
      <div class="vodfiles">${DROP_HTML('фото паспорта, прав, СТС')}</div>
      <form id="vf" class="vodform">
        ${VOD_GROUPS.map(([g, fields]) => `<fieldset><legend>${g}</legend><div class="grid">${fields.map(([k, lab, cls]) =>
          `<label class="${cls || ''}">${lab}<input name="${k}" value="${esc(v[k] || '')}"></label>`).join('')}</div></fieldset>`).join('')}
        <label class="full" style="display:flex;flex-direction:column;font-size:12px;color:var(--muted)">Примечание
          <textarea name="note" rows="2">${esc(v.note || '')}</textarea></label>
        <div class="foot"><div>${id ? '<button type="button" class="btn red" id="del">Удалить водителя</button>' : ''}</div>
          <div><button type="button" class="btn light" data-close>Закрыть</button> <button class="btn">Сохранить${onSaved ? ' и подставить в заявку' : ''}</button></div></div>
      </form>
    </div>`);
  if (onClose) $('#modalBox').querySelectorAll('[data-close]').forEach(b => b.onclick = () => onClose());

  const drawThumbs = docs => {
    $('#thumbs').innerHTML = thumbsHtml(files, docs, d => `<b>${esc(d.type)}</b> · найдено полей: ${d.found.length}`);
  };
  drawThumbs();
  const markDoubts = () => $('#vf').querySelectorAll('input[name]').forEach(i => {
    i.classList.toggle('gap', !!doubts[i.name]); i.title = doubts[i.name] || '';
  });

  bindDrop('voditel', res => {
    files.push(...res.docs.map(d => d.file).filter(Boolean));
    const filled = fillEmpty($('#vf'), res.fields);
    Object.assign(doubts, res.doubts);
    markDoubts(); drawThumbs(res.docs);
    return `Готово: заполнено полей — <b>${filled}</b>. Проверьте по картинкам${Object.keys(res.doubts).length ? ', жёлтые — особенно' : ''}.`;
  });
  $('#vf').querySelectorAll('input[name]').forEach(i => i.oninput = () => { delete doubts[i.name]; markDoubts(); });

  $('#vf').onsubmit = async e => {
    e.preventDefault();
    const d = { id, files };
    $('#vf').querySelectorAll('[name]').forEach(i => d[i.name] = i.value.trim());
    if (!id) {  // такой водитель уже есть? — обновим его, а не заведём второго
      const norm = s => (s || '').replace(/\s/g, '').toLowerCase();
      const same = S.voditeli.find(x => (d.passport && norm(x.passport) === norm(d.passport)) || (d.fio && norm(x.fio) === norm(d.fio)));
      if (same && confirm(`Водитель «${same.fio}» уже есть. Дополнить его карточку новыми данными?`)) {
        d.id = same.id;
        for (const k of Object.keys(d)) if (k !== 'files' && !d[k]) d[k] = same[k];
      }
    }
    const res = await api('voditel_save', d, 'Водитель сохранён');
    document.onpaste = null;
    if (onSaved) onSaved(vodById(res.id)); else openVoditel(res.id);
  };
  if ($('#del')) $('#del').onclick = async () => {
    if (!confirm('Удалить водителя из справочника? Файлы документов останутся в папке app-sklad/files.')) return;
    await api('voditel_delete', { id }, 'Удалено'); closeModal();
  };
}

// ===== Контрагенты: клиенты и перевозчики — из карточки предприятия или заявки клиента =====
const firmLabel = f => f ? `${f.name || 'без названия'}${f.inn ? ' · ИНН ' + f.inn : ''}` : '';
const firmById = id => S.firmy.find(f => f.id === id);
const firmDatalist = () => `<datalist id="firmList">${S.firmy.map(f => `<option value="${esc(firmLabel(f))}">`).join('')}</datalist>`;
const FIRM_GROUPS = [
  ['Компания', [['name', 'Наименование (ООО «…», ИП …)', 'wide'], ['inn', 'ИНН'], ['kpp', 'КПП'], ['ogrn', 'ОГРН / ОГРНИП']]],
  ['Адреса', [['address', 'Юридический адрес', 'full'], ['post_address', 'Почтовый адрес', 'full']]],
  ['Банк', [['rs', 'Расчётный счёт'], ['bik', 'БИК'], ['ks', 'Корр. счёт'], ['bank', 'Банк', 'wide']]],
  ['Подписант и связь', [['director', 'Руководитель / подписант', 'wide'], ['basis', 'Действует на основании'], ['phone', 'Телефон'], ['email', 'Эл. почта']]],
];

function viewFirmy() {
  const q = (ui.fq || '').toLowerCase();
  const list = S.firmy.filter(f => !q || [f.name, f.inn, f.phone, f.director].join(' ').toLowerCase().includes(q));
  const used = f => S.gruzy.filter(g => g.client_id === f.id).length + S.gruzy.filter(g => Object.values(g.legs).some(l => l.carrier_id === f.id)).length;
  $('#view').innerHTML = `
    <div class="bar"><h2 class="grow">Контрагенты — клиенты и перевозчики</h2>
      <input id="fq" placeholder="Поиск: название, ИНН, телефон" value="${esc(ui.fq || '')}" style="width:280px">
      <button class="btn" id="add">+ Из карточки или заявки</button></div>
    ${list.length ? `<table><thead><tr><th>Наименование</th><th>ИНН</th><th>Руководитель</th><th>Телефон</th><th>Счёт</th><th class="num">В заявках</th><th class="num">Файлов</th></tr></thead>
      <tbody>${list.map(f => `<tr class="click" data-id="${f.id}"><td>${esc(f.name)}</td><td>${esc(f.inn)}</td><td>${esc(f.director)}</td>
        <td>${esc(f.phone)}</td><td>${f.rs ? '✓' : ''}</td><td class="num">${used(f)}</td><td class="num">${f.files.length}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">Пока пусто. Нажмите «+ Из карточки или заявки» и перетащите карточку предприятия или заявку клиента.</div>'}`;
  $('#fq').oninput = e => { ui.fq = e.target.value; saveUi(); viewFirmy(); const i = $('#fq'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $('#add').onclick = () => openFirma(null);
  $('#view').querySelectorAll('tr[data-id]').forEach(tr => tr.onclick = () => openFirma(+tr.dataset.id));
}

// поля груза, которые берём из заявки клиента (режим «Заполнить из заявки клиента»)
const GRUZ_FROM_Z = [['client_doc', 'Заявка клиента (№, дата)', 'wide'], ['rate_client', 'Ставка клиента, ₽'], ['pay_form', 'НДС'],
  ['from_addr', 'Адрес погрузки', 'full'], ['dt_load', 'Дата погрузки', '', 'date'], ['to_addr', 'Адрес выгрузки', 'full'],
  ['dt_unload', 'Дата выгрузки', '', 'date'], ['cargo', 'Груз', 'wide'], ['kg', 'Вес, кг'], ['m3', 'Объём, м³'], ['places', 'Мест']];

function openFirma(id, onSaved, onClose, opt = {}) {
  const f = id ? { ...firmById(id) } : { files: [] };
  const zmode = !!opt.zayavka;  // заявка клиента: кроме реквизитов — данные груза
  let files = [...(f.files || [])], doubts = {}, auto = new Set(), cands = [];
  openModal(`
    <div class="head"><h2>${zmode ? 'Заполнить груз из заявки клиента' : id ? esc(f.name || 'Контрагент') : 'Новый контрагент из файлов'}</h2><button class="x" data-close>×</button></div>
    <div class="vodwrap">
      <div class="vodfiles">${DROP_HTML(zmode ? 'заявку клиента (PDF, фото, Word)' : 'карточку предприятия или заявку клиента (PDF, фото, Word)')}<div id="cands"></div></div>
      <form id="kf" class="vodform">
        ${zmode ? `<fieldset><legend>Груз из заявки — подставится только в пустые поля карточки груза</legend><div class="grid">${GRUZ_FROM_Z.map(([k, lab, cls, type]) =>
          k === 'pay_form' ? `<label>${lab}<select name="z_${k}">${formOpts('')}</select></label>`
            : `<label class="${cls || ''}">${lab}<input name="z_${k}" type="${type || 'text'}"></label>`).join('')}</div></fieldset>
          <p class="hint" style="margin:4px 0 0">Заказчик (реквизиты) — ниже. Если компании нет — оставьте пусто, подставится только груз.</p>` : ''}
        ${FIRM_GROUPS.map(([g, fields]) => `<fieldset><legend>${zmode ? 'Заказчик — ' + g.toLowerCase() : g}</legend><div class="grid">${fields.map(([k, lab, cls]) =>
          `<label class="${cls || ''}">${lab}<input name="${k}" value="${esc(f[k] || '')}"></label>`).join('')}</div></fieldset>`).join('')}
        <label class="full" style="display:flex;flex-direction:column;font-size:12px;color:var(--muted)">Примечание
          <textarea name="note" rows="2">${esc(f.note || '')}</textarea></label>
        <div class="foot"><div>${id ? '<button type="button" class="btn red" id="del">Удалить</button>' : ''}</div>
          <div><button type="button" class="btn light" data-close>Закрыть</button> <button class="btn">Сохранить${onSaved ? ' и подставить в заявку' : ''}</button></div></div>
      </form>
    </div>`);
  if (onClose) $('#modalBox').querySelectorAll('[data-close]').forEach(b => b.onclick = () => onClose());
  const form = $('#kf');
  const markDoubts = () => form.querySelectorAll('input[name]:not([name^="z_"])').forEach(i => { i.classList.toggle('gap', !!doubts[i.name]); i.title = doubts[i.name] || ''; });
  $('#thumbs').innerHTML = thumbsHtml(files, null, () => '');

  // выбрать компанию из найденных: поля, заполненные автоматически раньше, заменяем; введённые руками — не трогаем
  const choose = i => {
    const c = cands[i];
    for (const k of auto) { const inp = form.querySelector(`[name="${k}"]`); if (inp) inp.value = ''; }
    auto = new Set();
    for (const [k, v] of Object.entries(c.fields)) {
      const inp = form.querySelector(`[name="${k}"]`);
      if (inp && v && !inp.value.trim()) { inp.value = v; auto.add(k); }
    }
    doubts = { ...c.doubts }; markDoubts();
    $('#cands').querySelectorAll('[data-cand]').forEach(b => b.classList.toggle('on', +b.dataset.cand === i));
  };
  bindDrop(zmode ? 'zayavka' : 'firma', res => {
    files.push(...res.docs.map(d => d.file).filter(Boolean));
    $('#thumbs').innerHTML = thumbsHtml(files, res.docs, d => `компаний найдено: ${d.found}`);
    let zfilled = 0;
    if (zmode) {  // данные груза: в пустые поля, сомнительные — жёлтым
      zfilled = fillEmpty(form, Object.fromEntries(Object.entries(res.gruz || {}).map(([k, v]) => ['z_' + k, v])));
      for (const [k, msg] of Object.entries(res.gruz_doubts || {})) { const i = form.querySelector(`[name="z_${k}"]`); if (i) { i.classList.add('gap'); i.title = msg; } }
    }
    const zmsg = zmode ? `Груз: заполнено полей — <b>${zfilled}</b>. ` : '';
    cands = res.candidates;
    if (!cands.length) { $('#cands').innerHTML = ''; return zmsg + 'Реквизитов заказчика (кроме наших) не нашлось — впишите вручную или оставьте пусто.'; }
    $('#cands').innerHTML = cands.length > 1 ? `<p><b>В документе несколько компаний — какая нужна?</b></p>${cands.map((c, i) =>
      `<button type="button" class="chip" data-cand="${i}"><b>${esc(c.fields.name || 'без названия')}</b><span class="muted">ИНН ${esc(c.fields.inn)} · полей ${Object.keys(c.fields).length}</span></button>`).join(' ')}` : '';
    $('#cands').querySelectorAll('[data-cand]').forEach(b => b.onclick = () => choose(+b.dataset.cand));
    choose(0);
    const n = auto.size;
    return `${zmsg}${zmode ? 'Заказчик' : 'Готово'}: заполнено полей — <b>${n}</b>${cands.length > 1 ? `, выбрана первая из ${cands.length} компаний` : ''}. Наши реквизиты (ВЛ, ИП, МВЛ) пропущены. Проверьте по картинке${Object.keys(doubts).length ? ', жёлтые — особенно' : ''}.`;
  });
  form.querySelectorAll('input[name]').forEach(i => i.oninput = () => {
    if (i.name.startsWith('z_')) { i.classList.remove('gap'); i.title = ''; return; }
    delete doubts[i.name]; auto.delete(i.name); markDoubts();
  });

  form.onsubmit = async e => {
    e.preventDefault();
    const d = { id, files }, gz = {};
    form.querySelectorAll('[name]').forEach(i => {
      if (i.name.startsWith('z_')) gz[i.name.slice(2)] = i.value.trim(); else d[i.name] = i.value.trim();
    });
    let saved = null;
    if (d.name || d.inn || !zmode) {  // в режиме заявки компания необязательна — можно подставить только груз
      if (!id && d.inn) {  // такая компания уже есть — дополнить её карточку, а не заводить вторую
        const same = S.firmy.find(x => x.inn === d.inn);
        if (same && confirm(`«${same.name}» (ИНН ${same.inn}) уже есть. Дополнить её карточку новыми данными?`)) {
          d.id = same.id;
          for (const k of Object.keys(d)) if (k !== 'files' && !d[k]) d[k] = same[k];
        }
      }
      saved = firmById((await api('kontragent_save', d, 'Сохранено')).id);
    }
    document.onpaste = null;
    if (onSaved) onSaved(saved, gz); else openFirma(saved.id);
  };
  if ($('#del')) $('#del').onclick = async () => {
    if (!confirm('Удалить из справочника? В заявках название останется, файлы — в папке app-sklad/files.')) return;
    await api('kontragent_delete', { id }, 'Удалено'); closeModal();
  };
}

// ===== Вкладка «Склады» (справочник) =====
function viewNastr() {
  $('#view').innerHTML = `<h2>Склады</h2>
    <table><thead><tr><th>Название</th><th>Адрес</th><th></th></tr></thead><tbody>
    ${S.sklady.map(s => `<tr><td><input data-n="${s.id}" value="${esc(s.name)}"></td>
      <td><input data-a="${s.id}" value="${esc(s.address)}" style="width:100%"></td>
      <td><button class="btn small" data-save="${s.id}">Сохранить</button> <button class="btn small red" data-del="${s.id}">Удалить</button></td></tr>`).join('')}
    <tr><td><input id="nn" placeholder="Новый склад"></td><td><input id="na" placeholder="Адрес" style="width:100%"></td>
      <td><button class="btn small" id="nadd">Добавить</button></td></tr></tbody></table>
    <h2 style="margin-top:24px">Менеджеры</h2>
    <p class="hint">Кто ведёт заявку — для расчёта зарплаты. Переименование меняет имя и во всех его заявках; удаление из списка заявки не трогает.</p>
    <table style="max-width:600px"><thead><tr><th>Имя</th><th class="num">Заявок</th><th></th></tr></thead><tbody>
    ${S.managers.map(m => `<tr><td><input data-mn="${m.id}" value="${esc(m.name)}"></td>
      <td class="num">${S.gruzy.filter(g => g.manager === m.name).length}</td>
      <td><button class="btn small" data-msave="${m.id}">Сохранить</button> <button class="btn small red" data-mdel="${m.id}">Удалить</button></td></tr>`).join('')}
    <tr><td><input id="mn" placeholder="Новый менеджер"></td><td></td><td><button class="btn small" id="madd">Добавить</button></td></tr>
    </tbody></table>`;
  $('#view').querySelectorAll('[data-msave]').forEach(b => b.onclick = () =>
    api('manager_save', { id: +b.dataset.msave, name: $(`[data-mn="${b.dataset.msave}"]`).value }, 'Сохранено'));
  $('#view').querySelectorAll('[data-mdel]').forEach(b => b.onclick = () => {
    if (confirm('Убрать менеджера из списка? В его заявках имя останется.')) api('manager_delete', { id: +b.dataset.mdel }, 'Удалено');
  });
  $('#madd').onclick = () => api('manager_save', { name: $('#mn').value }, 'Добавлено');

  // вход в приложение: смена пароля (блокнот на рабочем столе обновится сам) и выход
  $('#view').insertAdjacentHTML('beforeend', `<h2 style="margin-top:24px">Вход в приложение</h2>
    <p class="hint">Логин и пароль — в блокноте «Склад ВЛ — вход» на рабочем столе. После смены пароля блокнот обновится, войти нужно будет заново.</p>
    <div class="bar"><input id="pwOld" type="password" placeholder="Старый пароль" autocomplete="current-password">
      <input id="pwNew" type="password" placeholder="Новый пароль (от 8 символов)" autocomplete="new-password">
      <button class="btn" id="pwGo">Сменить пароль</button><span class="grow"></span>
      <button class="btn light" id="logout">Выйти</button></div>`);
  $('#pwGo').onclick = async () => {
    const r = await fetch('/api/password', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old: $('#pwOld').value, new: $('#pwNew').value }) });
    const res = await r.json();
    if (!r.ok) return toast(res.error || 'Не удалось', true);
    toast('Пароль изменён, блокнот обновлён'); setTimeout(() => location.href = '/login', 1200);
  };
  $('#logout').onclick = async () => { await fetch('/api/logout', { method: 'POST' }); location.href = '/login'; };
  $('#view').querySelectorAll('[data-save]').forEach(b => b.onclick = () => {
    const i = b.dataset.save;
    api('sklad_save', { id: +i, name: $(`[data-n="${i}"]`).value, address: $(`[data-a="${i}"]`).value }, 'Сохранено');
  });
  $('#view').querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
    if (confirm('Удалить склад?')) api('sklad_delete', { id: +b.dataset.del }, 'Удалено');
  });
  $('#nadd').onclick = () => api('sklad_save', { name: $('#nn').value, address: $('#na').value }, 'Добавлено');
}

// ---------- окно ----------
function openModal(html) {
  $('#modalBox').innerHTML = html;
  $('#modal').hidden = false;
  $('#modalBox').querySelectorAll('[data-close]').forEach(b => b.onclick = closeModal);
}
function closeModal() { $('#modal').hidden = true; document.onpaste = null; render(); }
$('#modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });

load();
