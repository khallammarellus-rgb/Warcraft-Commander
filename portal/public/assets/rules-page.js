/** Rules reference — horizontal slide deck (hosted PNGs from PDF export) */

async function initRulesPage() {
  const track = document.getElementById('rules-slides-track');
  const viewport = document.getElementById('rules-slides-viewport');
  const counter = document.getElementById('rules-slide-counter');
  const sourceLink = document.getElementById('rules-source-link');
  if (!track || !viewport) return;

  let config = { slides: [] };
  try {
    const res = await fetch('/data/rules-slides.json');
    if (res.ok) config = await res.json();
  } catch (_) {}

  const slides = config.slides || [];
  if (sourceLink && config.source_url) sourceLink.href = config.source_url;

  track.innerHTML = '';
  slides.forEach((slide, i) => {
    const article = document.createElement('article');
    article.className = 'rules-slide';
    article.dataset.index = String(i);
    const label = document.createElement('p');
    label.className = 'rules-slide-label';
    label.textContent = slide.title ? `${i + 1}. ${slide.title}` : `Slide ${i + 1}`;
    const img = document.createElement('img');
    img.src = slide.file;
    img.alt = slide.title || `Rules slide ${i + 1}`;
    img.loading = i < 2 ? 'eager' : 'lazy';
    img.decoding = 'async';
    article.appendChild(label);
    article.appendChild(img);
    track.appendChild(article);
  });

  const panels = [...track.querySelectorAll('.rules-slide')];
  let active = 0;

  function updateCounter() {
    if (!counter) return;
    const title = slides[active]?.title;
    counter.textContent = title
      ? `Slide ${active + 1} of ${panels.length} — ${title}`
      : `Slide ${active + 1} of ${panels.length}`;
  }

  function scrollToSlide(idx) {
    active = Math.max(0, Math.min(panels.length - 1, idx));
    panels[active]?.scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' });
    updateCounter();
  }

  viewport.addEventListener('scroll', () => {
    const left = viewport.scrollLeft;
    const width = panels[0]?.offsetWidth || 1;
    const gap = 16;
    active = Math.max(0, Math.min(panels.length - 1, Math.round(left / (width + gap))));
    updateCounter();
  }, { passive: true });

  document.getElementById('rules-prev')?.addEventListener('click', () => scrollToSlide(active - 1));
  document.getElementById('rules-next')?.addEventListener('click', () => scrollToSlide(active + 1));

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowLeft') scrollToSlide(active - 1);
    if (ev.key === 'ArrowRight') scrollToSlide(active + 1);
  });

  updateCounter();
}

document.addEventListener('DOMContentLoaded', initRulesPage);