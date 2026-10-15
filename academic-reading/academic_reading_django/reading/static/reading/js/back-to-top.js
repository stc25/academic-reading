/* Back-to-top button: appears after scrolling, returns to the top and moves focus
   to <main> so keyboard and screen-reader users land at the start of the content. */
(function () {
  var btn = document.getElementById('back-to-top');
  if (!btn) return;
  var THRESHOLD = 400, ticking = false;
  function update() {
    ticking = false;
    btn.classList.toggle('is-visible', window.scrollY > THRESHOLD);
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(update); }
  }, { passive: true });
  update();
  btn.addEventListener('click', function () {
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
    var main = document.getElementById('content');
    if (main) main.focus({ preventScroll: true });
  });
})();
