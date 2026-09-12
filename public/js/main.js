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

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    videos.forEach((video) => video.pause());
    return;
  }

  requestVideoUpdate();
});

document.querySelectorAll("[data-youtube-id]").forEach((container) => {
  const cover = container.querySelector(".youtube-cover");
  const thumbnail = cover?.querySelector("img");
  const videoId = container.getAttribute("data-youtube-id");

  if (!(cover instanceof HTMLButtonElement) || !videoId) return;

  if (thumbnail instanceof HTMLImageElement) {
    thumbnail.addEventListener("error", () => {
      thumbnail.src = `https://i.ytimg.com/vi/${encodeURIComponent(videoId)}/hqdefault.jpg`;
    }, { once: true });
  }

  cover.addEventListener("click", () => {
    const iframe = document.createElement("iframe");
    iframe.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}?autoplay=1&rel=0`;
    iframe.title = "Разработка котельной Валдай в MetaPlatform";
    iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.allowFullscreen = true;
    container.replaceChildren(iframe);
  }, { once: true });
});

const registrationForm = document.querySelector("#registration-form");

if (registrationForm instanceof HTMLFormElement) {
  const status = registrationForm.querySelector("[data-registration-status]");
  const submit = registrationForm.querySelector("button[type='submit']");
  const username = registrationForm.elements.namedItem("username");

  if (username instanceof HTMLInputElement) {
    username.addEventListener("input", () => {
      username.value = username.value.toLowerCase().replace(/\s+/g, "");
    });
  }

  registrationForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!registrationForm.reportValidity()) return;
    if (!(submit instanceof HTMLButtonElement)) return;

    const data = new FormData(registrationForm);
    const payload = {
      email: String(data.get("email") || "").trim(),
      username: String(data.get("username") || "").trim(),
      consent: data.get("consent") === "on",
      website: String(data.get("website") || ""),
    };

    submit.disabled = true;
    submit.classList.add("is-loading");
    submit.setAttribute("aria-busy", "true");
    submit.firstChild.textContent = "Создаём доступ ";
    if (status instanceof HTMLElement) {
      status.textContent = "";
      status.className = "registration-status";
    }

    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result?.error?.message || "Не удалось создать доступ. Попробуйте ещё раз.");
      }

      registrationForm.classList.add("is-complete");
      registrationForm.querySelectorAll("input, button").forEach((element) => {
        element.disabled = true;
      });
      submit.classList.remove("is-loading");
      submit.classList.add("is-success");
      submit.removeAttribute("aria-busy");
      submit.firstChild.textContent = "Доступ создан ";
      const submitIcon = submit.querySelector("span");
      if (submitIcon instanceof HTMLElement) submitIcon.textContent = "✓";
      if (status instanceof HTMLElement) {
        status.textContent = result.message || "Доступ создан. Проверьте почту.";
        status.classList.add("is-success");
      }
    } catch (error) {
      if (status instanceof HTMLElement) {
        status.textContent = error instanceof Error ? error.message : "Не удалось создать доступ.";
        status.classList.add("is-error");
      }
      submit.disabled = false;
      submit.classList.remove("is-loading");
      submit.removeAttribute("aria-busy");
      submit.firstChild.textContent = "Получить доступ ";
    }
  });
}
