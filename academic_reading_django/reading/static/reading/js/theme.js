/* Dark-mode switch. The head script in base.html has already set data-theme. */
(function () {
  var root = document.documentElement;
  var sw = document.getElementById('theme-switch');
  if (!sw) return;
  function sync() { sw.setAttribute('aria-checked', root.getAttribute('data-theme') === 'dark' ? 'true' : 'false'); }
  sync();
  sw.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('ar-theme', next); } catch (e) {}
    sync();
  });
  /* Follow the OS only while the reader has not made a choice. */
  try {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      var saved = null;
      try { saved = localStorage.getItem('ar-theme'); } catch (x) {}
      if (saved === 'light' || saved === 'dark') return;
      root.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      sync();
    });
  } catch (e) {}
})();
