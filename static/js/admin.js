document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("adminMenu");
  const side = document.getElementById("adminSidebar");
  if (btn && side) btn.addEventListener("click", () => side.classList.toggle("open"));

  document.querySelectorAll("input[type=file]").forEach(input => {
    input.addEventListener("change", () => {
      const file = input.files[0];
      if (!file) return;
      if (file.size > 8 * 1024 * 1024) {
        alert("Image is larger than 8 MB.");
        input.value = "";
      }
    });
  });
});
