/* Soshyant Expert — landing page behaviour */
(() => {
  'use strict';

  const cfg = window.SOSHYANT || {};
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Navigation ---------- */
  const nav = $('#nav');
  const toggle = $('.nav-toggle');
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 12);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  const setMenu = (open) => {
    nav.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  };
  toggle.addEventListener('click', () => setMenu(!nav.classList.contains('open')));
  $$('.nav-links a').forEach((a) => a.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });

  /* ---------- Reveal on scroll ---------- */
  const revealEls = $$('.reveal');
  if ('IntersectionObserver' in window && !reduceMotion) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add('in'));
  }

  /* ---------- Contact placeholders ---------- */
  const contact = cfg.contact || {};
  const clean = (v) => String(v || '').replace(/^\s*\[|\]\s*$/g, '').trim();

  $$('[data-contact]').forEach((el) => {
    const value = contact[el.dataset.contact];
    if (value) el.textContent = value;
  });

  $$('[data-contact-href]').forEach((a) => {
    const key = a.dataset.contactHref;
    const value = clean(contact[key]);
    if (!value) return;
    if (key === 'email') a.href = 'mailto:' + value + '?subject=' + encodeURIComponent('Soshyant Expert demo');
    else if (key === 'phone') a.href = 'tel:' + value.replace(/[^\d+]/g, '');
    else a.href = /^https?:\/\//i.test(value) ? value : 'https://' + value;
  });

  const avatar = $('#avatar');
  const initials = clean(contact.name).split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('');
  if (avatar && initials) avatar.textContent = initials.toUpperCase();

  const year = $('#year');
  if (year) year.textContent = new Date().getFullYear();

  /* ---------- Google Calendar booking ---------- */
  (function setupBooking() {
    const raw = String(cfg.bookingUrl || '').trim();
    const embed = $('#calEmbed');
    const placeholder = $('#calPlaceholder');
    const openLink = $('#calOpen');
    buildCalendarMock();
    if (!raw) return;

    let url;
    try { url = new URL(raw); } catch (e) {
      console.warn('[Soshyant] bookingUrl is not a valid URL:', raw);
      return;
    }

    const publicUrl = new URL(url.href);
    publicUrl.searchParams.delete('gv');
    openLink.href = publicUrl.href;
    openLink.hidden = false;

    const embeddable = url.hostname === 'calendar.google.com' && /\/appointments\//.test(url.pathname);
    if (embeddable) {
      url.searchParams.set('gv', 'true');
      const frame = document.createElement('iframe');
      frame.src = url.href;
      frame.title = 'Book a Soshyant Expert demo (Google Calendar)';
      frame.loading = 'lazy';
      embed.appendChild(frame);
      embed.hidden = false;
      placeholder.hidden = true;
    } else {
      // Short share links (calendar.app.google/…) can't be framed — offer a button instead.
      $('#calUnset').hidden = true;
      $('#calExternal').hidden = false;
      $('#calExternalBtn').href = url.href;
    }
  })();

  function buildCalendarMock() {
    const grid = $('#calGrid');
    if (!grid) return;
    const today = new Date();
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const days = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const lead = (first.getDay() + 6) % 7; // weeks start on Monday
    $('#calMonth').textContent = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

    const frag = document.createDocumentFragment();
    ['M', 'T', 'W', 'T', 'F', 'S', 'S'].forEach((d) => {
      const el = document.createElement('span');
      el.className = 'dow';
      el.textContent = d;
      frag.appendChild(el);
    });
    for (let i = 0; i < lead; i++) frag.appendChild(document.createElement('span'));

    let selected = null;
    for (let d = 1; d <= days; d++) {
      const date = new Date(today.getFullYear(), today.getMonth(), d);
      const weekday = date.getDay();
      const el = document.createElement('span');
      el.className = 'd';
      el.textContent = d;
      if (d > today.getDate() && weekday !== 0 && weekday !== 6 && d % 4 !== 1) {
        el.classList.add('av');
        if (!selected) { selected = date; el.classList.add('sel'); }
      }
      frag.appendChild(el);
    }
    grid.appendChild(frag);
    if (selected) {
      $('#calDay').textContent = selected.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
    }
  }

  /* ---------- Hero product demo ---------- */
  const scenarios = [
    {
      title: 'Pump housing torque',
      lang: 'en', dir: 'ltr',
      q: 'What’s the torque spec for the M12 bolts on the pump housing?',
      searching: 'Searching 412 documents…',
      status: 'ok', statusLabel: 'Answered', meta: '1 source cited',
      a: 'Tighten them to 60 N·m in a star pattern, in two passes — 30 N·m first, then 60 N·m. Re-check the torque after the first heat cycle.',
      cite: '1',
      src: { title: 'Pump Manual rev. 4', loc: '§7.2 Assembly · version 4',
        quote: 'Torque the M12 housing bolts to <mark>60 N·m in a star pattern, in two passes (30 N·m, then 60 N·m)</mark>. Re-torque after the first heat cycle.' }
    },
    {
      title: 'Contractor parental leave',
      lang: 'en', dir: 'ltr',
      q: 'Do contractors get paid parental leave?',
      searching: 'Searching 412 documents…',
      status: 'warn', statusLabel: 'Insufficient evidence', meta: 'Closest source shown',
      a: 'I couldn’t find a policy for contractors in the approved documents. The HR Handbook only covers parental leave for employees — please check with HR, or ask an admin to add the contractor policy.',
      cite: '1',
      src: { title: 'HR Handbook 2026', loc: '§4.3 Parental leave · version 7',
        quote: 'Paid parental leave applies to <mark>permanent and fixed-term employees</mark> after six months of continuous service.' }
    },
    {
      title: 'شرایط گارانتی دستگاه',
      lang: 'fa', dir: 'rtl',
      q: 'مدت گارانتی دستگاه چقدر است و چه مدارکی لازم دارد؟',
      searching: 'جست‌وجو در ۴۱۲ سند…',
      status: 'ok', statusLabel: 'پاسخ مستند', meta: '۱ منبع',
      a: 'گارانتی دستگاه ۲۴ ماه از تاریخ نصب است. برای ثبت درخواست، فاکتور خرید و برگه نصبِ امضاشده لازم است.',
      cite: '۱',
      src: { title: 'شرایط گارانتی', loc: 'بند ۲.۱ · نسخه ۳',
        quote: '<mark>دوره گارانتی ۲۴ ماه از تاریخ نصب</mark> است. ارائه فاکتور خرید و برگه نصب امضاشده برای ثبت درخواست الزامی است.' }
    }
  ];

  const el = {
    stream: $('#stream'), title: $('#convTitle'), q: $('#mQ'), a: $('#mA'),
    meta: $('#mMeta'), status: $('#mStatus'), metaText: $('#mMetaText'),
    search: $('#mSearch'), searchText: $('#mSearchText'), text: $('#mText'),
    source: $('#mSource'), sCite: $('#sCite'), sTitle: $('#sTitle'), sLoc: $('#sLoc'), sQuote: $('#sQuote')
  };
  const convButtons = $$('.app-conv');
  let run = 0;
  let timer = null;
  let current = 0;

  const sleep = (ms, id) => new Promise((resolve) => {
    timer = setTimeout(() => { if (id === run) resolve(); }, ms);
  });

  function setChrome(s, i) {
    convButtons.forEach((b, k) => b.classList.toggle('active', k === i));
    el.stream.lang = s.lang;
    el.stream.dir = s.dir;
    el.title.textContent = s.title;
  }

  function citeEl(label, animate) {
    const c = document.createElement('span');
    c.className = 'cite' + (animate ? ' pop' : '');
    c.textContent = label;
    return c;
  }

  function fillSource(s) {
    el.sCite.textContent = s.cite;
    el.sTitle.textContent = s.src.title;
    el.sLoc.textContent = s.src.loc;
    el.sQuote.innerHTML = s.src.quote; // static, trusted copy defined above
  }

  function renderFinal(s) {
    el.q.textContent = s.q;
    el.a.hidden = false;
    el.search.hidden = true;
    el.meta.hidden = false;
    el.status.className = 'm-status ' + s.status;
    el.status.textContent = s.statusLabel;
    el.metaText.textContent = s.meta;
    el.text.hidden = false;
    el.text.textContent = s.a;
    el.text.appendChild(citeEl(s.cite, false));
    fillSource(s);
    el.source.hidden = false;
  }

  async function play(i) {
    const id = ++run;
    clearTimeout(timer);
    current = i;
    const s = scenarios[i];
    setChrome(s, i);

    if (reduceMotion) {
      renderFinal(s);
      await sleep(9000, id);
      return play((i + 1) % scenarios.length);
    }

    // reset
    el.q.textContent = '';
    el.a.hidden = true;
    el.source.hidden = true;
    el.text.textContent = '';

    await sleep(450, id);
    const caret = document.createElement('span');
    caret.className = 'caret';
    el.q.appendChild(caret);
    for (const ch of s.q) {
      caret.before(ch);
      await sleep(16 + Math.random() * 34, id);
    }
    caret.remove();
    el.q.normalize();

    await sleep(380, id);
    el.a.hidden = false;
    el.meta.hidden = true;
    el.text.hidden = true;
    el.search.hidden = false;
    el.searchText.textContent = s.searching;

    await sleep(1500, id);
    el.search.hidden = true;
    el.meta.hidden = false;
    el.status.className = 'm-status ' + s.status;
    el.status.textContent = s.statusLabel;
    el.metaText.textContent = s.meta;
    el.text.hidden = false;

    const words = s.a.split(' ');
    let built = '';
    for (let w = 0; w < words.length; w++) {
      built += (w ? ' ' : '') + words[w];
      el.text.textContent = built;
      await sleep(38 + Math.random() * 46, id);
    }
    await sleep(220, id);
    el.text.appendChild(citeEl(s.cite, true));

    await sleep(500, id);
    fillSource(s);
    el.source.hidden = false;

    await sleep(6800, id);
    play((i + 1) % scenarios.length);
  }

  convButtons.forEach((b, k) => b.addEventListener('click', () => play(k)));

  // Only animate while the preview is on screen.
  const app = $('.app');
  if (app && 'IntersectionObserver' in window) {
    let started = false;
    new IntersectionObserver((entries) => {
      const visible = entries[0].isIntersecting;
      if (visible && !started) { started = true; play(current); }
      else if (!visible && started) { started = false; run++; clearTimeout(timer); renderFinal(scenarios[current]); }
    }, { threshold: 0.25 }).observe(app);
  } else {
    play(0);
  }
})();
