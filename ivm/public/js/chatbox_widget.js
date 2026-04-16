$(document).on("app_ready", function () {
	if (frappe.session.user === "Guest") {
		return;
	}
	if (document.getElementById("howiebot-widget")) {
		return;
	}

	const CHAT_ICON = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
		<path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/>
		<path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/>
	</svg>`;

	const CLOSE_ICON = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
		<path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
	</svg>`;

	const SEND_ICON = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
		<path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
	</svg>`;

	// Build widget DOM
	const widget = document.createElement("div");
	widget.id = "howiebot-widget";
	widget.innerHTML = `
		<button id="howiebot-toggle" title="Chat with HowieBot">
			${CHAT_ICON}
		</button>
		<div id="howiebot-panel">
			<div id="howiebot-header">
				<span class="howiebot-title">HowieBot</span>
				<button id="howiebot-close" title="Close">&times;</button>
			</div>
			<div id="howiebot-messages"></div>
			<div id="howiebot-input-area">
				<textarea id="howiebot-input" placeholder="Type a message..." rows="1"></textarea>
				<button id="howiebot-send" title="Send">${SEND_ICON}</button>
			</div>
		</div>
	`;
	document.body.appendChild(widget);

	const toggleBtn = document.getElementById("howiebot-toggle");
	const panel = document.getElementById("howiebot-panel");
	const closeBtn = document.getElementById("howiebot-close");
	const messagesEl = document.getElementById("howiebot-messages");
	const inputEl = document.getElementById("howiebot-input");
	const sendBtn = document.getElementById("howiebot-send");
	let isSending = false;

	function togglePanel() {
		const isOpen = panel.classList.toggle("open");
		toggleBtn.innerHTML = isOpen ? CLOSE_ICON : CHAT_ICON;
		if (isOpen) {
			inputEl.focus();
		}
	}

	function scrollToBottom() {
		messagesEl.scrollTop = messagesEl.scrollHeight;
	}

	function appendMessage(text, type) {
		const msg = document.createElement("div");
		msg.className = `howiebot-msg ${type}`;
		msg.textContent = text;
		messagesEl.appendChild(msg);
		scrollToBottom();
		return msg;
	}

	function showTyping() {
		const typing = document.createElement("div");
		typing.className = "howiebot-typing";
		typing.id = "howiebot-typing-indicator";
		typing.innerHTML = "<span></span><span></span><span></span>";
		messagesEl.appendChild(typing);
		scrollToBottom();
		return typing;
	}

	function removeTyping() {
		const el = document.getElementById("howiebot-typing-indicator");
		if (el) {
			el.remove();
		}
	}

	function setInputEnabled(enabled) {
		isSending = !enabled;
		inputEl.disabled = !enabled;
		sendBtn.disabled = !enabled;
	}

	function sendMessage() {
		const message = inputEl.value.trim();
		if (!message || isSending) {
			return;
		}

		appendMessage(message, "user");
		inputEl.value = "";
		inputEl.style.height = "auto";
		setInputEnabled(false);
		showTyping();

		frappe.call({
			method: "ivm.ivm_integrations.howiebot.chat.send_message",
			args: { message: message },
			callback: function (r) {
				removeTyping();
				setInputEnabled(true);
				if (r && r.message) {
					const reply = r.message.reply || r.message.response || JSON.stringify(r.message);
					appendMessage(reply, "bot");
				} else {
					appendMessage("No response received.", "error");
				}
				inputEl.focus();
			},
			error: function () {
				removeTyping();
				setInputEnabled(true);
				appendMessage("Something went wrong. Please try again.", "error");
				inputEl.focus();
			},
		});
	}

	// Event listeners
	toggleBtn.addEventListener("click", togglePanel);
	closeBtn.addEventListener("click", togglePanel);

	inputEl.addEventListener("keydown", function (e) {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	});

	sendBtn.addEventListener("click", sendMessage);

	// Auto-resize textarea
	inputEl.addEventListener("input", function () {
		this.style.height = "auto";
		this.style.height = Math.min(this.scrollHeight, 80) + "px";
	});
});
