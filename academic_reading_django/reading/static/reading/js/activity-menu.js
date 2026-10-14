/* Activity menu (phones/tablets). Opens the panel in the sticky bar under the
   masthead; closes on Escape (returning focus to the button), outside click, or
   choosing an activity (a normal page navigation). Also publishes the masthead's
   height as --masthead-h so the bar can stick directly beneath it. */
(function () {
  var bar = document.getElementById('activity-bar');
  if (!bar) return;
  var btn = bar.querySelector('.activity-menu-btn');
  var panel = document.getElementById('activity-menu-panel');
  var head = document.querySelector('.masthead');

  function setHeight() {
    if (head) document.documentElement.style.setProperty('--masthead-h', head.offsetHeight + 'px');
  }
  setHeight();
  window.addEventListener('resize', setHeight);
  if (head && window.ResizeObserver) new ResizeObserver(setHeight).observe(head);

  function set(open, returnFocus) {
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    panel.hidden = !open;
    if (!open && returnFocus) btn.focus();
  }
  btn.addEventListener('click', function () { set(panel.hidden); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !panel.hidden) set(false, true);
  });
  document.addEventListener('click', function (e) {
    if (!panel.hidden && !bar.contains(e.target)) set(false);
  });
  window.matchMedia('(min-width: 1024px)').addEventListener('change', function (e) {
    if (e.matches) set(false);
  });
})();
