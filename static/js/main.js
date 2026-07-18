/* ==========================================================================
   CIFAKE — shared front-end behaviour
   1) Dark / light theme toggle (persisted in localStorage)
   2) Scroll-reveal animation for .reveal elements
   3) Drag-and-drop upload widget with preview + submit spinner
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initScrollReveal();
  initUploadWidget();
  animateProbabilityBars();
});

/* ------------------------------ Theme toggle ------------------------------ */
function initThemeToggle() {
  const root = document.documentElement;
  const toggleBtn = document.getElementById("themeToggle");
  const stored = localStorage.getItem("cifake-theme");
  const initial = stored || "dark";
  root.setAttribute("data-theme", initial);
  updateToggleIcon(initial);

  if (!toggleBtn) return;
  toggleBtn.addEventListener("click", () => {
    const current = root.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("cifake-theme", next);
    updateToggleIcon(next);
  });
}

function updateToggleIcon(theme) {
  const toggleBtn = document.getElementById("themeToggle");
  if (!toggleBtn) return;
  toggleBtn.innerHTML =
    theme === "dark" ? '<i class="bi bi-sun-fill"></i>' : '<i class="bi bi-moon-stars-fill"></i>';
}

/* ------------------------------ Scroll reveal ------------------------------ */
function initScrollReveal() {
  const elements = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window) || elements.length === 0) {
    elements.forEach((el) => el.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  elements.forEach((el) => observer.observe(el));
}

/* ------------------------------ Upload widget ------------------------------ */
function initUploadWidget() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const form = document.getElementById("uploadForm");
  if (!dropzone || !fileInput || !form) return;

  const previewWrap = document.getElementById("previewWrap");
  const previewImg = document.getElementById("previewImg");
  const previewName = document.getElementById("previewName");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const spinner = document.getElementById("spinnerOverlay");
  const ALLOWED = ["image/jpeg", "image/jpg", "image/png"];

  const openPicker = () => fileInput.click();
  dropzone.addEventListener("click", openPicker);
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") openPicker();
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files && files.length) {
      fileInput.files = files;
      handleFile(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      handleFile(fileInput.files[0]);
    }
  });

  function handleFile(file) {
    if (!ALLOWED.includes(file.type)) {
      alert("Only JPG, JPEG, and PNG images are supported.");
      fileInput.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.src = e.target.result;
      previewName.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
      previewWrap.classList.add("active");
      analyzeBtn.disabled = false;
    };
    reader.readAsDataURL(file);
  }

  form.addEventListener("submit", () => {
    if (!fileInput.files || !fileInput.files[0]) return;
    analyzeBtn.disabled = true;
    analyzeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Analyzing…';
    if (spinner) spinner.classList.add("active");
  });
}

/* ------------------------------ Probability bars ------------------------------ */
function animateProbabilityBars() {
  document.querySelectorAll(".prob-fill[data-target]").forEach((bar) => {
    const target = bar.getAttribute("data-target");
    requestAnimationFrame(() => {
      bar.style.width = `${target}%`;
    });
  });
}
