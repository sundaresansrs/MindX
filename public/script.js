// Wrap in an IIFE to avoid global variable collisions with dashboard.html
(function () {

    // ===================================================
    // GLOBAL STATE FOR SCRIPT.JS PIPELINE
    // ===================================================

    let localUploadedFiles = [];
    let localIsProcessing = false;
    let localConversationHistory = [];

    // Voice recognition
    let recognition = null;
    let isListening = false;
    let silenceTimer = null;
    let finalTranscript = '';
    let interimTranscript = '';

    // ===================================================
    // INITIALIZATION
    // ===================================================

    document.addEventListener('DOMContentLoaded', () => {
        console.log('MindX initialized');

        // Initialize components
        initFileUpload();
        initVoiceRecognition();
        initMessageInput();
        initSendButton();

        // Load conversation history from sessionStorage
        loadConversationHistory();
    });

    // ===================================================
    // FILE UPLOAD - INITIALIZATION
    // ===================================================

    function initFileUpload() {
        const fileInput = document.getElementById('file-upload-input');
        const attachBtn = document.querySelector('.attach-btn');

        // Click on label triggers file input
        if (fileInput) fileInput.addEventListener('change', handleFileSelection);

        // Drag and drop (optional enhancement)
        document.body.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        document.body.addEventListener('drop', (e) => {
            e.preventDefault();
            if (e.dataTransfer.files) {
                const files = Array.from(e.dataTransfer.files);
                processFiles(files);
            }
        });

        // Close upload menu clicking outside
        document.addEventListener('click', (e) => {
            const menu = document.getElementById('upload-menu');
            const btn = e.target.closest('.input-icon-btn');
            if (menu && !menu.contains(e.target) && !btn) {
                menu.classList.remove('show');
            }
        });
    }

    // Toggle upload menu
    function toggleUploadMenu(e) {
        if (e) e.stopPropagation();
        const menu = document.getElementById('upload-menu');
        if (menu) {
            menu.classList.toggle('show');
        }
    }

    // Trigger specific file type upload
    function triggerFileUpload(acceptString) {
        const fileInput = document.getElementById('file-upload-input');
        if (fileInput) {
            fileInput.accept = acceptString;
            fileInput.click();
        }

        const menu = document.getElementById('upload-menu');
        if (menu) menu.classList.remove('show');
    }

    // ===================================================
    // FILE SELECTION HANDLER
    // ===================================================

    function handleFileSelection(event) {
        const files = Array.from(event.target.files);
        processFiles(files);
        event.target.value = ''; // Reset input
    }

    // ===================================================
    // FILE PROCESSING
    // ===================================================

    function processFiles(files) {
        // Check total number of files
        if (localUploadedFiles.length + files.length > CONFIG.MAX_FILES) {
            alert(`You can only upload up to ${CONFIG.MAX_FILES} files at once.`);
            return;
        }

        files.forEach(file => {
            // Validate file
            if (!validateFile(file)) return;

            // Create file object
            const fileObj = {
                id: Date.now() + Math.random(),
                name: file.name,
                size: file.size,
                type: file.type,
                file: file,
                preview: null,
                processedContent: null,
                status: 'pending'
            };

            // Generate preview
            generatePreview(fileObj);

            // Add to array
            localUploadedFiles.push(fileObj);
        });

        // Display previews
        displayFilePreviews();
    }

    // ===================================================
    // FILE VALIDATION
    // ===================================================

    function validateFile(file) {
        // Check file type
        if (!CONFIG.ALLOWED_TYPES[file.type]) {
            alert(`File type "${file.type}" is not supported.\nAllowed types: Images, PDF, DOCX, TXT`);
            return false;
        }

        // Check file size
        if (file.size > CONFIG.MAX_FILE_SIZE) {
            alert(`File "${file.name}" is too large.\nMaximum size: ${CONFIG.MAX_FILE_SIZE / 1024 / 1024} MB`);
            return false;
        }

        return true;
    }

    // ===================================================
    // PREVIEW GENERATION
    // ===================================================

    function generatePreview(fileObj) {
        if (fileObj.type.startsWith('image/')) {
            // Generate image preview
            const reader = new FileReader();
            reader.onload = (e) => {
                fileObj.preview = e.target.result;
                displayFilePreviews();
            };
            reader.readAsDataURL(fileObj.file);
        } else if (fileObj.type === 'application/pdf') {
            // Generate PDF preview (first page)
            generatePDFPreview(fileObj);
        }
    }

    async function generatePDFPreview(fileObj) {
        try {
            const arrayBuffer = await fileObj.file.arrayBuffer();
            const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
            const page = await pdf.getPage(1);

            const viewport = page.getViewport({ scale: 0.5 });
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            canvas.width = viewport.width;
            canvas.height = viewport.height;

            await page.render({ canvasContext: context, viewport: viewport }).promise;
            fileObj.preview = canvas.toDataURL();
            displayFilePreviews();
        } catch (error) {
            console.error('Error generating PDF preview:', error);
        }
    }

    // ===================================================
    // DISPLAY FILE PREVIEWS
    // ===================================================

    function displayFilePreviews() {
        const previewContainer = document.getElementById('file-list-preview');
        if (!previewContainer) return;

        if (localUploadedFiles.length === 0) {
            previewContainer.innerHTML = '';
            previewContainer.classList.remove('has-files');
            return;
        }

        previewContainer.classList.add('has-files');
        previewContainer.innerHTML = localUploadedFiles.map(fileObj => `
    < div class="file-preview-item" data - id="${fileObj.id}" >
        ${fileObj.preview ? `
        <img src="${fileObj.preview}" alt="${fileObj.name}" class="file-preview-image">
      ` : `
        <div class="file-preview-icon">${getFileIcon(fileObj.type)}</div>
      `}
      <div class="file-preview-info">
        <div class="file-preview-name" title="${fileObj.name}">${truncateFileName(fileObj.name, 30)}</div>
        <div class="file-preview-size">${formatFileSize(fileObj.size)}</div>
        ${fileObj.status !== 'pending' ? `
          <div class="file-preview-status">${fileObj.status}</div>
        ` : ''}
      </div>
      <button class="file-remove-btn" onclick="removeFile('${fileObj.id}')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div >
    `).join('');
    }

    // ===================================================
    // HELPER FUNCTIONS
    // ===================================================

    function getFileIcon(type) {
        return CONFIG.ALLOWED_TYPES[type]?.icon || '📎';
    }

    function truncateFileName(name, maxLength = 20) {
        if (name.length <= maxLength) return name;
        const ext = name.split('.').pop();
        const nameWithoutExt = name.substring(0, name.length - ext.length - 1);
        return nameWithoutExt.substring(0, maxLength - ext.length - 4) + '...' + ext;
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function removeFile(fileId) {
        localUploadedFiles = localUploadedFiles.filter(f => f.id.toString() !== fileId.toString());
        displayFilePreviews();
    }

    // ===================================================
    // MESSAGE INPUT - AUTO EXPANSION
    // ===================================================

    function initMessageInput() {
        const input = document.getElementById('search-input');
        if (!input) return;

        input.addEventListener('input', function () {
            // Auto-resize
            this.style.height = 'auto';
            const newHeight = Math.min(this.scrollHeight, 200);
            this.style.height = newHeight + 'px';

            // Show scrollbar if needed
            if (this.scrollHeight > 200) {
                this.style.overflowY = 'auto';
            } else {
                this.style.overflowY = 'hidden';
            }

            // Update character count
            updateCharCount(this.value.length);
        });

        // Handle Enter key
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    function updateCharCount(length) {
        const charCount = document.getElementById('char-counter');
        if (!charCount) return;
        charCount.textContent = `${length}/${CONFIG.MAX_CHARS}`;

        if (length > CONFIG.MAX_CHARS * 0.95) {
            charCount.classList.add('error');
            charCount.classList.remove('warning');
        } else if (length > CONFIG.MAX_CHARS * 0.85) {
            charCount.classList.add('warning');
            charCount.classList.remove('error');
        } else {
            charCount.classList.remove('warning', 'error');
        }
    }

    // ===================================================
    // SEND BUTTON
    // ===================================================

    function initSendButton() {
        const sendBtn = document.getElementById('search-btn');
        if (sendBtn) sendBtn.addEventListener('click', sendMessage);
    }

    // ===================================================
    // SEND MESSAGE - MAIN FUNCTION
    // ===================================================

    async function sendMessage() {
        if (localIsProcessing) return;

        const input = document.getElementById('search-input');
        const message = input.value.trim();

        // Must have either message or files
        if (!message && localUploadedFiles.length === 0) return;

        // Disable send button
        localIsProcessing = true;
        document.getElementById('search-btn').disabled = true;

        try {
            // Process files first
            if (localUploadedFiles.length > 0) {
                await processUploadedFiles();
            }

            // Display user message
            displayUserMessage(message, localUploadedFiles);

            // Build prompt
            const prompt = buildPrompt(message, localUploadedFiles);

            // Clear input and files
            input.value = '';
            input.style.height = 'auto';
            const filesToSend = [...localUploadedFiles];
            localUploadedFiles = [];
            displayFilePreviews();

            // Show typing indicator
            showTypingIndicator();

            // Send to AI
            const response = await sendToGemini(prompt, filesToSend);

            // Hide typing indicator
            hideTypingIndicator();

            // Display AI response
            displayAIMessage(response);

            // Save to history
            saveToHistory({
                role: 'user',
                content: message,
                files: filesToSend.map(f => ({ name: f.name, type: f.type }))
            });
            saveToHistory({
                role: 'assistant',
                content: response
            });

        } catch (error) {
            console.error('Error sending message:', error);
            hideTypingIndicator();
            displayAIMessage('Sorry, something went wrong. Please try again.');
        } finally {
            localIsProcessing = false;
            const sendBtn = document.getElementById('search-btn');
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    // ===================================================
    // PROCESS UPLOADED FILES
    // ===================================================

    async function processUploadedFiles() {
        showProcessingOverlay('Processing files...');

        const promises = localUploadedFiles.map(async (fileObj) => {
            const processorType = CONFIG.ALLOWED_TYPES[fileObj.type]?.processor;

            try {
                switch (processorType) {
                    case 'image':
                        await processImage(fileObj);
                        break;
                    case 'pdf':
                        await processPDF(fileObj);
                        break;
                    case 'docx':
                        await processDOCX(fileObj);
                        break;
                    case 'text':
                        await processTXT(fileObj);
                        break;
                }
                fileObj.status = '✓ Processed';
            } catch (error) {
                console.error(`Error processing ${fileObj.name}:`, error);
                fileObj.status = '✗ Error';
            }

            displayFilePreviews();
        });

        await Promise.all(promises);
        hideProcessingOverlay();
    }

    // ===================================================
    // IMAGE PROCESSING (OCR)
    // ===================================================

    async function processImage(fileObj) {
        updateProcessingText(`Processing ${fileObj.name}...`);

        // For Gemini, we send the image directly (base64)
        // No OCR needed - Gemini has vision
        const reader = new FileReader();
        const base64 = await new Promise((resolve) => {
            reader.onload = (e) => resolve(e.target.result.split(',')[1]);
            reader.readAsDataURL(fileObj.file);
        });

        fileObj.processedContent = {
            type: 'image',
            data: base64,
            mimeType: fileObj.type
        };
    }

    // ===================================================
    // PDF PROCESSING
    // ===================================================

    async function processPDF(fileObj) {
        updateProcessingText(`Reading PDF: ${fileObj.name}...`);

        const arrayBuffer = await fileObj.file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

        let fullText = '';

        for (let i = 1; i <= pdf.numPages; i++) {
            updateProcessingText(`Reading PDF: ${fileObj.name} (page ${i}/${pdf.numPages})...`);

            const page = await pdf.getPage(i);
            const textContent = await page.getTextContent();
            const pageText = textContent.items.map(item => item.str).join(' ');

            fullText += `\n--- Page ${i} ---\n${pageText}\n`;
        }

        fileObj.processedContent = {
            type: 'text',
            data: fullText.trim(),
            pageCount: pdf.numPages
        };
    }

    // ===================================================
    // DOCX PROCESSING
    // ===================================================

    async function processDOCX(fileObj) {
        updateProcessingText(`Processing document: ${fileObj.name}...`);

        const arrayBuffer = await fileObj.file.arrayBuffer();
        const result = await mammoth.extractRawText({ arrayBuffer: arrayBuffer });

        fileObj.processedContent = {
            type: 'text',
            data: result.value
        };
    }

    // ===================================================
    // TXT PROCESSING
    // ===================================================

    async function processTXT(fileObj) {
        updateProcessingText(`Reading text file: ${fileObj.name}...`);

        const text = await fileObj.file.text();

        fileObj.processedContent = {
            type: 'text',
            data: text
        };
    }

    // ===================================================
    // BUILD PROMPT FOR AI
    // ===================================================

    function buildPrompt(userMessage, files) {
        let prompt = '';

        // Add file contents
        if (files.length > 0) {
            prompt += 'USER UPLOADED DOCUMENTS:\n\n';

            files.forEach(fileObj => {
                if (fileObj.processedContent && fileObj.processedContent.type === 'text') {
                    prompt += `[File: ${fileObj.name}]\n`;
                    if (fileObj.processedContent.pageCount) {
                        prompt += `(${fileObj.processedContent.pageCount} pages)\n`;
                    }
                    prompt += `${fileObj.processedContent.data}\n\n`;
                }
            });
        }

        // Add user message
        if (userMessage) {
            prompt += `USER QUESTION:\n${userMessage}\n\n`;
        }

        prompt += 'Please analyze the documents and answer the question thoroughly.';

        return prompt;
    }

    // ===================================================
    // SEND TO GEMINI API
    // ===================================================

    async function sendToGemini(prompt, files) {
        // Check for API key
        if (!CONFIG.GEMINI_API_KEY || CONFIG.GEMINI_API_KEY === 'YOUR_API_KEY_HERE') {
            throw new Error('Please set your Gemini API key in config.js');
        }

        // Build request body
        const parts = [];

        // Add text prompt
        if (prompt) {
            parts.push({ text: prompt });
        }

        // Add images (if any)
        files.forEach(fileObj => {
            if (fileObj.processedContent && fileObj.processedContent.type === 'image') {
                parts.push({
                    inline_data: {
                        mime_type: fileObj.processedContent.mimeType,
                        data: fileObj.processedContent.data
                    }
                });
            }
        });

        const requestBody = {
            contents: [{
                parts: parts
            }]
        };

        // Make API request
        const response = await fetch(
            `${CONFIG.GEMINI_ENDPOINT}?key=${CONFIG.GEMINI_API_KEY}`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            }
        );

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error?.message || 'API request failed');
        }

        const data = await response.json();

        // Extract response text
        const responseText = data.candidates?.[0]?.content?.parts?.[0]?.text || 'No response generated.';

        return responseText;
    }

    // ===================================================
    // DISPLAY USER MESSAGE
    // ===================================================

    function displayUserMessage(message, files) {
        const conversationArea = document.getElementById('chat-container') || document.querySelector('.conversation-area');
        if (!conversationArea) return;

        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-bubble user-message';

        // Add files (if any) - ABOVE text
        if (files && files.length > 0) {
            const filesContainer = document.createElement('div');
            filesContainer.className = 'flex flex-col gap-2 mb-3';

            files.forEach(fileObj => {
                const isImage = fileObj.type && fileObj.type.startsWith('image');
                const fileCard = document.createElement('div');
                fileCard.className = 'flex items-center gap-3 bg-white/10 border border-white/10 p-3 rounded-xl max-w-sm cursor-pointer hover:bg-white/20 transition-colors';

                if (isImage && fileObj.preview) {
                    fileCard.innerHTML = `
                  <img src="${fileObj.preview}" alt="${fileObj.name}" class="w-8 h-8 object-cover rounded">
                  <div class="flex-1 min-w-0 text-left">
                     <div class="text-xs font-bold text-slate-100 truncate">${truncateFileName(fileObj.name, 20)}</div>
                     <div class="text-[10px] text-slate-500 uppercase tracking-tight">${formatFileSize(fileObj.size)}</div>
                  </div>
                `;
                } else {
                    fileCard.innerHTML = `
                  <span class="material-symbols-outlined text-primary text-2xl">${isImage ? 'image' : 'description'}</span>
                  <div class="flex-1 min-w-0 text-left">
                      <div class="text-xs font-bold text-slate-100 truncate">${truncateFileName(fileObj.name, 20)}</div>
                      <div class="text-[10px] text-slate-500 uppercase tracking-tight">${formatFileSize(fileObj.size)}</div>
                  </div>
                `;
                }
                filesContainer.appendChild(fileCard);
            });

            messageWrapper.appendChild(filesContainer);
        }

        // Add message text - BELOW files
        if (message) {
            const messageText = document.createElement('div');
            messageText.textContent = message;
            messageWrapper.appendChild(messageText);
        }

        conversationArea.appendChild(messageWrapper);
        scrollToBottom();
    }

    // ===================================================
    // DISPLAY AI MESSAGE
    // ===================================================

    function displayAIMessage(content) {
        const conversationArea = document.getElementById('chat-container') || document.querySelector('.conversation-area');
        if (!conversationArea) return;

        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-bubble ai-message';

        const messageText = document.createElement('div');
        messageText.className = 'markdown-body'; // Using markdown-body to inherit styles

        // Parse markdown
        messageText.innerHTML = marked.parse(content);

        messageWrapper.appendChild(messageText);
        conversationArea.appendChild(messageWrapper);
        scrollToBottom();
    }

    // ===================================================
    // TYPING INDICATOR
    // ===================================================

    function showTypingIndicator() {
        const conversationArea = document.getElementById('chat-container') || document.querySelector('.conversation-area');
        if (!conversationArea) return;

        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.id = 'typingIndicator';
        indicator.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;

        conversationArea.appendChild(indicator);
        scrollToBottom();
    }

    function hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    // ===================================================
    // PROCESSING OVERLAY
    // ===================================================

    function showProcessingOverlay(text) {
        const overlay = document.getElementById('processingOverlay');
        if (!overlay) return;
        const textEl = document.getElementById('processingText');
        textEl.textContent = text;
        overlay.classList.add('visible');
    }

    function hideProcessingOverlay() {
        const overlay = document.getElementById('processingOverlay');
        if (overlay) overlay.classList.remove('visible');
    }

    function updateProcessingText(text) {
        const textEl = document.getElementById('processingText');
        if (textEl) {
            textEl.textContent = text;
        }
    }

    // ===================================================
    // SCROLL TO BOTTOM
    // ===================================================

    function scrollToBottom() {
        const scroller = document.getElementById('chat-scroller');
        if (scroller) scroller.scrollTop = scroller.scrollHeight;
    }

    // ===================================================
    // CONVERSATION HISTORY
    // ===================================================

    function saveToHistory(message) {
        localConversationHistory.push(message);
        sessionStorage.setItem('mindx_conversation', JSON.stringify(localConversationHistory));
    }

    function loadConversationHistory() {
        const saved = sessionStorage.getItem('mindx_conversation');
        if (saved) {
            localConversationHistory = JSON.parse(saved);
        }
    }

    // ===================================================
    // VOICE RECOGNITION
    // ===================================================

    function initVoiceRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        const btn = document.getElementById('voice-btn');
        if (!SpeechRecognition) {
            console.warn('Voice recognition not supported');
            if (btn) btn.style.display = 'none';
            return;
        }

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onresult = (event) => {
            interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;

                if (event.results[i].isFinal) {
                    finalTranscript += transcript + ' ';
                } else {
                    interimTranscript += transcript;
                }
            }

            updateInputWithTranscript();
            updateVoiceStatusPreview();
            resetSilenceTimer();
        };

        recognition.onerror = (event) => {
            console.error('Voice recognition error:', event.error);
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                alert(`Voice error: ${event.error}`);
            }
            stopVoiceRecognition();
        };

        recognition.onend = () => {
            if (isListening) {
                try {
                    recognition.start();
                } catch (e) {
                    stopVoiceRecognition();
                }
            }
        };

        // Add click handler
        if (btn) btn.addEventListener('click', toggleVoiceRecognition);
    }

    function toggleVoiceRecognition() {
        if (isListening) {
            stopVoiceRecognition();
        } else {
            startVoiceRecognition();
        }
    }

    function startVoiceRecognition() {
        if (!recognition) return;

        finalTranscript = '';
        interimTranscript = '';

        const input = document.getElementById('search-input');
        if (input) input.value = '';

        try {
            recognition.start();
            isListening = true;
            updateVoiceUI(true);
            showVoiceStatus();
        } catch (e) {
            console.error('Error starting recognition:', e);
        }
    }

    function stopVoiceRecognition() {
        if (recognition) {
            recognition.stop();
        }

        isListening = false;

        if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
        }

        updateVoiceUI(false);
        hideVoiceStatus();
    }

    function updateInputWithTranscript() {
        const input = document.getElementById('search-input');
        if (!input) return;
        const fullTranscript = (finalTranscript + interimTranscript).trim();

        input.value = fullTranscript;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';

        updateCharCount(fullTranscript.length);
    }

    function resetSilenceTimer() {
        if (silenceTimer) {
            clearTimeout(silenceTimer);
        }

        silenceTimer = setTimeout(() => {
            const transcript = (finalTranscript + interimTranscript).trim();

            if (transcript.length >= CONFIG.VOICE_MIN_LENGTH) {
                stopVoiceRecognition();
                setTimeout(() => {
                    sendMessage();
                }, 300);
            }
        }, CONFIG.VOICE_SILENCE_DELAY);
    }

    function updateVoiceUI(listening) {
        const voiceBtn = document.getElementById('voice-btn');
        if (!voiceBtn) return;
        const indicator = voiceBtn.querySelector('.listening-indicator');

        if (listening) {
            voiceBtn.classList.add('listening');
            if (indicator) indicator.classList.add('active');
        } else {
            voiceBtn.classList.remove('listening');
            if (indicator) indicator.classList.remove('active');
        }
    }

    function showVoiceStatus() {
        const status = document.getElementById('voiceStatus');
        if (status) {
            status.classList.add('visible');
        }
    }

    function hideVoiceStatus() {
        const status = document.getElementById('voiceStatus');
        if (status) {
            status.classList.remove('visible');
        }
    }

    function updateVoiceStatusPreview() {
        const preview = document.querySelector('.transcript-preview');
        if (preview) {
            const transcript = (finalTranscript + interimTranscript).trim();
            preview.textContent = transcript || 'Start speaking...';
        }
    }

    // Expose necessary functions to the global scope
    window.removeFile = removeFile;
    window.handleSearch = sendMessage; // Override older dashboard.html references
    window.toggleUploadMenu = toggleUploadMenu;
    window.triggerFileUpload = triggerFileUpload;

})();
