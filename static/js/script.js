// Light/Dark mode toggle
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.btn-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      document.body.classList.toggle('dark-mode');
    });
  }
});
