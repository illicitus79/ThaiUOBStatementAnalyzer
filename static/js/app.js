// ── Global flash auto-dismiss ──
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => el.remove(), 5000);
});

// ── Animate KPI cards on load ──
function animateValue(el, start, end, duration, prefix, suffix) {
  if (!el) return;
  const range = end - start;
  let startTime = null;
  const step = (timestamp) => {
    if (!startTime) startTime = timestamp;
    const progress = Math.min((timestamp - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = prefix + (start + range * eased).toFixed(2) + suffix;
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ── Scroll reveal animation ──
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.glass-card, .credit-card, .kpi-card').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(20px)';
  el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  observer.observe(el);
});
