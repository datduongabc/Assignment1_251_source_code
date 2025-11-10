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

// --- CHỌN KÊNH ---
channelListDiv.addEventListener("click", (e) => {
  if (e.target && e.target.classList.contains("channel")) {
    const newChannel = e.target.dataset.channel;
    if (newChannel !== currentChannel) {
      document.querySelector(".channel.active")?.classList.remove("active");
      e.target.classList.add("active");
      currentChannel = newChannel;
      channelTitle.textContent = currentChannel;

      addMessage(`Switched to ${currentChannel}`);
    }
  }
});

// --- GỬI TIN NHẮN ---
let isSending = false; // Prevent rapid fire sending

async function sendMessage() {
  const content = input.value.trim();
  if (!content || isSending) return;

  // Lock sending để tránh duplicate
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

    // Hiển thị tin nhắn của mình ngay lập tức
    addOwnMessage(content);
  } catch (e) {
    addMessage(`Error: ${e.message}`);
    // Restore input nếu lỗi
    input.value = content;
  } finally {
    // Unlock sending
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

// --- HIỂN THỊ TIN NHẮN ---
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

const seenMessages = new Set();
let lastPeerCount = -1;
let isConnectionLost = false;

// --- NHẬN TIN NHẮN ---
async function pollMessages() {
  while (true) {
    try {
      const response = await fetch(`${API_BASE}/messages`);

      if (isConnectionLost) {
        isConnectionLost = false;
        addMessage("✅ Reconnected!");
      }

      if (response.status === 200) {
        const data = await response.json();
        console.log("Received message:", data); // Debug log

        if (
          data.type === "channel_peer_update" ||
          data.type === "peer_update"
        ) {
          // Hiển thị peer count chung (không phân kênh)
          const peerCount = data.peer_count || data.peer_count;
          if (peerCount !== lastPeerCount) {
            lastPeerCount = peerCount;
            addMessage(`📊 Connected peers: ${peerCount}`);
          }
        } else if (data.type === "message") {
          // Handle regular chat message
          // Tạo unique ID dựa trên content và sender (không dùng timestamp)
          const msgId = `${data.sender}-${data.text}-${data.text.length}`;

          if (data.sender && data.text && !seenMessages.has(msgId)) {
            seenMessages.add(msgId);

            if (data.sender === "Unknown") {
              addMessage(data.text);
            }
            // Chỉ hiển thị tin nhắn của người khác
            else if (data.sender !== USERNAME) {
              addOtherMessage(data.text, data.sender);
            }
          }
        }
      } else if (response.status !== 204) {
        // Polling nhanh hơn khi không có tin nhắn
        await new Promise((r) => setTimeout(r, 100));
      }

      // Không cần polling peer count - chỉ nhận qua messages
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

// --- KHỞI TẠO ---
setTimeout(async () => {
  try {
    const response = await fetch(`${API_BASE}/status`);
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
