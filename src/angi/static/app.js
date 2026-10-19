(function () {
  "use strict";

  const rollBtn = document.getElementById("roll-btn");
  const rerollBtn = document.getElementById("reroll-btn");
  const acceptBtn = document.getElementById("accept-btn");
  const shareBtn = document.getElementById("share-btn");
  const resultCard = document.getElementById("result-card");
  const dishEl = document.getElementById("dish");
  const lineEl = document.getElementById("line");
  const tierFace = document.getElementById("tier-face");
  const weatherLine = document.getElementById("weather-line");
  const brokeBadge = document.getElementById("broke-badge");
  const rejectCountEl = document.getElementById("reject-count");
  const streakEl = document.getElementById("streak");
  const weatherBadge = document.getElementById("weather-badge");
  const cityChips = document.querySelector('.chips[data-group="city"]');
  const mascot = document.getElementById("mascot");
  const toast = document.getElementById("toast");
  const canvas = document.getElementById("share-canvas");

  const REROLL_LABELS = [
    [0, "Không chịu, đổi món 😤"],
    [2, "Vẫn không chịu?!"],
    [4, "Bạn nghiêm túc đấy à?"],
    [6, "…Được rồi, chiều bạn 🙄"],
    [8, "Tôi hết ý kiến rồi đấy 😮‍💨"],
    [15, "Đổi tiếp đi, huyền thoại 🫡"],
  ];
  const TIER_FACES = ["😋", "😏", "😤", "🙄", "😮‍💨", "🫡"];
  // rejected-count milestones -> badge (shown on card + share card, toast on unlock)
  const ACHIEVEMENTS = [
    [30, "👑 Khó Tính Huyền Thoại"],
    [20, "🏅 Khó Tính Chuyên Nghiệp"],
    [10, "🏆 Khó Tính Học Việc"],
  ];
  const WEATHER_LABEL = { rain: "🌧️ đang mưa", hot: "🥵 nắng nóng", any: "🌤️ dễ chịu" };
  const WEATHER_CARD_LINE = {
    rain: "🌧 Trời đang mưa — món dễ ship được ưu tiên đấy.",
    hot: "🥵 Trời nóng — tôi né mấy món bốc lửa cho bạn rồi.",
  };
  const CITY_LABEL = { hn: "HN", sg: "SG" };
  const OFFLINE_LINES = [
    "Mạng công ty lại dở chứng rồi, thử lại phát nữa nhé.",
    "Ơ kìa, mất kết nối. Nhưng đói thì vẫn phải ăn đấy, thử lại đi!",
  ];

  let state = load();
  let current = null; // last /api/suggest response
  let typing = null;
  let locked = false;

  function localDate(d) {
    return (d || new Date()).toLocaleDateString("en-CA"); // YYYY-MM-DD, local tz
  }

  function load() {
    const today = localDate();
    try {
      const saved = JSON.parse(localStorage.getItem("angi") || "{}");
      if (saved.date === today) return { date: today, rejected: saved.rejected || [], city: saved.city || null };
      return { date: today, rejected: [], city: saved.city || null };
    } catch (e) {
      return { date: today, rejected: [], city: null };
    }
  }

  function save() {
    try { localStorage.setItem("angi", JSON.stringify(state)); } catch (e) { /* private mode */ }
  }

  // chips
  const picks = { budget: null, mood: null, city: state.city };
  document.querySelectorAll(".chips").forEach((group) => {
    const name = group.dataset.group;
    group.querySelectorAll(".chip").forEach((chip) => {
      if (name === "city" && chip.dataset.value === state.city) chip.classList.add("active");
      chip.addEventListener("click", () => {
        const was = chip.classList.contains("active");
        group.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        picks[name] = was ? null : chip.dataset.value;
        if (!was) chip.classList.add("active");
        if (name === "city") {
          state.city = picks.city;
          save();
          cityChips.classList.remove("pulse");
          updateWeatherBadge();
        }
      });
    });
  });

  // weather is invisible until someone picks a city — nudge first-time visitors
  if (!state.city) cityChips.classList.add("pulse");

  async function updateWeatherBadge() {
    if (!picks.city) { weatherBadge.hidden = true; return; }
    try {
      const res = await fetch("/api/weather?city=" + picks.city);
      if (!res.ok) return;
      const w = await res.json();
      const icon = (WEATHER_LABEL[w.weather] || "").split(" ")[0];
      const temp = w.temp_c === null ? "" : ` · ${Math.round(w.temp_c)}°C`;
      weatherBadge.textContent = `${CITY_LABEL[picks.city]}${temp} ${icon}`.trim();
      weatherBadge.hidden = false;
    } catch (e) { /* badge is decoration — never block on it */ }
  }
  updateWeatherBadge();

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => (toast.hidden = true), 4000);
  }

  function typewriter(text) {
    if (typing) clearInterval(typing);
    lineEl.classList.remove("loading");
    lineEl.textContent = "";
    const cursor = document.createElement("span");
    cursor.className = "cursor";
    cursor.innerHTML = "&nbsp;";
    lineEl.appendChild(cursor);
    let i = 0;
    typing = setInterval(() => {
      if (i >= text.length) {
        clearInterval(typing);
        typing = null;
        cursor.remove();
        return;
      }
      cursor.before(document.createTextNode(text[i]));
      i += 1;
    }, 22);
    lineEl.onclick = () => { // tap to skip
      if (typing) {
        clearInterval(typing);
        typing = null;
        lineEl.textContent = text;
      }
    };
  }

  function rerollLabel(n) {
    let label = REROLL_LABELS[0][1];
    for (const [min, text] of REROLL_LABELS) if (n >= min) label = text;
    return label;
  }

  function badgeFor(n) {
    for (const [min, name] of ACHIEVEMENTS) if (n >= min) return name;
    return null;
  }

  async function suggest(isReroll) {
    if (isReroll && current) {
      state.rejected.push(current.dish);
      save();
      const n = state.rejected.length;
      rerollBtn.textContent = rerollLabel(n); // escalate immediately, not after the fetch
      for (const [min, name] of ACHIEVEMENTS) {
        if (n === min) showToast(`Thành tựu mở khóa: ${name} — chê ${min} món một buổi trưa!`);
      }
    }
    locked = false;
    rollBtn.disabled = true;
    rerollBtn.disabled = true;
    mascot.classList.remove("wobble");
    void mascot.offsetWidth; // restart animation
    mascot.classList.add("wobble");
    if (resultCard.hidden) {
      rollBtn.textContent = "Đang chọn… 🍳";
    } else {
      if (typing) { clearInterval(typing); typing = null; }
      lineEl.classList.add("loading");
      lineEl.textContent = "Đang nghĩ câu cà khịa… 🍳";
    }

    try {
      const res = await fetch("/api/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          budget: picks.budget,
          mood: picks.mood,
          city: picks.city,
          rejected: state.rejected,
          client_date: state.date,
        }),
      });
      if (res.status === 429) {
        showToast((await res.json()).error);
        return;
      }
      if (!res.ok) {
        showToast("Có lỗi xảy ra, thử lại nhé.");
        return;
      }
      const data = await res.json();
      current = data;
      render(data);
    } catch (e) {
      lineEl.classList.remove("loading");
      showToast(OFFLINE_LINES[Math.floor(Math.random() * OFFLINE_LINES.length)]);
    } finally {
      rollBtn.disabled = false;
      rerollBtn.disabled = false;
      rollBtn.textContent = "Chọn giùm tôi! 🎲";
    }
  }

  function render(data) {
    resultCard.hidden = false;
    resultCard.className = "card result-card tier-" + data.tier;
    tierFace.textContent = TIER_FACES[data.tier] || TIER_FACES[TIER_FACES.length - 1];
    dishEl.textContent = data.dish;
    typewriter(data.line);
    rerollBtn.textContent = rerollLabel(state.rejected.length);
    acceptBtn.textContent = "Chốt món này 😋";
    const n = state.rejected.length;
    const badge = badgeFor(n);
    rejectCountEl.hidden = n < 3;
    rejectCountEl.textContent = `Bạn đã chê ${n} món hôm nay 🙄` + (badge ? ` · ${badge}` : "");
    const wxLine = WEATHER_CARD_LINE[data.weather];
    weatherLine.hidden = !(wxLine && picks.city);
    if (wxLine) weatherLine.textContent = wxLine;
    brokeBadge.hidden = !data.broke;
    if (data.weather && picks.city) {
      weatherBadge.hidden = false;
    }
    streakEl.hidden = true;
    resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  rollBtn.addEventListener("click", () => suggest(false));
  rerollBtn.addEventListener("click", () => suggest(true));

  function bumpStreak() {
    let s = { last: null, count: 0 };
    try { s = JSON.parse(localStorage.getItem("angi_streak") || "{}") || s; } catch (e) { /* ignore */ }
    const today = state.date;
    if (s.last === today) return s.count || 1;
    const y = new Date();
    y.setDate(y.getDate() - 1);
    s.count = s.last === localDate(y) ? (s.count || 0) + 1 : 1;
    s.last = today;
    try { localStorage.setItem("angi_streak", JSON.stringify(s)); } catch (e) { /* ignore */ }
    return s.count;
  }

  function victoryLine(tier, n) {
    if (tier === 0) return "Chốt ngay không chê — bạn là vị khách trong mơ đấy 🎉";
    if (tier <= 2) return "Cuối cùng cũng chốt! Quyết định sáng suốt đấy 🎉";
    return `Sau ${n} món bị chê, cuối cùng bạn cũng gật. Trưa nay đáng nhớ đấy 🎉`;
  }

  acceptBtn.addEventListener("click", () => {
    if (!current) return;
    locked = true;
    acceptBtn.textContent = "Chốt! Ăn ngon nhé 🎉";
    const streak = bumpStreak();
    showToast(victoryLine(current.tier, state.rejected.length) + " Giờ thì khoe vào nhóm đi!");
    if (streak >= 2) {
      streakEl.hidden = false;
      streakEl.textContent = `🔥 Chuỗi ${streak} ngày quyết đoán`;
    }
  });

  shareBtn.addEventListener("click", async () => {
    if (!current) return;
    drawCard(current);
    const text = `🍜 Trưa nay: ${current.dish} — "${current.line}" → angi.wakeuplate.io.vn`;
    canvas.toBlob(async (blob) => {
      const file = new File([blob], "angi.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], text });
          return;
        } catch (e) { /* user cancelled -> fall through */ }
      }
      try {
        await navigator.clipboard.writeText(text);
        showToast("Đã copy! Dán vào nhóm chat thôi 📋");
      } catch (e) {
        showToast(text);
      }
      const a = document.createElement("a");
      a.href = canvas.toDataURL("image/png");
      a.download = "angi.png";
      a.click();
    }, "image/png");
  });

  function drawCard(data) {
    const ctx = canvas.getContext("2d");
    const W = 1080, H = 1080;
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, "#FF7A29");
    grad.addColorStop(1, "#E63946");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    ctx.textAlign = "center";
    ctx.fillStyle = "#fff";
    ctx.font = "160px serif";
    ctx.fillText("🍜", W / 2, 280);
    ctx.font = "800 52px -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
    ctx.fillText("HÔM NAY ĂN GÌ?", W / 2, 400);
    ctx.font = "800 88px -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
    wrapText(ctx, data.dish, W / 2, 530, 920, 96);
    ctx.font = "italic 42px -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
    wrapText(ctx, "“" + data.line + "”", W / 2, 700, 880, 56);
    const n = state.rejected.length;
    if (n >= 3) {
      const badge = badgeFor(n);
      ctx.font = "700 40px -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
      ctx.fillStyle = "#FFC53D";
      ctx.fillText(`Đã chê ${n} món 🙄` + (badge ? ` · ${badge}` : ""), W / 2, 950);
    }
    ctx.fillStyle = "rgba(255,255,255,.85)";
    ctx.font = "600 34px -apple-system, 'Segoe UI', Roboto, Arial, sans-serif";
    ctx.fillText("angi.wakeuplate.io.vn", W / 2, 1020);
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = text.split(" ");
    let line = "";
    for (const word of words) {
      const test = line ? line + " " + word : word;
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, y);
        line = word;
        y += lineHeight;
      } else {
        line = test;
      }
    }
    while (line.length > 1 && ctx.measureText(line).width > maxWidth) {
      line = line.slice(0, -2) + "…"; // single over-long word: hard-truncate
    }
    ctx.fillText(line, x, y);
  }
})();
