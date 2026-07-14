function showToast(message, type, duration, position) {
    Toastify({
        text: message,
        duration: duration || 3000,
        close: true,
        className: type || "info",
        gravity: "top", // `top` or `bottom`
        position: position || "right", // `left`, `center` or `right`
        stopOnFocus: true, // Prevents dismissing of toast on hover
        style: {
          background: type,
        },
        onClick: function(){} // Callback after click
      }).showToast();
}

document.addEventListener("alpine:init", function () {
  Alpine.data("asynczShell", function () {
    const storageKey = "asyncz.dashboard.sidebarCollapsed";

    return {
      sidebarCollapsed: false,
      mobileMenuOpen: false,

      get sidebarExpanded() {
        return !this.sidebarCollapsed;
      },

      get sidebarToggleLabel() {
        return this.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar";
      },

      init() {
        try {
          this.sidebarCollapsed = window.localStorage.getItem(storageKey) === "true";
        } catch (_error) {
          this.sidebarCollapsed = false;
        }

        this.applySidebarState();
      },

      applySidebarState() {
        document.body.classList.toggle("az-sidebar-collapsed", this.sidebarCollapsed);
      },

      toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        this.applySidebarState();

        try {
          window.localStorage.setItem(storageKey, String(this.sidebarCollapsed));
        } catch (_error) {
          // Storage can be disabled in private browsing or strict test contexts.
        }
      },

      toggleMobileMenu() {
        this.mobileMenuOpen = !this.mobileMenuOpen;
      },

      closeMobileMenu() {
        this.mobileMenuOpen = false;
      },
    };
  });

  Alpine.data("asynczTasks", function () {
    return {
      selected: [],

      get selectedCount() {
        return this.selected.length;
      },

      get selectedLabel() {
        const count = this.selected.length;
        if (count === 1) return "1 selected";
        return `${count} selected`;
      },

      get selectedPayload() {
        return JSON.stringify(this.selected);
      },

      get noSelection() {
        return this.selected.length === 0;
      },

      init() {
        this.refreshSelection();
        document.body.addEventListener("htmx:afterSwap", (event) => {
          if (event.target && event.target.id === "tasks-table") {
            this.$nextTick(() => this.refreshSelection());
          }
        });
      },

      rowCheckboxes() {
        return Array.from(this.$root.querySelectorAll('input[name="row"]'));
      },

      refreshSelection() {
        const rows = this.rowCheckboxes();
        this.selected = rows.filter((checkbox) => checkbox.checked).map((checkbox) => checkbox.value);

        const selectAll = this.$root.querySelector("#select-all");
        if (selectAll) {
          selectAll.checked = rows.length > 0 && this.selected.length === rows.length;
          selectAll.indeterminate = this.selected.length > 0 && this.selected.length < rows.length;
        }
      },

      toggleAll(event) {
        const checked = event.target.checked;
        this.rowCheckboxes().forEach((checkbox) => {
          checkbox.checked = checked;
        });
        this.refreshSelection();
      },

      openAddTask() {
        const modal = document.getElementById("add-modal");
        if (modal) modal.showModal();
      },

      closeAddTask() {
        const modal = document.getElementById("add-modal");
        if (modal) modal.close();
      },

      confirmRemove(event) {
        const label = event.currentTarget.dataset.confirmLabel || "this task";
        if (!window.confirm(`Remove task ${label}?`)) {
          event.preventDefault();
        }
      },

      copyTask(event) {
        const taskId = event.currentTarget.dataset.taskId;
        if (!taskId || !navigator.clipboard) return;

        navigator.clipboard.writeText(taskId).then(() => {
          if (typeof showToast === "function") {
            showToast("Task id copied", "#172033", 1600);
          }
        });
      },
    };
  });
});

document.addEventListener("DOMContentLoaded", function () {
  const overlay = document.getElementById("loading-overlay");
  const showLoading = () => overlay && overlay.classList.remove("hidden");
  const hideLoading = () => overlay && overlay.classList.add("hidden");

  const inDialog = (el) => !!(el && el.closest && el.closest("dialog"));
  const hasHx = (el) => !!(el && (
    el.hasAttribute("hx-post") || el.hasAttribute("hx-get") ||
    el.hasAttribute("hx-put") || el.hasAttribute("hx-delete") ||
    el.hasAttribute("data-hx")
  ));

  document.querySelectorAll("form").forEach((form) => {
    const method = (form.getAttribute("method") || "").toLowerCase();
    form.addEventListener("submit", () => {
      if (method === "dialog") return;
      if (inDialog(form) && !hasHx(form)) return;
      if (form.getAttribute("target") === "_blank" || form.hasAttribute("data-no-loading")) {
        return;
      }
      showLoading();
    });
  });

  document.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", () => {
      const href = link.getAttribute("href") || "";
      if (link.hasAttribute("data-no-loading")) return;
      if (!href || href.startsWith("#")) return;
      if (link.hasAttribute("target")) return;
      if (inDialog(link)) return;
      showLoading();
    });
  });

  document.querySelectorAll("button[data-href]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.hasAttribute("data-no-loading")) return;
      if (inDialog(button)) return;
      const to = button.getAttribute("data-href");
      if (!to) return;
      showLoading();
      window.location.href = to;
    });
  });

  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("close", hideLoading);
    dialog.addEventListener("cancel", hideLoading);

    dialog.querySelectorAll("form[method='dialog'], button[data-close], [data-dialog-close]")
      .forEach((el) => {
        el.addEventListener("click", hideLoading);
      });
  });

  document.body.addEventListener("htmx:afterOnLoad", hideLoading);
  document.body.addEventListener("htmx:responseError", hideLoading);
  window.addEventListener("pageshow", hideLoading);
});
