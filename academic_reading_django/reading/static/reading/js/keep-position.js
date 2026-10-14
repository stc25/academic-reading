// Keep the reader in the work area on narrow screens.
//
// Below 1024px the page is one column: the whole reading text, then the
// activity list and work pane far below it. Choosing an activity, changing
// level/reply language, or finishing Generate / Check (which reload the page)
// would all land the reader back at the top, in the text. So the page they
// are leaving leaves a note in sessionStorage, and the page they arrive on
// scrolls the activity list back into view. Wide screens (two columns, both
// visible at once) are untouched. Everything is wrapped in try/catch because
// sessionStorage can be unavailable (private windows, blocked site data).
(function () {
  var KEY = "reading:keepWorkInView";
  var narrow = window.matchMedia("(max-width: 1023px)");

  function arm() {
    try {
      if (narrow.matches) sessionStorage.setItem(KEY, "1");
    } catch (e) {}
  }
  window.keepWorkInView = arm; // generate.js calls this just before it reloads

  document.addEventListener("click", function (event) {
    if (event.target.closest && event.target.closest(".activity-nav a")) arm();
  });
  document.addEventListener("change", function (event) {
    if (event.target.closest && event.target.closest(".level-reply-row")) arm();
  });

  var armed = false;
  try {
    armed = sessionStorage.getItem(KEY) === "1";
    sessionStorage.removeItem(KEY);
  } catch (e) {}
  if (!armed || !narrow.matches) return;

  // The browser may try to restore the old scroll offset after load; take over.
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  var target = document.querySelector(".activity-nav");
  if (!target) return;
  function show() {
    target.scrollIntoView({ block: "start" });
  }
  show();
  window.addEventListener("load", show);
})();
