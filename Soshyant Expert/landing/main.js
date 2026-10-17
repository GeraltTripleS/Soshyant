/* Soshyant Expert — cyberpunk landing page behaviour */
(() => {
  'use strict';

  const cfg = window.SOSHYANT || {};
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const html = document.documentElement;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=<>/\\[]{}';
  const GLYPHS_FA = 'ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی۰۱۲۳۴۵۶۷۸۹';
  const onView = (el, cb, opts) => {
    if (!el) return;
    if (!('IntersectionObserver' in window)) { cb(true); return; }
    new IntersectionObserver((es) => cb(es[0].isIntersecting), opts).observe(el);
  };

  /* ---------- Language (English default, Persian from fa.js) ---------- */
  const FA = window.SOSHYANT_FA || null;
  const LANG_KEY = 'soshyant-landing-lang';
  let lang = html.lang === 'fa' && FA ? 'fa' : 'en';
  const isFa = () => lang === 'fa';
  const T = (key, en) => (isFa() && FA.ui[key] != null ? FA.ui[key] : en);
  const digits = (v) => (isFa() ? String(v).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]) : String(v));
  const dec = (x, n) => (isFa() ? digits(x.toFixed(n)).replace('.', '٫') : x.toFixed(n));
  const onLang = (fn) => document.addEventListener('langchange', fn);
  const setText = (el, text) => { el._scr = (el._scr || 0) + 1; el.textContent = text; }; // also stops a running scramble

  function i18n() {
    const nodes = $$('[data-i18n]').map((el) => ({ el, key: el.dataset.i18n, en: el.innerHTML }));
    const attrs = [];
    $$('[data-i18n-attr]').forEach((el) => el.dataset.i18nAttr.split(';').forEach((pair) => {
      const [name, key] = pair.split(':').map((s) => s.trim());
      if (name && key) attrs.push({ el, name, key, en: el.getAttribute(name) });
    }));
    const meta = $('meta[name="description"]');
    const en = { title: document.title, desc: meta ? meta.content : '' };
    const pick = (key, fallback) => (isFa() && FA.text[key] != null ? FA.text[key] : fallback);

    function apply(next, byUser) {
      if (next === 'fa' && !FA) next = 'en';
      const changed = next !== lang;
      lang = next;
      html.lang = next;
      html.dir = next === 'fa' ? 'rtl' : 'ltr';
      nodes.forEach((n) => { n.el._scr = (n.el._scr || 0) + 1; n.el.innerHTML = pick(n.key, n.en); });
      attrs.forEach((a) => a.el.setAttribute(a.name, pick(a.key, a.en)));
      document.title = pick('meta.title', en.title);
      if (meta) meta.content = pick('meta.desc', en.desc);
      $$('[data-num]').forEach((el) => { if (!el.dataset.num) el.dataset.num = el.textContent; el.textContent = digits(el.dataset.num); });
      $$('.copy').forEach((b) => { b.textContent = T('copy', 'copy'); });
      html.classList.remove('i18n-pending');
      if (!byUser) return;
      try { localStorage.setItem(LANG_KEY, next); } catch (e) { /* storage blocked */ }
      const url = new URL(location.href);
      if (url.searchParams.has('lang')) { url.searchParams.set('lang', next); history.replaceState(null, '', url); }
      if (!reduce) {
        html.classList.add('lang-swap');
        setTimeout(() => html.classList.remove('lang-swap'), 450);
        $$('.rv.in [data-scramble]').forEach((s) => scramble(s));
      }
      if (changed) document.dispatchEvent(new CustomEvent('langchange'));
    }

    const btn = $('#langBtn');
    if (btn) {
      if (!FA) btn.hidden = true;
      btn.addEventListener('click', () => apply(isFa() ? 'en' : 'fa', true));
    }
    apply(lang, false);
  }

  /* ---------- Boot sequence ---------- */
  function boot() {
    return new Promise((resolve) => {
      const el = $('#boot');
      if (!el || !html.classList.contains('booting')) { if (el) el.remove(); resolve(); return; }
      const lines = $$('.boot-line', el);
      const bar = $('.boot-bar i', el);
      const pct = $('#bootPct');
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        try { sessionStorage.setItem('sx-boot', '1'); } catch (e) { /* private mode */ }
        el.classList.add('out');
        setTimeout(() => { html.classList.remove('booting'); el.remove(); resolve(); }, 520);
      };
      el.addEventListener('click', finish);
      window.addEventListener('keydown', finish, { once: true });
      const step = 165;
      lines.forEach((line, i) => setTimeout(() => {
        line.classList.add('on');
        const p = Math.round(((i + 1) / lines.length) * 100);
        bar.style.width = p + '%';
        pct.textContent = digits(String(p).padStart(3, '0')) + '%';
      }, 200 + i * step));
      setTimeout(finish, 200 + lines.length * step + 450);
    });
  }

  /* ---------- Nav, progress, side rail ---------- */
  function nav() {
    const bar = $('#nav');
    const toggle = $('.nav-toggle');
    const progress = $('#progressBar');
    const pct = $('#railPct');
    let ticking = false;
    const update = () => {
      ticking = false;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? window.scrollY / max : 0;
      bar.classList.toggle('scrolled', window.scrollY > 10);
      progress.style.transform = `scaleX(${p})`;
      if (pct) pct.textContent = digits(String(Math.round(p * 100)).padStart(3, '0')) + '%';
    };
    window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();

    const setMenu = (open) => {
      bar.classList.toggle('open', open);
      html.classList.toggle('menu-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? T('menuClose', 'Close menu') : T('menuOpen', 'Open menu'));
    };
    setMenu(false);
    onLang(() => { setMenu(bar.classList.contains('open')); update(); });
    toggle.addEventListener('click', () => setMenu(!bar.classList.contains('open')));
    $$('.nav-links a').forEach((a) => a.addEventListener('click', () => setMenu(false)));
    window.addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });

    const rail = $$('.rail a');
    if (rail.length && 'IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => entries.forEach((e) => {
        if (!e.isIntersecting) return;
        rail.forEach((a) => a.classList.toggle('active', a.dataset.sec === e.target.id));
      }), { rootMargin: '-45% 0px -50% 0px' });
      rail.forEach((a) => { const s = document.getElementById(a.dataset.sec); if (s) io.observe(s); });
    }
  }

  /* ---------- Custom cursor ---------- */
  function cursor() {
    if (!fine || reduce) return;
    const dot = $('.cur-dot');
    const ring = $('.cur-ring');
    const label = $('.cur-label');
    html.classList.add('cursor-on');
    let x = -100, y = -100, rx = -100, ry = -100;
    const show = (v) => { dot.style.opacity = ring.style.opacity = v ? '1' : '0'; };
    window.addEventListener('pointermove', (e) => { x = e.clientX; y = e.clientY; show(true); }, { passive: true });
    document.addEventListener('pointerout', (e) => { if (!e.relatedTarget || e.relatedTarget.tagName === 'IFRAME') show(false); });
    document.addEventListener('pointerover', (e) => {
      if (e.target.tagName === 'IFRAME') { show(false); return; }
      const t = e.target.closest('a, button, summary, [data-cursor]');
      ring.classList.toggle('hover', !!t);
      const key = t ? (t.dataset.cursor || (t.tagName === 'SUMMARY' ? 'EXPAND' : t.tagName === 'A' ? 'OPEN' : 'SELECT')) : '';
      label.textContent = (isFa() && FA.ui.cursor && FA.ui.cursor[key]) || key;
    });
    window.addEventListener('pointerdown', () => ring.classList.add('down'));
    window.addEventListener('pointerup', () => ring.classList.remove('down'));
    const loop = () => {
      rx += (x - rx) * 0.22;
      ry += (y - ry) * 0.22;
      dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
      requestAnimationFrame(loop);
    };
    loop();
  }

  /* ---------- Magnetic buttons + tilt cards ---------- */
  function magnetic() {
    if (!fine || reduce) return;
    $$('.magnetic').forEach((el) => {
      el.addEventListener('pointermove', (e) => {
        const r = el.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height / 2);
        el.style.transform = `translate(${dx * 0.2}px, ${dy * 0.3}px)`;
      });
      el.addEventListener('pointerleave', () => { el.style.transform = ''; });
    });
  }

  function tilt() {
    if (!fine || reduce) return;
    $$('.tilt').forEach((el) => {
      const max = el.classList.contains('idcard') ? 12 : 6;
      el.addEventListener('pointermove', (e) => {
        const r = el.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        el.classList.add('tilting');
        el.style.setProperty('--ry', ((px - 0.5) * max).toFixed(2) + 'deg');
        el.style.setProperty('--rx', ((0.5 - py) * max).toFixed(2) + 'deg');
        el.style.setProperty('--mx', (px * 100).toFixed(1) + '%');
        el.style.setProperty('--my', (py * 100).toFixed(1) + '%');
        el.style.setProperty('--hx', (px * 100).toFixed(1) + '%');
        el.style.setProperty('--hy', (py * 100).toFixed(1) + '%');
      });
      el.addEventListener('pointerleave', () => {
        el.classList.remove('tilting');
        el.style.setProperty('--rx', '0deg');
        el.style.setProperty('--ry', '0deg');
      });
    });
  }

  /* ---------- Text effects ---------- */
  function scramble(el, text = el.textContent, duration = 700) {
    const token = (el._scr = (el._scr || 0) + 1);
    if (reduce) { el.textContent = text; return; }
    const set = /[؀-ۿ]/.test(text) ? GLYPHS_FA : GLYPHS;
    const start = performance.now();
    const frame = (now) => {
      if (token !== el._scr) return;
      const p = clamp((now - start) / duration, 0, 1);
      const n = Math.floor(p * text.length);
      let out = text.slice(0, n);
      for (let i = n; i < text.length; i++) out += text[i] === ' ' ? ' ' : set[(Math.random() * set.length) | 0];
      el.textContent = out;
      if (p < 1) requestAnimationFrame(frame); else el.textContent = text;
    };
    requestAnimationFrame(frame);
  }

  function countUp(el) {
    const to = Number(el.dataset.count);
    el._n = to;
    if (reduce) { el.textContent = digits(to); return; }
    const start = performance.now();
    const frame = (now) => {
      const p = clamp((now - start) / 1400, 0, 1);
      el._n = Math.round(to * (1 - Math.pow(1 - p, 3)));
      el.textContent = digits(el._n);
      if (p < 1) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }
  const countDigits = () => $$('[data-count]').forEach((el) => { el.textContent = digits(el._n != null ? el._n : el.dataset.count); });

  function typeTerminal(el) {
    $$('li', el).forEach((li, i) => setTimeout(() => li.classList.add('on'), reduce ? 0 : 250 + i * 230));
  }

  function reveal() {
    const els = $$('.rv');
    const enter = (el) => {
      el.classList.add('in');
      $$('[data-scramble]', el).forEach((s) => scramble(s));
      $$('[data-count]', el).forEach(countUp);
      if (el.id === 'secTerm') typeTerminal(el);
    };
    if (!('IntersectionObserver' in window)) { els.forEach(enter); return; }
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { enter(e.target); io.unobserve(e.target); }
    }), { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
    els.forEach((el) => io.observe(el));
  }

  /* ---------- Hero: live vector space ----------
     Points are passages from different documents, embedded in a 3D space.
     The cursor is the query vector; the five nearest passages light up. */
  function vectorField() {
    const canvas = $('#vecField');
    const hero = $('.hero');
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');
    const list = $('#nnList');
    const coord = $('#qCoord');
    const DOCS = [
      { n: 'PUMP_MANUAL', c: [25, 255, 176] },
      { n: 'SAFETY_PROC', c: [110, 246, 255] },
      { n: 'HR_HANDBOOK', c: [255, 181, 71] },
      { n: 'WARRANTY', c: [255, 61, 129] },
      { n: 'MAINT_SCHED', c: [25, 255, 176] },
      { n: 'HYDRAULICS', c: [110, 246, 255] },
      { n: 'GEARBOX', c: [255, 181, 71] }
    ];
    let W = 0, H = 0, pts = [], pairs = [], running = false, lastPanel = 0, lastMove = -1e9;
    const q = { x: 0, y: 0, tx: 0, ty: 0, user: false };
    const near = new Array(5);
    const nd = new Array(5);

    function build() {
      const n = W < 700 ? 120 : 240;
      const centers = DOCS.map((d, i) => {
        const a = (i / DOCS.length) * Math.PI * 2;
        return [Math.cos(a) * 0.62, Math.sin(i * 2.1) * 0.32, Math.sin(a) * 0.62];
      });
      pts = [];
      for (let i = 0; i < n; i++) {
        const d = i % DOCS.length;
        const [cx, cy, cz] = centers[d];
        const r = 0.3 * Math.cbrt(Math.random());
        const th = Math.random() * Math.PI * 2;
        const ph = Math.acos(2 * Math.random() - 1);
        pts.push({
          x: cx + r * Math.sin(ph) * Math.cos(th), y: cy + r * Math.cos(ph), z: cz + r * Math.sin(ph) * Math.sin(th),
          d, sec: '§' + (1 + ((Math.random() * 9) | 0)) + '.' + (1 + ((Math.random() * 6) | 0)), sx: 0, sy: 0, s: 1
        });
      }
      pairs = [];
      for (let i = 0; i < pts.length; i++) {
        let k = 0;
        for (let j = i + 1; j < pts.length && k < 2; j++) {
          const a = pts[i], b = pts[j];
          if (a.d !== b.d) continue;
          const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
          if (dx * dx + dy * dy + dz * dz < 0.022) { pairs.push([i, j]); k++; }
        }
      }
    }

    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth, h = canvas.clientHeight;
      const rebuild = !pts.length || (w < 700) !== (W < 700);
      W = w; H = h;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (rebuild) build();
      if (!q.x) { q.x = q.tx = W * side(); q.y = q.ty = H * 0.45; }
    }

    hero.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse') return;
      const r = canvas.getBoundingClientRect();
      q.tx = e.clientX - r.left;
      q.ty = e.clientY - r.top;
      q.user = true;
      lastMove = performance.now();
    });
    hero.addEventListener('pointerleave', () => { q.user = false; });

    const fmt = (v) => (v >= 0 ? '+' : '') + v.toFixed(2);
    // The cloud sits opposite the headline: right of centre in English, left in Persian.
    const side = () => (isFa() ? 0.32 : 0.68);

    function draw(now) {
      const t = now / 1000;
      const narrow = W < 900;
      if (!q.user || now - lastMove > 3500) {
        q.tx = W * (narrow ? 0.5 : side()) + Math.sin(t * 0.37) * W * (narrow ? 0.3 : 0.18);
        q.ty = H * 0.5 + Math.sin(t * 0.53 + 1.2) * H * 0.24;
      }
      q.x += (q.tx - q.x) * 0.1;
      q.y += (q.ty - q.y) * 0.1;

      ctx.clearRect(0, 0, W, H);
      const ry = t * 0.07, rx = -0.35 + Math.sin(t * 0.13) * 0.06;
      const cY = Math.cos(ry), sY = Math.sin(ry), cX = Math.cos(rx), sX = Math.sin(rx);
      const ox = W * (narrow ? 0.5 : side()), oy = H * 0.5;
      const sc = Math.min(W, H) * (narrow ? 0.62 : 0.6), f = 2.8;
      for (const p of pts) {
        const x = p.x * cY - p.z * sY;
        let z = p.x * sY + p.z * cY;
        const y = p.y * cX - z * sX;
        z = p.y * sX + z * cX;
        const s = f / (f + z);
        p.sx = ox + x * sc * s; p.sy = oy + y * sc * s; p.s = s;
      }

      near.fill(null); nd.fill(Infinity);
      for (const p of pts) {
        const dx = p.sx - q.x, dy = p.sy - q.y, d = dx * dx + dy * dy;
        if (d < nd[4]) {
          let k = 4;
          while (k > 0 && d < nd[k - 1]) { nd[k] = nd[k - 1]; near[k] = near[k - 1]; k--; }
          nd[k] = d; near[k] = p;
        }
      }

      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(25,255,176,0.08)';
      ctx.beginPath();
      for (const [i, j] of pairs) { ctx.moveTo(pts[i].sx, pts[i].sy); ctx.lineTo(pts[j].sx, pts[j].sy); }
      ctx.stroke();

      for (const p of pts) {
        const [r, g, b] = DOCS[p.d].c;
        const a = clamp((p.s - 0.72) * 1.7, 0.14, 0.85);
        const sz = 1.2 + (p.s - 0.7) * 3.4;
        ctx.fillStyle = `rgba(${r},${g},${b},${a.toFixed(2)})`;
        ctx.fillRect(p.sx - sz / 2, p.sy - sz / 2, sz, sz);
      }

      ctx.strokeStyle = 'rgba(25,255,176,0.09)';
      ctx.beginPath();
      ctx.moveTo(0, q.y); ctx.lineTo(W, q.y);
      ctx.moveTo(q.x, 0); ctx.lineTo(q.x, H);
      ctx.stroke();

      ctx.font = '500 10px "JetBrains Mono", monospace';
      near.forEach((p, i) => {
        if (!p) return;
        const g = ctx.createLinearGradient(q.x, q.y, p.sx, p.sy);
        g.addColorStop(0, 'rgba(255,181,71,0.9)');
        g.addColorStop(1, 'rgba(25,255,176,0.7)');
        ctx.strokeStyle = g;
        ctx.lineWidth = i === 0 ? 1.6 : 1;
        ctx.beginPath(); ctx.moveTo(q.x, q.y); ctx.lineTo(p.sx, p.sy); ctx.stroke();
        ctx.strokeStyle = i === 0 ? '#ffb547' : '#19ffb0';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(p.sx - 4, p.sy - 4, 8, 8);
        if (i < 3 && W >= 700) {
          ctx.fillStyle = i === 0 ? 'rgba(255,181,71,0.95)' : 'rgba(220,255,243,0.75)';
          ctx.fillText(`${DOCS[p.d].n} ${p.sec}`, p.sx + 9, p.sy - 7);
        }
      });

      const pulse = 14 + Math.sin(t * 4) * 2;
      ctx.strokeStyle = '#ffb547';
      ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(q.x, q.y, pulse, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#ffb547';
      ctx.beginPath(); ctx.arc(q.x, q.y, 3, 0, Math.PI * 2); ctx.fill();
      ctx.font = '700 10px "JetBrains Mono", Vazirmatn, monospace';
      ctx.fillText(T('queryLabel', 'QUERY'), q.x + pulse + 6, q.y + 3);

      if (list && now - lastPanel > 150) {
        lastPanel = now;
        const span = Math.max(W, H);
        list.innerHTML = near.map((p, i) => p
          ? `<li><b>0${i + 1}</b><span>${DOCS[p.d].n} ${p.sec}</span><span>${clamp(0.97 - (Math.sqrt(nd[i]) / span) * 1.6, 0.3, 0.99).toFixed(2)}</span></li>`
          : '').join('');
        if (coord) coord.textContent = `[${fmt((q.x / W) * 2 - 1)}, ${fmt(1 - (q.y / H) * 2)}]`;
      }
    }

    const loop = (now) => { if (!running) return; draw(now); requestAnimationFrame(loop); };
    resize();
    window.addEventListener('resize', () => { resize(); if (!running) draw(performance.now()); });
    if (reduce) { draw(performance.now()); return; }
    let visible = true;
    const sync = () => {
      const want = visible && !document.hidden;
      if (want && !running) { running = true; requestAnimationFrame(loop); }
      else if (!want) running = false;
    };
    onView(hero, (v) => { visible = v; sync(); });
    document.addEventListener('visibilitychange', sync);
    sync();
  }

  /* ---------- 01 Live console ---------- */
  function consoleDemo() {
    const S = [
      {
        lang: 'en', dir: 'ltr',
        q: 'What’s the torque spec for the M12 bolts on the pump housing?',
        log: [['embed(query)', '384-d vector'], ['retrieve --hybrid', '12 candidates'], ['filter --acl', '3 passages allowed'], ['generate --grounded', 'cited']],
        status: 'ok', statusLabel: 'ANSWERED', meta: '1 source cited',
        a: 'Tighten them to 60 N·m in a star pattern, in two passes — 30 N·m first, then 60 N·m. Re-check the torque after the first heat cycle.',
        cite: '1',
        src: { title: 'Pump Manual rev. 4', loc: '§7.2 Assembly · version 4',
          quote: 'Torque the M12 housing bolts to <mark>60 N·m in a star pattern, in two passes (30 N·m, then 60 N·m)</mark>. Re-torque after the first heat cycle.' }
      },
      {
        lang: 'en', dir: 'ltr',
        q: 'Do contractors get paid parental leave?',
        log: [['embed(query)', '384-d vector'], ['retrieve --hybrid', '7 candidates'], ['filter --acl', '2 passages allowed'], ['generate --grounded', 'evidence insufficient']],
        status: 'warn', statusLabel: 'INSUFFICIENT EVIDENCE', meta: 'closest source shown',
        a: 'I couldn’t find a policy for contractors in the approved documents. The HR Handbook only covers parental leave for employees — check with HR, or ask an admin to add the contractor policy.',
        cite: '1',
        src: { title: 'HR Handbook 2026', loc: '§4.3 Parental leave · version 7',
          quote: 'Paid parental leave applies to <mark>permanent and fixed-term employees</mark> after six months of continuous service.' }
      },
      {
        lang: 'fa', dir: 'rtl',
        q: 'مدت گارانتی دستگاه چقدر است و چه مدارکی لازم دارد؟',
        log: [['embed(query)', '384-d vector'], ['retrieve --hybrid', '9 candidates'], ['filter --acl', '2 passages allowed'], ['generate --grounded', 'cited']],
        status: 'ok', statusLabel: 'پاسخ مستند', meta: '۱ منبع',
        a: 'گارانتی دستگاه ۲۴ ماه از تاریخ نصب است. برای ثبت درخواست، فاکتور خرید و برگه نصبِ امضاشده لازم است.',
        cite: '۱',
        src: { title: 'شرایط گارانتی', loc: 'بند ۲.۱ · نسخه ۳',
          quote: '<mark>دوره گارانتی ۲۴ ماه از تاریخ نصب</mark> است. ارائه فاکتور خرید و برگه نصب امضاشده برای ثبت درخواست الزامی است.' }
      }
    ];
    const el = {
      main: $('#stream'), q: $('#mQ'), log: $('#mLog'), a: $('#mA'), status: $('#mStatus'), meta: $('#mMetaText'),
      text: $('#mText'), src: $('#mSource'), sCite: $('#sCite'), sTitle: $('#sTitle'), sLoc: $('#sLoc'), sQuote: $('#sQuote')
    };
    const box = $('#consoleBox');
    if (!box) return;
    // Persian page: the two English sessions are replaced by their Persian versions from fa.js.
    const sessions = () => (isFa() ? FA.console.map((f, i) => ({ ...S[i], ...f, lang: 'fa', dir: 'rtl' })).concat(S.slice(FA.console.length)) : S);
    const btns = $$('.con-sess');
    let run = 0, timer = null, cur = 0, started = false;
    const sleep = (ms, id) => new Promise((res) => { timer = setTimeout(() => { if (id === run) res(); }, ms); });
    const citeEl = (c, pop) => { const s = document.createElement('span'); s.className = 'cite' + (pop ? ' pop' : ''); s.textContent = c; return s; };
    const logLine = (cmd, res, done) => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="cmd">› ${cmd}</span><span class="dots"></span><span class="res${done ? '' : ' spin'}">${done ? '✓ ' + res : '|'}</span>`;
      return li;
    };
    const fillSource = (s) => {
      el.sCite.textContent = s.cite; el.sTitle.textContent = s.src.title; el.sLoc.textContent = s.src.loc;
      el.sQuote.innerHTML = s.src.quote; // static, trusted copy defined above
    };
    const showMeta = (s) => {
      el.a.hidden = false;
      el.status.className = 'status ' + s.status;
      el.status.textContent = s.statusLabel;
      el.meta.textContent = s.meta;
    };
    const final = (s) => {
      el.q.textContent = s.q;
      el.log.innerHTML = '';
      s.log.forEach(([c, r]) => el.log.appendChild(logLine(c, r, true)));
      showMeta(s);
      el.text.textContent = s.a;
      el.text.appendChild(citeEl(s.cite));
      fillSource(s);
      el.src.hidden = false;
    };

    async function play(i) {
      const id = ++run;
      clearTimeout(timer);
      cur = i;
      const list = sessions();
      const s = list[i];
      btns.forEach((b, k) => b.classList.toggle('active', k === i));
      el.main.lang = s.lang;
      el.main.dir = s.dir;
      if (reduce) { final(s); await sleep(9000, id); return play((i + 1) % list.length); }

      el.q.textContent = '';
      el.log.innerHTML = '';
      el.a.hidden = true;
      el.src.hidden = true;
      el.text.textContent = '';
      await sleep(350, id);
      const caret = document.createElement('i');
      caret.className = 'caret';
      el.q.appendChild(caret);
      for (const ch of s.q) { caret.before(ch); await sleep(14 + Math.random() * 28, id); }
      caret.remove();
      el.q.normalize();
      await sleep(250, id);

      for (const [c, r] of s.log) {
        const li = logLine(c, r, false);
        el.log.appendChild(li);
        const res = $('.res', li);
        for (let k = 0; k < 6; k++) { res.textContent = '|/-\\'[k % 4]; await sleep(55, id); }
        res.className = 'res';
        res.textContent = '✓ ' + r;
        await sleep(80, id);
      }

      showMeta(s);
      const words = s.a.split(' ');
      let built = '';
      for (let w = 0; w < words.length; w++) {
        built += (w ? ' ' : '') + words[w];
        el.text.textContent = built;
        await sleep(32 + Math.random() * 38, id);
      }
      await sleep(180, id);
      el.text.appendChild(citeEl(s.cite, true));
      await sleep(420, id);
      fillSource(s);
      el.src.hidden = false;
      await sleep(6500, id);
      play((i + 1) % list.length);
    }

    const still = () => {
      run++; clearTimeout(timer);
      const s = sessions()[cur];
      el.main.lang = s.lang; el.main.dir = s.dir;
      final(s);
    };
    btns.forEach((b, k) => b.addEventListener('click', () => play(k)));
    still();
    onView(box, (v) => {
      if (v && !started) { started = true; play(cur); }
      else if (!v && started) { started = false; still(); }
    }, { threshold: 0.3 });
    onLang(() => { if (started) play(cur); else still(); });
  }

  /* ---------- 03 RAG pipeline simulator ---------- */
  function ragSim() {
    const root = $('#sim');
    if (!root) return;
    const CHUNKS = {
      c1: { doc: 'Pump Manual rev.4', loc: '§7.2', text: 'Torque M12 housing bolts to 60 N·m in a star pattern, in two passes.' },
      c2: { doc: 'Pump Manual rev.4', loc: '§7.4', text: 'Re-torque the housing bolts after the first heat cycle.' },
      c3: { doc: 'Maint. Schedule v6', loc: '§3.4', text: 'Replace the hydraulic filter cartridge every 500 operating hours.' },
      c4: { doc: 'Hydraulic Unit v3', loc: 'Tab 5.2', text: 'Max pressure drop across the filter: 0.8 bar.' },
      c5: { doc: 'Safety Proc. v9', loc: '§2.1', text: 'Lock out and tag out the pump before opening the housing.' },
      c6: { doc: 'HR Handbook 2026', loc: '§4.3', text: 'Paid parental leave applies to permanent and fixed-term employees.' },
      c7: { doc: 'Pricing 2026', loc: '§1.0', text: 'Pump service contract list prices by region.', restricted: 'sales only' },
      c8: { doc: 'Warranty Terms v3', loc: '§2.1', text: 'Warranty: 24 months from the installation date.' },
      c9: { doc: 'Warranty Terms v3', loc: '§2.4', text: 'Claims need the purchase invoice and signed installation sheet.' },
      c10: { doc: 'Gearbox Manual v2', loc: '§5.1', text: 'Gearbox oil ISO VG 220; change every 4,000 hours.' },
      c11: { doc: 'HR Handbook 2026', loc: '§6.1', text: 'Remote work requests are approved by line managers.' },
      c12: { doc: 'Pump Manual rev.4', loc: '§9.1', text: 'All torque values assume lubricated threads.' }
    };
    const QS = [
      {
        q: 'What torque for the M12 pump housing bolts?',
        hits: [['c1', 0.82, 0.94], ['c2', 0.71, 0.88], ['c12', 0.66, 0.81], ['c7', 0.58, 0.77], ['c5', 0.44, 0.69]],
        ctx: ['c1', 'c2', 'c12'], status: 'ok', label: 'ANSWERED', tokens: 1284,
        answer: 'Tighten to 60 N·m in a star pattern, in two passes [1]. Re-torque after the first heat cycle [2] — the values assume lubricated threads [3].'
      },
      {
        q: 'How often do we replace the hydraulic filter?',
        hits: [['c3', 0.88, 0.92], ['c4', 0.61, 0.85], ['c10', 0.22, 0.54], ['c5', 0.12, 0.41]],
        ctx: ['c3', 'c4'], status: 'ok', label: 'ANSWERED', tokens: 986,
        answer: 'Every 500 operating hours [1] — or sooner if the pressure drop across the filter exceeds 0.8 bar [2].'
      },
      {
        q: 'Do contractors get paid parental leave?',
        hits: [['c6', 0.52, 0.74], ['c11', 0.18, 0.47]],
        ctx: ['c6'], status: 'warn', label: 'INSUFFICIENT EVIDENCE', tokens: 742,
        answer: 'The approved documents only cover parental leave for employees [1]. Nothing covers contractors, so I won’t guess — please check with HR.'
      }
    ];

    // Persian text for the same passages and questions; ids, scores and citations stay identical.
    const chunk = (id) => (isFa() && FA.sim.chunks[id] ? FA.sim.chunks[id] : CHUNKS[id]);
    const question = (i) => (isFa() && FA.sim.questions[i] ? { ...QS[i], ...FA.sim.questions[i] } : QS[i]);

    const kb = $('#kb'), emb = $('#emb'), embVec = $('#embVec'), qEl = $('#simQuery'), ctxEl = $('#ctx');
    const ans = $('#simAns'), tokBar = $('#tokBar'), tokNote = $('#tokNote'), runBtn = $('#simRun');
    const trk = $$('.trk', root), presets = $$('.chip-btn', root);
    const ids = Object.keys(CHUNKS);
    const buildKb = () => {
      kb.innerHTML = ids.map((id) => {
        const c = chunk(id);
        return `<div class="tile" data-id="${id}"><span class="rank"></span>` +
          `<span class="t-doc">${c.doc} · ${c.loc}${c.restricted ? ` · <em>${c.restricted}</em>` : ''}</span>` +
          `<span class="t-txt">${c.text}</span>` +
          `<span class="t-score"><span class="bar lex"><i></i></span><span class="bar sem"><i></i></span><span class="t-hyb"></span></span>` +
          `<span class="deny">${T('denied', 'ACCESS<br>DENIED')}</span></div>`;
      }).join('');
      $('#kbNote').textContent = `${digits(ids.length)} ${T('passages', 'passages')} · ${digits(new Set(ids.map((i) => CHUNKS[i].doc)).size)} ${T('docs', 'docs')}`;
    };
    buildKb();
    emb.innerHTML = '<i></i>'.repeat(64);
    const cells = $$('i', emb);
    const tile = (cid) => $(`.tile[data-id="${cid}"]`, kb);

    const seeded = (seed) => () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const vecFor = (qi) => { const r = seeded(qi * 7919 + 13); return cells.map(() => r() * 2 - 1); };
    const paint = (v) => v.forEach((x, i) => {
      cells[i].style.background = x >= 0
        ? `rgba(25,255,176,${(0.1 + x * 0.8).toFixed(2)})`
        : `rgba(255,61,129,${(0.1 - x * 0.7).toFixed(2)})`;
    });

    let run = 0, cur = 0, userTouched = false, inView = false, started = false, autoTimer = null;
    const sleep = (ms, id) => new Promise((res) => setTimeout(() => { if (id === run) res(); }, reduce ? 0 : ms));

    const setStage = (n, dur) => trk.forEach((t, i) => {
      t.classList.toggle('done', i < n);
      t.classList.toggle('active', i === n);
      if (i === n) t.style.setProperty('--dur', dur + 'ms');
    });
    const addBlock = (kind, htmlText, n) => {
      const d = document.createElement('div');
      d.className = 'cb ' + kind;
      if (n) d.dataset.n = n;
      d.innerHTML = htmlText; // static, trusted copy defined above
      ctxEl.appendChild(d);
    };
    const tokText = (n) => {
      const loc = isFa() ? 'fa-IR' : 'en-US';
      return `${n.toLocaleString(loc)} / ${(8192).toLocaleString(loc)} ${T('tokens', 'tokens')}`;
    };
    const tokens = (to, id) => (async () => {
      for (let k = 1; k <= 20; k++) {
        tokNote.textContent = tokText(Math.round((to * k) / 20));
        await sleep(30, id);
      }
    })();

    function reset(qi) {
      presets.forEach((b, i) => b.classList.toggle('active', i === qi));
      trk.forEach((t) => t.classList.remove('active', 'done'));
      $$('.tile', kb).forEach((t) => {
        t.className = 'tile';
        $('.rank', t).textContent = '';
        $$('.bar i', t).forEach((b) => { b.style.width = '0'; });
        $('.t-hyb', t).textContent = '';
      });
      ctxEl.innerHTML = '';
      ans.innerHTML = `<span class="sim-idle">${T('idle', 'Waiting for pipeline…')}</span>`;
      tokBar.style.width = '0';
      tokNote.textContent = tokText(0);
      cells.forEach((c) => { c.style.background = ''; });
      embVec.textContent = '[ … ]';
      qEl.textContent = question(qi).q;
    }

    async function go(qi) {
      const id = ++run;
      started = true;
      clearTimeout(autoTimer);
      cur = qi;
      reset(qi);
      const Q = question(qi);
      $('span', runBtn).textContent = T('replay', '↻ Replay');

      // 01 — embed the question
      setStage(0, 1500);
      qEl.textContent = '';
      for (const ch of Q.q) { qEl.textContent += ch; await sleep(14, id); }
      for (let k = 0; k < 8; k++) { paint(cells.map(() => Math.random() * 2 - 1)); await sleep(70, id); }
      const v = vecFor(qi);
      paint(v);
      embVec.textContent = '[ ' + v.slice(0, 4).map((x) => x.toFixed(3)).join(', ') + ', … ] · 384-d';
      await sleep(350, id);

      // 02 — hybrid retrieval
      setStage(1, 2000);
      kb.style.setProperty('--kbh', kb.offsetHeight + 'px');
      kb.classList.remove('scan');
      void kb.offsetWidth;
      kb.classList.add('scan');
      await sleep(900, id);
      const ranked = Q.hits.map(([cid, lex, sem]) => ({ cid, lex, sem, hyb: lex * 0.4 + sem * 0.6 })).sort((a, b) => b.hyb - a.hyb);
      for (let r = 0; r < ranked.length; r++) {
        const h = ranked[r], t = tile(h.cid);
        t.classList.add('hit');
        $('.rank', t).textContent = '#' + digits(r + 1);
        const [lx, sm] = $$('.bar i', t);
        lx.style.width = h.lex * 100 + '%';
        sm.style.width = h.sem * 100 + '%';
        $('.t-hyb', t).textContent = T('hybrid', 'hybrid') + ' ' + dec(h.hyb, 2);
        await sleep(180, id);
      }
      $$('.tile:not(.hit)', kb).forEach((t) => t.classList.add('miss'));
      await sleep(500, id);

      // 03 — access control
      setStage(2, 1100);
      const denied = ranked.filter((h) => CHUNKS[h.cid].restricted);
      for (const h of denied) { tile(h.cid).classList.add('denied'); await sleep(320, id); }
      if (!denied.length) await sleep(320, id);
      Q.ctx.forEach((cid) => tile(cid).classList.add('ctx-on'));
      ranked.filter((h) => !Q.ctx.includes(h.cid) && !CHUNKS[h.cid].restricted).forEach((h) => tile(h.cid).classList.add('miss'));
      await sleep(700, id);

      // 04 — augment the prompt
      setStage(3, 1600);
      addBlock('sys', `<b>${T('system', 'SYSTEM')}</b>${T('systemText', 'Answer only from the passages below. Cite each claim. If they don’t cover it, say so.')}`);
      await sleep(260, id);
      for (let n = 0; n < Q.ctx.length; n++) {
        const c = chunk(Q.ctx[n]);
        addBlock('psg', `<b>[${digits(n + 1)}]</b>${c.doc} ${c.loc} — ${c.text}`, String(n + 1));
        await sleep(260, id);
      }
      addBlock('q', `<b>${T('question', 'QUESTION')}</b>${Q.q}`);
      tokBar.style.width = ((Q.tokens / 8192) * 100).toFixed(1) + '%';
      tokens(Q.tokens, id);
      await sleep(700, id);

      // 05 — grounded generation
      setStage(4, 2200);
      const label = Q.status === 'ok' ? T('answered', Q.label) : T('insufficient', Q.label);
      ans.innerHTML = `<span class="status ${Q.status}">${label}</span><div class="sim-text"></div>`;
      const out = $('.sim-text', ans);
      for (const part of Q.answer.split(/(\[\d\])/)) {
        const m = part.match(/^\[(\d)\]$/);
        if (m) {
          const c = document.createElement('span');
          c.className = 'cite pop';
          c.textContent = digits(m[1]);
          c.dataset.n = m[1];
          out.appendChild(c);
          await sleep(140, id);
          continue;
        }
        for (const w of part.split(/(\s+)/)) {
          if (!w) continue;
          out.appendChild(document.createTextNode(w));
          if (w.trim()) await sleep(40, id);
        }
      }
      trk.forEach((t) => { t.classList.remove('active'); t.classList.add('done'); });
      if (!userTouched) {
        autoTimer = setTimeout(() => { if (inView && !userTouched && id === run) go((qi + 1) % QS.length); }, 6500);
      }
    }

    const highlight = (n) => {
      $$('.cb', ctxEl).forEach((b) => b.classList.toggle('glow', !!n && b.dataset.n === n));
      const cid = n ? QS[cur].ctx[Number(n) - 1] : null;
      $$('.tile', kb).forEach((t) => t.classList.toggle('glow', t.dataset.id === cid));
    };
    ans.addEventListener('pointerover', (e) => { const c = e.target.closest('.cite'); highlight(c ? c.dataset.n : null); });
    ans.addEventListener('pointerleave', () => highlight(null));

    presets.forEach((b, i) => b.addEventListener('click', () => { userTouched = true; go(i); }));
    runBtn.addEventListener('click', () => { userTouched = true; go(cur); });
    const idle = () => { $('span', runBtn).textContent = T('run', '▶ Run pipeline'); reset(cur); };
    idle();
    onView(root, (v) => {
      inView = v;
      if (v && !started) go(0);
    }, { threshold: 0.25 });
    onLang(() => {
      run++;
      clearTimeout(autoTimer);
      buildKb();
      if (started) go(cur); else idle();
    });
  }

  /* ---------- 05 Perimeter switch ---------- */
  function perimeter() {
    const root = $('#perim');
    if (!root) return;
    const btns = $$('.switch button', root);
    const state = $('#perimState');
    let touched = false;
    const stateText = (mode) => (mode === 'cloud'
      ? T('perimCloud', 'uplink: open · documents leaving your network')
      : T('perimLocal', 'uplink: none · perimeter sealed'));
    const readout = (b, mode) => (isFa() && b.dataset[mode + 'Fa']) || b.dataset[mode];
    const set = (mode) => {
      if (root.dataset.mode === mode) return;
      root.dataset.mode = mode;
      btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
      scramble(state, stateText(mode), 500);
      $$('[data-local]', root).forEach((b) => scramble(b, readout(b, mode), 450));
    };
    const paint = () => {
      const mode = root.dataset.mode;
      setText(state, stateText(mode));
      $$('[data-local]', root).forEach((b) => setText(b, readout(b, mode)));
    };
    paint();
    onLang(paint);
    btns.forEach((b) => b.addEventListener('click', () => { touched = true; set(b.dataset.mode); }));
    // Demonstrate the switch once when it first comes into view.
    let demoed = false;
    onView(root, (v) => {
      if (!v || demoed || reduce) return;
      demoed = true;
      setTimeout(() => { if (!touched) set('cloud'); }, 1400);
      setTimeout(() => { if (!touched) set('local'); }, 5200);
    }, { threshold: 0.45 });
  }

  /* ---------- Kinetic band (speed + skew follow scroll velocity) ---------- */
  function kinetic() {
    const track = $('#kinTrack');
    if (!track || reduce) return;
    let x = 0, v = 0, lastY = window.scrollY, dir = -1, running = false, half = 0;
    const measure = () => { half = track.scrollWidth / 2; };
    measure();
    window.addEventListener('resize', measure);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
    window.addEventListener('scroll', () => {
      const y = window.scrollY;
      v = clamp(v + (y - lastY) * 0.25, -40, 40);
      if (y !== lastY) dir = y > lastY ? -1 : 1;
      lastY = y;
    }, { passive: true });
    const loop = () => {
      if (!running) return;
      x += dir * (1.1 + Math.abs(v) * 0.6);
      if (half) { if (x <= -half) x += half; if (x > 0) x -= half; }
      v *= 0.9;
      track.style.transform = `translate3d(${x}px, 0, 0) skewX(${clamp(-v * 0.5, -14, 14)}deg)`;
      requestAnimationFrame(loop);
    };
    onView(track.parentElement, (on) => {
      if (on && !running) { running = true; requestAnimationFrame(loop); }
      else if (!on) running = false;
    });
  }

  /* ---------- Contact placeholders ---------- */
  function contactInfo() {
    const contact = cfg.contact || {};
    const clean = (v) => String(v || '').replace(/^\s*\[|\]\s*$/g, '').trim();
    $$('[data-contact]').forEach((el) => { const v = contact[el.dataset.contact]; if (v) el.textContent = v; });
    $$('[data-contact-href]').forEach((a) => {
      const key = a.dataset.contactHref;
      const v = clean(contact[key]);
      if (!v) return;
      if (key === 'email') a.href = 'mailto:' + v + '?subject=' + encodeURIComponent('Soshyant Expert demo');
      else if (key === 'phone') a.href = 'tel:' + v.replace(/[^\d+]/g, '');
      else a.href = /^https?:\/\//i.test(v) ? v : 'https://' + v;
    });
    const avatar = $('#avatar');
    const initials = clean(contact.name).split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('');
    if (avatar && initials) avatar.textContent = initials.toUpperCase();
    $$('.copy').forEach((b) => b.addEventListener('click', async () => {
      const v = clean(contact[b.dataset.copy]);
      if (!v) return;
      try { await navigator.clipboard.writeText(v); b.textContent = T('copied', 'copied'); } catch (e) { b.textContent = T('failed', 'failed'); }
      b.classList.add('ok');
      setTimeout(() => { b.textContent = T('copy', 'copy'); b.classList.remove('ok'); }, 1600);
    }));
  }

  /* ---------- Google Calendar booking ---------- */
  function booking() {
    const raw = String(cfg.bookingUrl || '').trim();
    calendarMock();
    if (!raw) return;
    let url;
    try { url = new URL(raw); } catch (e) { console.warn('[Soshyant] bookingUrl is not a valid URL:', raw); return; }

    const publicUrl = new URL(url.href);
    publicUrl.searchParams.delete('gv');
    const openLink = $('#calOpen');
    openLink.href = publicUrl.href;
    openLink.hidden = false;

    if (url.hostname === 'calendar.google.com' && /\/appointments\//.test(url.pathname)) {
      url.searchParams.set('gv', 'true');
      const frame = document.createElement('iframe');
      frame.src = url.href;
      frame.title = T('calFrame', 'Book a Soshyant Expert demo (Google Calendar)');
      frame.loading = 'lazy';
      $('#calEmbed').appendChild(frame);
      $('#calEmbed').hidden = false;
      $('#calPlaceholder').hidden = true;
    } else {
      // Short share links (calendar.app.google/…) can't be framed — offer a button instead.
      $('#calUnset').hidden = true;
      $('#calExternal').hidden = false;
      $('#calExternalBtn').href = url.href;
    }
  }

  function calendarMock() {
    const grid = $('#calGrid');
    if (!grid) return;
    const draw = () => {
      // Persian: Persian month names and digits on the same (Gregorian) calendar the booking page uses.
      const locale = isFa() ? 'fa-IR-u-ca-gregory' : undefined;
      const today = new Date();
      const first = new Date(today.getFullYear(), today.getMonth(), 1);
      const days = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
      $('#calMonth').textContent = first.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
      grid.textContent = '';
      const frag = document.createDocumentFragment();
      T('weekdays', ['M', 'T', 'W', 'T', 'F', 'S', 'S']).forEach((d) => {
        const s = document.createElement('span'); s.className = 'dow'; s.textContent = d; frag.appendChild(s);
      });
      for (let i = 0; i < (first.getDay() + 6) % 7; i++) frag.appendChild(document.createElement('span'));
      let selected = null;
      for (let d = 1; d <= days; d++) {
        const date = new Date(today.getFullYear(), today.getMonth(), d);
        const s = document.createElement('span');
        s.className = 'd';
        s.textContent = digits(d);
        if (d > today.getDate() && date.getDay() % 6 !== 0 && d % 4 !== 1) {
          s.classList.add('av');
          if (!selected) { selected = date; s.classList.add('sel'); }
        }
        frag.appendChild(s);
      }
      grid.appendChild(frag);
      $('#calDay').textContent = selected
        ? selected.toLocaleDateString(locale, { weekday: 'short', month: 'short', day: 'numeric' })
        : T('available', 'Available');
    };
    draw();
    onLang(draw);
  }

  /* ---------- Footer word: SOSHYANT ↔ سوشیانت ---------- */
  function footWord() {
    const el = $('#footWord');
    if (!el || reduce) return;
    setInterval(() => {
      el.classList.add('swap');
      el.classList.toggle('fa');
      setTimeout(() => el.classList.remove('swap'), 420);
    }, 3600);
  }

  /* ---------- Init ---------- */
  i18n();
  const year = $('#year');
  const setYear = () => { if (year) year.textContent = digits(new Date().getFullYear()); };
  setYear();
  onLang(setYear);
  onLang(countDigits);
  nav();
  cursor();
  magnetic();
  tilt();
  contactInfo();
  booking();
  vectorField();
  consoleDemo();
  ragSim();
  perimeter();
  kinetic();
  footWord();
  boot().then(reveal);
})();
