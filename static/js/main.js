document.addEventListener("DOMContentLoaded", () => {
  const header = document.getElementById("siteHeader");
  const menu = document.getElementById("menuToggle");
  const nav = document.getElementById("navLinks");

  window.addEventListener("scroll", () => {
    if (header) header.classList.toggle("scrolled", window.scrollY > 20);
  });

  if (menu && nav) {
    menu.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      menu.setAttribute("aria-expanded", open);
    });
    nav.querySelectorAll("a").forEach(a => a.addEventListener("click", () => nav.classList.remove("open")));
  }

  const reveal = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        reveal.unobserve(entry.target);
      }
    });
  }, {threshold: .12});

  document.querySelectorAll(".reveal").forEach(el => reveal.observe(el));

  document.querySelectorAll(".tilt-card").forEach(card => {
    card.addEventListener("pointermove", e => {
      if (window.innerWidth < 800) return;
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5;
      const y = (e.clientY - r.top) / r.height - .5;
      card.style.transform = `perspective(900px) rotateX(${(-y * 5).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateY(-3px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  });
});


// Privacy-friendly public-site interaction analytics. Contact details are never
// read from the browser by this script; they are collected only when the visitor
// voluntarily submits the contact form.
(() => {
  const send = (event_type, target, metadata = {}) => {
    try {
      const body = JSON.stringify({event_type, target, metadata});
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/analytics/event', new Blob([body], {type: 'application/json'}));
      } else {
        fetch('/analytics/event', {method:'POST', headers:{'Content-Type':'application/json'}, body, keepalive:true}).catch(()=>{});
      }
    } catch (_) {}
  };

  document.addEventListener('click', (e) => {
    const link = e.target.closest('a');
    if (!link) return;
    const href = link.getAttribute('href') || '';
    const text = (link.textContent || '').trim().replace(/\s+/g, ' ').slice(0,120);
    if (href.includes('wa.me')) send('whatsapp_click', href.split('?')[0], {text});
    else if (href.includes('mailto:')) send('email_click', href, {text});
    else if (href.startsWith('/project/')) send('project_click', href, {text});
    else if (href.startsWith('/portfolio/')) send('portfolio_click', href, {text});
    else if (href.startsWith('#')) send('section_click', href, {text});
    else if (link.target === '_blank') send('external_click', href, {text});
  }, {passive:true});

  document.querySelectorAll('form').forEach(form => {
    if (form.action.includes('/contact')) {
      form.addEventListener('submit', () => send('contact_form_start', 'contact-form'));
    }
  });
})();
