/* markitdown-web front-end: batch upload, preview and download. */
(function () {
  "use strict";

  var MAX_FILES_FALLBACK = 20;
  var MAX_FILE_BYTES_FALLBACK = 50 * 1024 * 1024;

  var state = {
    entries: [],
    nextId: 1,
    selectedId: null,
    busy: false,
    limits: {
      max_files: MAX_FILES_FALLBACK,
      max_file_bytes: MAX_FILE_BYTES_FALLBACK
    }
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function t(key, vars) {
    return window.I18N.t(key, vars);
  }

  function formatBytes(bytes) {
    if (!bytes) {
      return "0 B";
    }
    var units = ["B", "KB", "MB", "GB"];
    var index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    var value = bytes / Math.pow(1024, index);
    var digits = index === 0 ? 0 : value < 10 ? 1 : 0;
    return value.toFixed(digits) + " " + units[index];
  }

  function saveBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function setStatus(text) {
    els.status.textContent = text || "";
  }

  function errorMessage(entry) {
    var type = entry.result && entry.result.error_type;
    var key = type ? "error_" + type : "error_http";
    var base = t(key);
    var detail = entry.result && entry.result.error;
    if (detail && detail !== base) {
      base += " " + (detail.length > 220 ? detail.slice(0, 220) + "…" : detail);
    }
    return base;
  }

  /* ---------------- rendering ---------------- */

  function render() {
    els.fileList.textContent = "";
    state.entries.forEach(function (entry) {
      els.fileList.appendChild(renderRow(entry));
    });
    els.emptyNote.hidden = state.entries.length > 0;
    els.clearBtn.disabled = state.busy || state.entries.length === 0;
    els.convertBtn.disabled = state.busy || state.entries.length === 0;
    els.convertBtn.textContent = state.busy ? t("convertRunning") : t("convert");

    var okCount = state.entries.filter(function (e) {
      return e.status === "ok";
    }).length;
    els.zipBtn.disabled = state.busy || okCount === 0;
    renderLimits();
    renderPreview();
  }

  function renderLimits() {
    els.limitsHint.textContent = t("limits", {
      files: state.limits.max_files,
      size: formatBytes(state.limits.max_file_bytes)
    });
  }

  function renderRow(entry) {
    var li = document.createElement("li");
    li.className = "file-row status-" + entry.status;
    if (entry.id === state.selectedId) {
      li.classList.add("selected");
    }

    var main = document.createElement("button");
    main.type = "button";
    main.className = "file-main";
    main.addEventListener("click", function () {
      state.selectedId = entry.id;
      render();
    });

    var name = document.createElement("span");
    name.className = "file-name";
    name.textContent = entry.name;
    name.title = entry.name;

    var meta = document.createElement("span");
    meta.className = "file-meta";
    var bits = [formatBytes(entry.size)];
    if (entry.status === "ok" && entry.result) {
      bits.push(entry.result.output_name);
      if (entry.result.truncated) {
        bits.push(t("truncated"));
      }
    } else if (entry.status === "error") {
      bits.push(errorMessage(entry));
    } else if (entry.status === "converting") {
      bits.push(t("convertRunning"));
    }
    meta.textContent = bits.join(" · ");

    main.appendChild(name);
    main.appendChild(meta);

    var badge = document.createElement("span");
    badge.className = "badge badge-" + entry.status;
    badge.textContent = entry.status;

    var actions = document.createElement("span");
    actions.className = "row-actions";

    if (entry.status === "ok") {
      var dl = document.createElement("button");
      dl.type = "button";
      dl.className = "btn btn-sm";
      dl.textContent = "↓ .md";
      dl.title = t("download");
      dl.addEventListener("click", function (event) {
        event.stopPropagation();
        downloadEntry(entry);
      });
      actions.appendChild(dl);
    }

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-sm btn-ghost";
    remove.textContent = "×";
    remove.title = t("remove");
    remove.disabled = state.busy;
    remove.addEventListener("click", function (event) {
      event.stopPropagation();
      removeEntry(entry.id);
    });
    actions.appendChild(remove);

    li.appendChild(main);
    li.appendChild(badge);
    li.appendChild(actions);
    return li;
  }

  function renderPreview() {
    var entry = findEntry(state.selectedId);
    var hasMarkdown = !!(entry && entry.status === "ok" && entry.result);
    els.copyBtn.disabled = !hasMarkdown;
    els.downloadBtn.disabled = !hasMarkdown;

    els.previewBody.textContent = "";
    if (hasMarkdown) {
      els.previewBody.textContent = entry.result.markdown;
    } else {
      var span = document.createElement("span");
      span.className = "placeholder";
      span.textContent = t("previewPlaceholder");
      els.previewBody.appendChild(span);
    }
  }

  function findEntry(id) {
    for (var i = 0; i < state.entries.length; i += 1) {
      if (state.entries[i].id === id) {
        return state.entries[i];
      }
    }
    return null;
  }

  /* ---------------- file handling ---------------- */

  function addFiles(fileList) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (incoming.length === 0) {
      return;
    }
    var room = state.limits.max_files - state.entries.length;
    if (incoming.length > room) {
      incoming = incoming.slice(0, Math.max(room, 0));
      setStatus(t("statusTooMany", { max: state.limits.max_files }));
    }
    incoming.forEach(function (file) {
      state.entries.push({
        id: state.nextId++,
        file: file,
        name: file.name,
        size: file.size,
        status: "pending",
        result: null
      });
    });
    render();
  }

  function removeEntry(id) {
    state.entries = state.entries.filter(function (entry) {
      return entry.id !== id;
    });
    if (state.selectedId === id) {
      state.selectedId = null;
    }
    render();
  }

  function clearAll() {
    state.entries = [];
    state.selectedId = null;
    setStatus(t("statusCleared"));
    render();
  }

  function downloadEntry(entry) {
    if (!entry || !entry.result) {
      return;
    }
    saveBlob(
      new Blob([entry.result.markdown], { type: "text/markdown;charset=utf-8" }),
      entry.result.output_name
    );
  }

  /* ---------------- conversion ---------------- */

  function convertAll() {
    if (state.busy || state.entries.length === 0) {
      return;
    }
    var formData = new FormData();
    state.entries.forEach(function (entry) {
      formData.append("files", entry.file, entry.name);
    });

    state.busy = true;
    state.entries.forEach(function (entry) {
      entry.status = "converting";
      entry.result = null;
    });
    setStatus(t("statusConverting", { count: state.entries.length }));
    render();

    fetch("/api/convert", { method: "POST", body: formData })
      .then(function (response) {
        return response.json().then(function (payload) {
          if (!response.ok) {
            throw new Error(payload.detail || t("error_http"));
          }
          return payload;
        });
      })
      .then(function (payload) {
        applyResults(payload.results || []);
        var summary = payload.summary || {};
        setStatus(
          t("statusSummary", {
            ok: summary.succeeded || 0,
            failed: summary.failed || 0
          })
        );
      })
      .catch(function (error) {
        state.entries.forEach(function (entry) {
          if (entry.status === "converting" || entry.status === "pending") {
            entry.status = "error";
            entry.result = { error: String(error.message || error), error_type: null };
          }
        });
        setStatus(t("error_network"));
      })
      .then(function () {
        state.busy = false;
        render();
      });
  }

  function applyResults(results) {
    for (var i = 0; i < state.entries.length; i += 1) {
      var payload = results[i];
      if (!payload) {
        continue;
      }
      var entry = state.entries[i];
      entry.status = payload.ok ? "ok" : "error";
      entry.result = payload;
    }
    if (state.selectedId === null) {
      var firstOk = state.entries.filter(function (entry) {
        return entry.status === "ok";
      })[0];
      if (firstOk) {
        state.selectedId = firstOk.id;
      }
    }
  }

  function downloadZip() {
    if (state.busy) {
      return;
    }
    var payload = {
      files: state.entries
        .filter(function (entry) {
          return entry.status === "ok" && entry.result;
        })
        .map(function (entry) {
          return {
            filename: entry.result.output_name,
            markdown: entry.result.markdown
          };
        })
    };
    if (payload.files.length === 0) {
      return;
    }

    state.busy = true;
    setStatus(t("statusZipBuilding"));
    render();

    fetch("/api/zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.detail || t("error_http"));
          });
        }
        return response.blob();
      })
      .then(function (blob) {
        saveBlob(blob, "markitdown-output.zip");
        setStatus("");
      })
      .catch(function (error) {
        setStatus(t("error_network") + " " + String(error.message || error));
      })
      .then(function () {
        state.busy = false;
        render();
      });
  }

  /* ---------------- wiring ---------------- */

  function copyPreview() {
    var entry = findEntry(state.selectedId);
    if (!entry || !entry.result) {
      return;
    }
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      setStatus(t("statusUnsupportedBrowser"));
      return;
    }
    navigator.clipboard.writeText(entry.result.markdown).then(
      function () {
        setStatus(t("copied"));
      },
      function () {
        setStatus(t("copyFailed"));
      }
    );
  }

  function bindEvents() {
    els.dropzone.addEventListener("click", function () {
      els.fileInput.click();
    });
    els.dropzone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        els.fileInput.click();
      }
    });
    els.fileInput.addEventListener("change", function () {
      addFiles(els.fileInput.files);
      els.fileInput.value = "";
    });

    ["dragenter", "dragover"].forEach(function (name) {
      els.dropzone.addEventListener(name, function (event) {
        event.preventDefault();
        els.dropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      els.dropzone.addEventListener(name, function (event) {
        event.preventDefault();
        els.dropzone.classList.remove("dragover");
      });
    });
    els.dropzone.addEventListener("drop", function (event) {
      addFiles(event.dataTransfer.files);
    });

    els.convertBtn.addEventListener("click", convertAll);
    els.zipBtn.addEventListener("click", downloadZip);
    els.clearBtn.addEventListener("click", clearAll);
    els.copyBtn.addEventListener("click", copyPreview);
    els.downloadBtn.addEventListener("click", function () {
      downloadEntry(findEntry(state.selectedId));
    });
    els.langToggle.addEventListener("click", function () {
      window.I18N.apply(window.I18N.lang() === "es" ? "en" : "es");
    });
    document.addEventListener("langchange", render);
  }

  function loadLimits() {
    fetch("/api/health")
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (data && data.limits) {
          state.limits = data.limits;
        }
        render();
      })
      .catch(function () {
        render();
      });
  }

  function init() {
    els = {
      dropzone: $("dropzone"),
      fileInput: $("file-input"),
      limitsHint: $("limits-hint"),
      fileList: $("file-list"),
      emptyNote: $("empty-note"),
      convertBtn: $("convert-btn"),
      zipBtn: $("zip-btn"),
      clearBtn: $("clear-btn"),
      status: $("status"),
      previewBody: $("preview-body"),
      copyBtn: $("copy-btn"),
      downloadBtn: $("download-btn"),
      langToggle: $("lang-toggle")
    };
    bindEvents();
    window.I18N.apply(window.I18N.detect());
    loadLimits();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
