const mockPeers = [
  { id: "p1", name: "Thông", online: true },
  { id: "p2", name: "Nguyên", online: false },
  { id: "p3", name: "Đạt", online: true },
  { id: "p4", name: "Phú", online: true },
];

const mockChannels = [
  { id: "general", name: "# CNPM", unread: 0 },
  { id: "dev", name: "# MMT", unread: 2 },
  { id: "random", name: "# Database", unread: 0 },
];

const messages = {
  "ch:general": [
    {
      from: "Thông",
      me: false,
      text: "Chào mừng đến #CNPM!",
      ts: Date.now() - 1000 * 60 * 60,
    },
    {
      from: "You",
      me: true,
      text: "Hi team 👋",
      ts: Date.now() - 1000 * 60 * 45,
    },
  ],
  "ch:dev": [
    {
      from: "Đạt",
      me: false,
      text: "Push code mới nha",
      ts: Date.now() - 1000 * 60 * 20,
    },
  ],
  "ch:random": [
    {
      from: "Nguyên",
      me: false,
      text: "Meme giờ nghỉ nè",
      ts: Date.now() - 1000 * 60 * 5,
    },
  ],
  "dm:p1": [
    {
      from: "Thông",
      me: false,
      text: "Bạn rảnh không?",
      ts: Date.now() - 1000 * 60 * 25,
    },
  ],
};

let activeView = { type: "channel", id: "general" };

const peerListEl = document.getElementById("peerList");
const channelListEl = document.getElementById("channelList");
const messageListEl = document.getElementById("messageList");
const messageInputEl = document.getElementById("messageInput");
const composerEl = document.getElementById("composer");
const sendBtnEl = document.getElementById("sendBtn");
const sendTargetEl = document.getElementById("sendTarget");
const chatTitleEl = document.getElementById("chatTitle");
const chatSubtitleEl = document.getElementById("chatSubtitle");
const simulateBtnEl = document.getElementById("simulateBtn");
const addChannelBtnEl = document.getElementById("addChannel");
const peerSearchEl = document.getElementById("peerSearch");
const channelSearchEl = document.getElementById("channelSearch");
const refreshPeersBtnEl = document.getElementById("refreshPeers");

function renderPeers(list = mockPeers) {
  const q = (peerSearchEl.value || "").toLowerCase();
  peerListEl.innerHTML = "";
  list
    .filter((p) => p.name.toLowerCase().includes(q))
    .forEach((p) => {
      const li = document.createElement("li");
      li.dataset.pid = p.id;
      if (activeView.type === "peer" && activeView.id === p.id)
        li.classList.add("active");

      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.textContent = p.name.charAt(0).toUpperCase();

      const name = document.createElement("div");
      name.className = "name";
      name.textContent = p.name;

      const unread = getUnreadCount({ type: "peer", id: p.id });
      if (unread > 0) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = unread;
        li.append(avatar, name, badge);
      } else {
        li.append(avatar, name);
      }

      const status = document.createElement("span");
      status.className = "status " + (p.online ? "online" : "offline");
      li.appendChild(status);

      li.addEventListener("click", () => {
        activeView = { type: "peer", id: p.id };
        markAsRead(activeView);
        updateHeader();
        renderPeers();
        renderChannels();
        renderMessages();
      });

      peerListEl.appendChild(li);
    });
}

function renderChannels(list = mockChannels) {
  const q = (channelSearchEl.value || "").toLowerCase();
  channelListEl.innerHTML = "";
  list
    .filter((c) => c.name.toLowerCase().includes(q))
    .forEach((c) => {
      const li = document.createElement("li");
      li.dataset.cid = c.id;
      if (activeView.type === "channel" && activeView.id === c.id)
        li.classList.add("active");

      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.textContent = "#";

      const name = document.createElement("div");
      name.className = "name";
      name.textContent = c.name;

      const unread = getUnreadCount({ type: "channel", id: c.id });
      if (unread > 0) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = unread;
        li.append(avatar, name, badge);
      } else {
        li.append(avatar, name);
      }

      li.addEventListener("click", () => {
        activeView = { type: "channel", id: c.id };
        markAsRead(activeView);
        updateHeader();
        renderPeers();
        renderChannels();
        renderMessages();
      });

      channelListEl.appendChild(li);
    });
}

function renderMessages() {
  const key = viewKey(activeView);
  const list = messages[key] || [];
  messageListEl.innerHTML = "";

  list.forEach((m) => {
    const wrap = document.createElement("div");
    wrap.className = "msg" + (m.me ? " me" : "");

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = m.text;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = (m.me ? "Bạn" : m.from) + " • " + fmtTime(m.ts);

    wrap.append(bubble, meta);
    messageListEl.appendChild(wrap);
  });

  messageListEl.scrollTop = messageListEl.scrollHeight;
}

function updateHeader() {
  if (activeView.type === "channel") {
    const ch = mockChannels.find((c) => c.id === activeView.id);
    chatTitleEl.textContent = ch ? ch.name : "# channel";
    chatSubtitleEl.textContent = "Broadcast trong kênh";
    sendTargetEl.textContent = "Kênh";
  } else {
    const p = mockPeers.find((x) => x.id === activeView.id);
    chatTitleEl.textContent = p ? p.name : "DM";
    chatSubtitleEl.textContent = "Tin nhắn trực tiếp (P2P)";
    sendTargetEl.textContent = "Peer";
  }
}

function fmtTime(ts) {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function viewKey(view) {
  return view.type === "channel" ? `ch:${view.id}` : `dm:${view.id}`;
}

function getUnreadCount(view) {
  const key = viewKey(view);
  const arr = messages[key] || [];
  const lr = lastRead[key] || 0;
  return arr.filter((m) => m.ts > lr && !m.me).length;
}

const lastRead = {};
function markAsRead(view) {
  const key = viewKey(view);
  const arr = messages[key] || [];
  const last = arr.length ? arr[arr.length - 1].ts : Date.now();
  lastRead[key] = last;
}

function autoresize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(160, textarea.scrollHeight) + "px";
}

composerEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = (messageInputEl.value || "").trim();
  if (!text) return;

  const now = Date.now();
  const key = viewKey(activeView);
  messages[key] = messages[key] || [];
  messages[key].push({ from: "You", me: true, text, ts: now });
  renderMessages();
  markAsRead(activeView);
  messageInputEl.value = "";
  autoresize(messageInputEl);

  // TODO: Nối backend thật ở đây:
  // if (activeView.type === 'channel') {
  //   fetch('/broadcast-peer', { method:'POST', body: JSON.stringify({ channelId: activeView.id, text }) });
  // } else {
  //   fetch('/send-peer', { method:'POST', body: JSON.stringify({ peerId: activeView.id, text }) });
  // }
});

messageInputEl.addEventListener("input", () => autoresize(messageInputEl));

messageInputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtnEl.click();
  }
});

peerSearchEl.addEventListener("input", () => renderPeers());
channelSearchEl.addEventListener("input", () => renderChannels());

refreshPeersBtnEl.addEventListener("click", () => {
  // Mock refresh: toggle a random peer online/offline
  const idx = Math.floor(Math.random() * mockPeers.length);
  mockPeers[idx].online = !mockPeers[idx].online;
  renderPeers();
  // TODO: Thực tế gọi API: fetch('/get-list') rồi cập nhật mockPeers
});

addChannelBtnEl.addEventListener("click", () => {
  const name = prompt("Tên channel (không có #):");
  if (!name) return;
  const id = name.toLowerCase().replace(/\s+/g, "-");
  mockChannels.push({ id, name: `# ${name}`, unread: 0 });
  renderChannels();
});

simulateBtnEl.addEventListener("click", () => simulateIncoming());

function simulateIncoming() {
  // Randomly pick channel or peer
  const mode = Math.random() < 0.6 ? "channel" : "peer";
  if (mode === "channel") {
    const c = mockChannels[Math.floor(Math.random() * mockChannels.length)];
    const key = `ch:${c.id}`;
    messages[key] = messages[key] || [];
    messages[key].push({
      from: "Thông",
      me: false,
      text: `Tin giả lập vào ${c.name}`,
      ts: Date.now(),
    });
    if (!(activeView.type === "channel" && activeView.id === c.id)) {
      // bump unread
      // (calculated on the fly via getUnreadCount, so no state to update)
    } else {
      markAsRead(activeView);
    }
  } else {
    const p = mockPeers[Math.floor(Math.random() * mockPeers.length)];
    const key = `dm:${p.id}`;
    messages[key] = messages[key] || [];
    messages[key].push({
      from: p.name,
      me: false,
      text: `DM từ ${p.name}`,
      ts: Date.now(),
    });
    if (!(activeView.type === "peer" && activeView.id === p.id)) {
      // will show unread badge
    } else {
      markAsRead(activeView);
    }
  }
  renderPeers();
  renderChannels();
  renderMessages();
}

updateHeader();
renderPeers();
renderChannels();
renderMessages();
autoresize(messageInputEl);
