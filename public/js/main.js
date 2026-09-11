const header = document.querySelector("[data-header]");

const updateHeader = () => {
  header?.classList.toggle("is-scrolled", window.scrollY > 24);
};

updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12 },
);

document.querySelectorAll(".reveal").forEach((element) => {
  revealObserver.observe(element);
});

const videoObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      const video = entry.target;
      if (!(video instanceof HTMLVideoElement)) return;

      if (entry.isIntersecting) {
        const source = video.querySelector("source[data-src]");
        if (source && !source.getAttribute("src")) {
          source.setAttribute("src", source.getAttribute("data-src") || "");
          video.load();
        }
        video.play().catch(() => {});
      } else {
        video.pause();
      }
    });
  },
  { rootMargin: "240px 0px", threshold: 0.1 },
);

document.querySelectorAll("[data-lazy-video]").forEach((video) => {
  videoObserver.observe(video);
});
