(() => {
  function mountRuleTags() {
    const sidebar = document.querySelector(".md-sidebar--secondary .md-sidebar__inner");
    if (!sidebar || sidebar.querySelector(".rule-tag-panel")) return;

    const rules = [];
    const seen = new Set();
    document.querySelectorAll(".md-content .source-rule[id]").forEach((rule) => {
      const id = rule.id.toLowerCase();
      if (!/^[ieagrtlc]\d{3}$/.test(id) || seen.has(id)) return;
      seen.add(id);
      rules.push({ id, label: id.toUpperCase() });
    });
    if (!rules.length) return;

    const panel = document.createElement("nav");
    panel.className = "rule-tag-panel";
    panel.setAttribute("aria-label", "Rules on this page");

    const title = document.createElement("div");
    title.className = "rule-tag-title";
    title.textContent = `Rules on this page (${rules.length})`;
    panel.append(title);

    const list = document.createElement("div");
    list.className = "rule-tag-list";
    for (const rule of rules) {
      const link = document.createElement("a");
      link.className = "rule-tag";
      link.href = `#${rule.id}`;
      link.textContent = rule.label;
      list.append(link);
    }
    panel.append(list);
    sidebar.append(panel);

    const updateActiveTag = () => {
      const current = window.location.hash.toLowerCase();
      list.querySelectorAll("a").forEach((link) => {
        if (link.getAttribute("href") === current) {
          link.setAttribute("aria-current", "location");
        } else {
          link.removeAttribute("aria-current");
        }
      });
    };
    window.addEventListener("hashchange", updateActiveTag);
    updateActiveTag();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountRuleTags, { once: true });
  } else {
    mountRuleTags();
  }
})();
