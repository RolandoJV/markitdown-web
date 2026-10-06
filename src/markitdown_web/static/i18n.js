/* Bilingual strings for markitdown-web (Spanish / English). */
(function () {
  "use strict";

  var STRINGS = {
    es: {
      tagline: "Convierte documentos a Markdown desde el navegador",
      dropTitle: "Arrastra y suelta archivos aquí",
      dropHint: "o haz clic para seleccionar varios",
      limits: "Hasta {files} archivos · {size} por archivo",
      convert: "Convertir",
      convertRunning: "Convirtiendo…",
      downloadZip: "Descargar ZIP",
      clear: "Limpiar",
      empty: "Aún no hay archivos.",
      remove: "Quitar",
      previewTitle: "Vista previa",
      previewPlaceholder: "Selecciona un archivo convertido para ver su Markdown.",
      copy: "Copiar",
      copied: "Copiado",
      copyFailed: "No se pudo copiar",
      download: "Descargar .md",
      statusConverting: "Convirtiendo {count} archivo(s)…",
      statusSummary: "Convertidos: {ok} · Fallidos: {failed}",
      statusZipBuilding: "Preparando el ZIP…",
      statusCleared: "Lista vaciada.",
      statusTooMany: "Máximo {max} archivos por lote.",
      statusUnsupportedBrowser: "Tu navegador no soporta esta acción.",
      truncated: "Salida truncada por el límite del servidor.",
      error_missing_dependency: "Falta una dependencia opcional en el servidor.",
      error_unsupported_format: "Formato no reconocido por el conversor.",
      error_conversion_failed: "La conversión falló.",
      error_too_large: "El archivo supera el límite permitido.",
      error_empty_file: "El archivo está vacío.",
      error_internal: "Error interno del servidor.",
      error_network: "No se pudo contactar con el servidor.",
      error_http: "El servidor devolvió un error.",
      credits:
        'Interfaz web no oficial para <a href="https://github.com/microsoft/markitdown" target="_blank" rel="noopener noreferrer">MarkItDown</a> de Microsoft. El código de conversión es de Adam Fourney y Microsoft, licencia MIT.'
    },
    en: {
      tagline: "Convert documents to Markdown from your browser",
      dropTitle: "Drag and drop files here",
      dropHint: "or click to browse (multiple selection)",
      limits: "Up to {files} files · {size} per file",
      convert: "Convert",
      convertRunning: "Converting…",
      downloadZip: "Download ZIP",
      clear: "Clear",
      empty: "No files yet.",
      remove: "Remove",
      previewTitle: "Preview",
      previewPlaceholder: "Select a converted file to see its Markdown.",
      copy: "Copy",
      copied: "Copied",
      copyFailed: "Could not copy",
      download: "Download .md",
      statusConverting: "Converting {count} file(s)…",
      statusSummary: "Succeeded: {ok} · Failed: {failed}",
      statusZipBuilding: "Building the ZIP…",
      statusCleared: "List cleared.",
      statusTooMany: "At most {max} files per batch.",
      statusUnsupportedBrowser: "Your browser does not support this action.",
      truncated: "Output truncated by the server limit.",
      error_missing_dependency: "The server is missing an optional dependency.",
      error_unsupported_format: "The converter does not recognize this format.",
      error_conversion_failed: "The conversion failed.",
      error_too_large: "The file exceeds the allowed limit.",
      error_empty_file: "The file is empty.",
      error_internal: "Internal server error.",
      error_network: "Could not reach the server.",
      error_http: "The server returned an error.",
      credits:
        'Unofficial web UI for Microsoft\'s <a href="https://github.com/microsoft/markitdown" target="_blank" rel="noopener noreferrer">MarkItDown</a>. Conversion code by Adam Fourney and Microsoft, MIT License.'
    }
  };

  var STORAGE_KEY = "markitdown-web.lang";
  var current = "es";

  function detectLanguage() {
    var stored = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      stored = null;
    }
    if (stored === "es" || stored === "en") {
      return stored;
    }
    var nav = (navigator.language || "es").toLowerCase();
    return nav.indexOf("en") === 0 ? "en" : "es";
  }

  function t(key, vars) {
    var table = STRINGS[current] || STRINGS.es;
    var value = table[key];
    if (value === undefined) {
      value = STRINGS.es[key];
    }
    if (typeof value !== "string") {
      return key;
    }
    if (vars) {
      Object.keys(vars).forEach(function (name) {
        value = value.replace(new RegExp("\\{" + name + "\\}", "g"), vars[name]);
      });
    }
    return value;
  }

  function apply(lang) {
    current = STRINGS[lang] ? lang : "es";
    document.documentElement.lang = current;
    document.querySelectorAll("[data-i18n]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (node) {
      node.innerHTML = t(node.getAttribute("data-i18n-html"));
    });
    try {
      window.localStorage.setItem(STORAGE_KEY, current);
    } catch (err) {
      /* storage may be blocked; language simply resets next load */
    }
    var toggle = document.getElementById("lang-toggle");
    if (toggle) {
      toggle.textContent = current === "es" ? "EN" : "ES";
    }
    document.dispatchEvent(new CustomEvent("langchange", { detail: { lang: current } }));
  }

  window.I18N = {
    t: t,
    apply: apply,
    lang: function () {
      return current;
    },
    detect: detectLanguage
  };
})();
