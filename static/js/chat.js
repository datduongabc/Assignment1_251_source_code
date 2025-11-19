const API_PORT = window.APP_CONFIG.API_PORT;
const USERNAME = window.APP_CONFIG.USERNAME;
const API_BASE = `http://localhost:${API_PORT}`;

const messagesDiv = document.getElementById("messages");
const input = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const channelListDiv = document.getElementById("channel-list");
const channelTitle = document.getElementById("current-channel-title");
let currentChannel = "#general";

document.title = `P2P Chat - ${USERNAME}`;
messagesDiv.innerHTML = "";
addMessage(`<strong>${USERNAME}</strong>`);

// --- SELECT CHANNEL ---
channelListDiv.addEventListener("click", (e) => {
  if (e.target && e.target.classList.contains("channel")) {
    const newChannel = e.target.dataset.channel;
    if (newChannel !== currentChannel) {
      document.querySelector(".channel.active")?.classList.remove("active");
      e.target.classList.add("active");
      e.target.classList.remove("new-message");
      currentChannel = newChannel;
      channelTitle.textContent = currentChannel;
      messagesDiv.innerHTML = "";
      addMessage(`Switched to channel <strong>${currentChannel}</strong>`);
    }
  }
});

// --- SEND MESSAGES ---
let isSending = false;

async function sendMessage() {
  const content = input.value.trim();
  if (!content || isSending) return;

  isSending = true;
  input.value = "";
  input.disabled = true;
  sendButton.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        channel: currentChannel,
        message: content,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    addOwnMessage(content);
  } catch (e) {
    addMessage(`Error: ${e.message}`);
    input.value = content;
  } finally {
    isSending = false;
    input.disabled = false;
    sendButton.disabled = false;
    input.focus();
  }
}

sendButton.addEventListener("click", sendMessage);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    sendMessage();
  }
});

// --- DISPLAY MESSAGES ---
function addMessage(msg, sender = null, isOwn = false) {
  const time = new Date().toLocaleTimeString();

  if (!sender) {
    const systemElement = document.createElement("div");
    systemElement.className = "system-msg";
    systemElement.innerHTML = msg;
    messagesDiv.appendChild(systemElement);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return;
  }

  const messageElement = document.createElement("div");
  messageElement.className = `message ${isOwn ? "own" : "other"}`;

  messageElement.innerHTML = `
    <div class="message-bubble">
      ${msg}
    </div>
    <div>
      ${!isOwn ? `<div class="message-sender">${sender}</div>` : ""}
      <div class="message-time">${time}</div>
    </div>
  `;

  messagesDiv.appendChild(messageElement);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function addOwnMessage(msg) {
  addMessage(msg, USERNAME, true);
}

function addOtherMessage(msg, sender) {
  addMessage(msg, sender || "Unknown", false);
}

// --- RECEIVE MESSAGES ---
const seenMessages = new Set();
let lastPeerCount = -1;
let isConnectionLost = false;

async function pollMessages() {
  while (true) {
    try {
      const response = await fetch(`${API_BASE}/messages`);

      if (isConnectionLost) {
        isConnectionLost = false;
        addMessage("Reconnected!");
      }

      if (response.status === 200) {
        const data = await response.json();

        if (data.type === "message") {
          const msgId = `${data.sender}-${data.raw}`;

          if (data.text && !seenMessages.has(msgId)) {
            seenMessages.add(msgId);

            if (data.channel === currentChannel) {
              if (data.sender === USERNAME) {
                addOwnMessage(data.text);
              } else {
                addOtherMessage(data.text, data.sender);
              }
            } else {
              showNotification(data.channel);
            }
          }
        }
      } else if (response.status !== 204) {
        await new Promise((r) => setTimeout(r, 100));
      }
    } catch (e) {
      console.error("Polling error:", e);

      if (!isConnectionLost) {
        isConnectionLost = true;
        addMessage("Lost connection");
      }

      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// --- INITIALIZE ---
setTimeout(async () => {
  try {
    const response = await fetch(`${API_BASE}/peers`);
    if (response.ok) {
      const data = await response.json();
      addMessage(`Connected peers: ${data.peer_count}`);
      lastPeerCount = data.peer_count;
      pollMessages();
    }
  } catch (e) {
    addMessage(`Error: ${e.message}`);
  }
}, 1000);
