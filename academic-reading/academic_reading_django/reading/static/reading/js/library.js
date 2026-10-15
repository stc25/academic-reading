/* Library search + language filter (home page). Pure client-side: it hides cards
   whose text (title, author, topic, language) does not contain every typed word,
   and groups left with no cards. The bar ships `hidden` and is revealed here, so
   without JavaScript the page is simply the full library. */
(function () {
  var bar = document.getElementById('library-bar');
  var input = document.getElementById('library-search');
  var select = document.getElementById('library-language');
  var status = document.getElementById('library-status');
  var empty = document.getElementById('library-empty');
  var groups = Array.prototype.slice.call(document.querySelectorAll('.lang-group'));
  if (!bar || !input || !select || !groups.length) return;

  var data = groups.map(function (g) {
    var name = g.querySelector('h2').textContent.trim();
    var opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    select.appendChild(opt);
    return {
      el: g, name: name,
      cards: Array.prototype.slice.call(g.querySelectorAll('.text-card')).map(function (c) {
        return { el: c, hay: (name + ' ' + c.textContent).replace(/\s+/g, ' ').toLowerCase() };
      })
    };
  });
  bar.hidden = false;

  var wasFiltering = false;
  function apply() {
    var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    var lang = select.value, shown = 0;
    data.forEach(function (g) {
      var any = false;
      g.cards.forEach(function (c) {
        var ok = (!lang || lang === g.name) && words.every(function (w) { return c.hay.indexOf(w) !== -1; });
        c.el.hidden = !ok;
        if (ok) { any = true; shown++; }
      });
      g.el.hidden = !any;
    });
    var filtering = words.length > 0 || !!lang;
    empty.hidden = shown > 0;
    status.textContent = filtering ? shown + (shown === 1 ? ' text' : ' texts') + ' shown' : '';
    if (filtering && !wasFiltering) {
      var h = document.getElementById('library');
      if (h) h.scrollIntoView({ block: 'start' });
    }
    wasFiltering = filtering;
  }
  input.addEventListener('input', apply);
  select.addEventListener('change', apply);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && input.value) { input.value = ''; apply(); }
  });
})();
