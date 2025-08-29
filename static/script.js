document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const statusDisplay = document.getElementById("statusDisplay");
  const chatLog = document.getElementById("chat-log");

  // Modal and settings elements
  const apiKeyModal = document.getElementById("api-key-modal");
  const saveKeysBtn = document.getElementById("save-keys-btn");
  const settingsBtn = document.getElementById("settings-btn");
  const murfKeyInput = document.getElementById("murf-key");
  const assemblyaiKeyInput = document.getElementById("assemblyai-key");
  const geminiKeyInput = document.getElementById("gemini-key");
  const serpapiKeyInput = document.getElementById("serpapi-key");

  let apiKeys = {};
  let isRecording = false;
  let ws = null;
  let audioContext;
  let mediaStream;
  let processor;
  let audioQueue = [];
  let isPlaying = false;

  // --- Modal & Settings Logic ---
  settingsBtn.addEventListener("click", () => {
    apiKeyModal.style.display = "flex";
  });

  saveKeysBtn.addEventListener("click", () => {
    const murfKey = murfKeyInput.value.trim();
    const assemblyaiKey = assemblyaiKeyInput.value.trim();
    const geminiKey = geminiKeyInput.value.trim();

    if (!murfKey || !assemblyaiKey || !geminiKey) {
      alert("Please fill in all required API keys.");
      return;
    }

    apiKeys = {
      murf: murfKey,
      assemblyai: assemblyaiKey,
      gemini: geminiKey,
      serpapi: serpapiKeyInput.value.trim(),
    };

    apiKeyModal.style.display = "none";
    recordBtn.disabled = false;
    recordBtn.classList.remove("bg-gray-500", "cursor-not-allowed");
    recordBtn.classList.add("bg-blue-600", "hover:bg-blue-700");
    statusDisplay.textContent = "Ready to chat!";
  });

  // --- Chat Logic ---
  const addMessage = (text, type) => {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${type}`;
    messageDiv.textContent = text;
    chatLog.appendChild(messageDiv);
    chatLog.scrollTop = chatLog.scrollHeight;
  };

  const playNextInQueue = () => {
    if (audioQueue.length > 0 && !isPlaying) {
      isPlaying = true;
      const base64Audio = audioQueue.shift();
      const audioData = Uint8Array.from(atob(base64Audio), (c) =>
        c.charCodeAt(0)
      ).buffer;

      if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }

      audioContext
        .decodeAudioData(audioData)
        .then((buffer) => {
          const source = audioContext.createBufferSource();
          source.buffer = buffer;
          source.connect(audioContext.destination);
          source.onended = () => {
            isPlaying = false;
            playNextInQueue();
          };
          source.start();
        })
        .catch((e) => {
          console.error("Error decoding audio data:", e);
          isPlaying = false;
          playNextInQueue();
        });
    }
  };

  const startRecording = async () => {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!audioContext || audioContext.state === "closed") {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: 16000,
        });
      }

      const source = audioContext.createMediaStreamSource(mediaStream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioContext.destination);

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          pcmData[i] = Math.max(-1, Math.min(1, inputData[i])) * 32767;
        }
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(pcmData.buffer);
        }
      };

      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

      ws.onopen = () => {
        const config = { type: "config", keys: apiKeys };
        ws.send(JSON.stringify(config));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "assistant") {
          addMessage(msg.text, "assistant");
        } else if (msg.type === "final") {
          addMessage(msg.text, "user");
        } else if (msg.type === "audio") {
          audioQueue.push(msg.b64);
          playNextInQueue();
        }
      };

      isRecording = true;
      recordBtn.classList.add("recording");
      statusDisplay.textContent = "Listening...";
    } catch (error) {
      console.error("Could not start recording:", error);
      alert("Microphone access is required.");
    }
  };

  const stopRecording = () => {
    if (processor) processor.disconnect();
    if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
    if (ws) ws.close();
    if (audioContext && audioContext.state !== "closed") {
      audioContext.close();
    }

    isRecording = false;
    recordBtn.classList.remove("recording");
    statusDisplay.textContent = "Ready to chat!";
  };

  recordBtn.addEventListener("click", () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });
});
