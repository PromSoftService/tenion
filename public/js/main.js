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

const videos = [...document.querySelectorAll("[data-lazy-video]")];

const loadVideo = (video) => {
  const source = video.querySelector("source[data-src]");
  if (source && !source.getAttribute("src")) {
    source.setAttribute("src", source.getAttribute("data-src") || "");
    video.load();
  }
};

const loadVideoObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      const video = entry.target;
      if (!(video instanceof HTMLVideoElement)) return;

      if (entry.isIntersecting) {
        loadVideo(video);
        loadVideoObserver.unobserve(video);
      }
    });
  },
  { rootMargin: "320px 0px", threshold: 0 },
);

videos.forEach((video) => {
  loadVideoObserver.observe(video);
});

let videoFrame = 0;

const updateActiveVideo = () => {
  videoFrame = 0;
  const viewportCenter = window.innerHeight / 2;
  const visibleVideos = videos
    .map((video) => ({ video, rect: video.getBoundingClientRect() }))
    .filter(({ rect }) => rect.bottom > 0 && rect.top < window.innerHeight)
    .sort((a, b) => {
      const aDistance = Math.abs((a.rect.top + a.rect.bottom) / 2 - viewportCenter);
      const bDistance = Math.abs((b.rect.top + b.rect.bottom) / 2 - viewportCenter);
      return aDistance - bDistance;
    });

  const activeVideo = visibleVideos[0]?.video;

  videos.forEach((video) => {
    if (video === activeVideo) {
      loadVideo(video);
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  });
};

const requestVideoUpdate = () => {
  if (videoFrame) return;
  videoFrame = window.requestAnimationFrame(updateActiveVideo);
};

updateActiveVideo();
window.addEventListener("scroll", requestVideoUpdate, { passive: true });
window.addEventListener("resize", requestVideoUpdate);
