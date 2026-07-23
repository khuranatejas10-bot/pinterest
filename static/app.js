document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const keywordInput = document.getElementById('keyword-input');
    const sendButton = document.getElementById('send-button');
    const chatMessagesContainer = document.getElementById('chat-messages-container');
    const typingIndicator = document.getElementById('typing-indicator');
    const clearChatBtn = document.getElementById('clear-chat-btn');

    let eventSource = null;

    // Helper: Scroll chat to bottom
    const scrollToBottom = () => {
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
    };

    // Clear Chat Logic
    clearChatBtn.addEventListener('click', () => {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        typingIndicator.style.display = 'none';
        chatMessagesContainer.innerHTML = `
            <div class="chat-message bot">
                <div class="avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="message-content">
                    <p>Hi there! 👋 I am your Pinterest PPT assistant. Type any keyword (e.g. <em>"modern home design"</em> or <em>"lofi wallpapers"</em>), and I'll scrape the most popular pins to generate a structured 6-slide PowerPoint presentation for you.</p>
                </div>
            </div>
        `;
        keywordInput.disabled = false;
        sendButton.disabled = false;
        keywordInput.focus();
        scrollToBottom();
    });

    // Helper: Add a chat bubble
    const addMessageBubble = (text, isUser = false, isHtml = false) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'bot'}`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'avatar';
        avatarDiv.innerHTML = isUser ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (isHtml) {
            contentDiv.innerHTML = text;
        } else {
            const p = document.createElement('p');
            p.textContent = text;
            contentDiv.appendChild(p);
        }
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        chatMessagesContainer.appendChild(messageDiv);
        scrollToBottom();
        
        return contentDiv; // Return content ref to update it dynamically
    };

    // Submit handler
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        
        const keyword = keywordInput.value.trim();
        if (!keyword) return;

        // Reset input
        keywordInput.value = '';
        keywordInput.disabled = true;
        sendButton.disabled = true;

        // Add user message
        addMessageBubble(keyword, true);

        // Add bot message placeholder for live status updates
        const botBubbleContent = addMessageBubble('', false, true);
        const statusListDiv = document.createElement('div');
        statusListDiv.className = 'status-list';
        botBubbleContent.appendChild(statusListDiv);

        // Show typing dots
        typingIndicator.style.display = 'flex';
        scrollToBottom();

        // Connect to Server-Sent Events (SSE)
        const encodedKeyword = encodeURIComponent(keyword);
        eventSource = new EventSource(`/api/pinterest/scrape?keyword=${encodedKeyword}`);

        // Helper to append a status list item
        const addStatusItem = (message) => {
            // Check if last status item has the same text to avoid duplicates
            const lastItem = statusListDiv.lastElementChild;
            if (lastItem && lastItem.textContent === message) return;

            const item = document.createElement('div');
            item.className = 'status-item';
            
            // Add a small spinner icon to the new status item
            item.innerHTML = `<i class="fas fa-circle-notch fa-spin status-icon" style="color: #E60023; margin-right: 8px;"></i> <span class="status-text">${message}</span>`;
            
            // Turn off the spinner of the previous status item
            if (lastItem) {
                const prevIcon = lastItem.querySelector('.status-icon');
                if (prevIcon) {
                    prevIcon.className = 'fas fa-check';
                    prevIcon.style.color = '#2ecc71'; // Green checkmark
                }
            }

            statusListDiv.appendChild(item);
            scrollToBottom();
        };

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'status') {
                    addStatusItem(data.message);
                } 
                else if (data.type === 'complete') {
                    // Close stream
                    eventSource.close();
                    
                    // Hide typing indicator
                    typingIndicator.style.display = 'none';
                    
                    // Complete the final status item mark
                    const lastItem = statusListDiv.lastElementChild;
                    if (lastItem) {
                        const prevIcon = lastItem.querySelector('.status-icon');
                        if (prevIcon) {
                            prevIcon.className = 'fas fa-check';
                            prevIcon.style.color = '#2ecc71';
                        }
                    }

                    // Success details
                    const successP = document.createElement('p');
                    successP.style.marginTop = '12px';
                    successP.style.fontWeight = '500';
                    successP.innerHTML = `<i class="fas fa-file-powerpoint" style="color: #d24726; margin-right: 6px;"></i> PowerPoint generated successfully with <strong>${data.num_images} images</strong> across <strong>${data.num_slides} slides</strong>!`;
                    botBubbleContent.appendChild(successP);

                    // Generate PPT Preview Container
                    const session_id = Math.random().toString(36).substring(2, 9);
                    const previewContainer = document.createElement('div');
                    previewContainer.className = 'ppt-preview-container';
                    
                    // Header
                    const previewHeader = document.createElement('div');
                    previewHeader.className = 'preview-header';
                    previewHeader.innerHTML = `
                        <span class="preview-title">Presentation Preview</span>
                        <span class="slide-counter">Slide 1 of ${data.num_slides}</span>
                    `;
                    previewContainer.appendChild(previewHeader);
                    
                    // Viewport
                    const previewViewport = document.createElement('div');
                    previewViewport.className = 'preview-viewport';
                    
                    // Slide 1 (Title slide)
                    const slide1 = document.createElement('div');
                    slide1.className = 'preview-slide slide-type-title active';
                    slide1.innerHTML = `
                        <div class="slide-title-text">${keyword.toUpperCase()}</div>
                        <div class="slide-title-bar"></div>
                        <div class="slide-subtitle-text">Top 10 on Pinterest</div>
                    `;
                    previewViewport.appendChild(slide1);
                    
                    // Slides 2 to N (Images)
                    const slides = [slide1];
                    const urls = data.image_urls || [];
                    
                    for (let i = 0; i < urls.length; i += 2) {
                        const slide = document.createElement('div');
                        slide.className = 'preview-slide slide-type-content';
                        
                        // Left Image container
                        const leftImgContainer = document.createElement('div');
                        leftImgContainer.className = 'preview-image-container';
                        leftImgContainer.innerHTML = `
                            <img src="${urls[i]}" alt="Rank ${i + 1}">
                            <div class="preview-image-badge">${i + 1}</div>
                        `;
                        slide.appendChild(leftImgContainer);
                        
                        // Right Image container
                        const rightImgContainer = document.createElement('div');
                        rightImgContainer.className = 'preview-image-container';
                        if (i + 1 < urls.length) {
                            rightImgContainer.innerHTML = `
                                <img src="${urls[i + 1]}" alt="Rank ${i + 2}">
                                <div class="preview-image-badge">${i + 2}</div>
                            `;
                        } else {
                            // Blank placeholder
                            rightImgContainer.style.visibility = 'hidden';
                        }
                        slide.appendChild(rightImgContainer);
                        
                        previewViewport.appendChild(slide);
                        slides.push(slide);
                    }
                    previewContainer.appendChild(previewViewport);
                    
                    // Controls
                    const previewControls = document.createElement('div');
                    previewControls.className = 'preview-controls';
                    previewControls.innerHTML = `
                        <button class="preview-nav-btn prev-btn" disabled><i class="fas fa-chevron-left"></i> Previous</button>
                        <button class="preview-nav-btn next-btn" ${slides.length <= 1 ? 'disabled' : ''}>Next <i class="fas fa-chevron-right"></i></button>
                    `;
                    previewContainer.appendChild(previewControls);
                    botBubbleContent.appendChild(previewContainer);
                    
                    // Carousel Logic
                    let currentSlideIdx = 0;
                    const prevBtn = previewControls.querySelector('.prev-btn');
                    const nextBtn = previewControls.querySelector('.next-btn');
                    const counterSpan = previewHeader.querySelector('.slide-counter');
                    
                    const updateSlideState = () => {
                        slides.forEach((slide, idx) => {
                            if (idx === currentSlideIdx) {
                                slide.classList.add('active');
                            } else {
                                slide.classList.remove('active');
                            }
                        });
                        
                        counterSpan.textContent = `Slide ${currentSlideIdx + 1} of ${data.num_slides}`;
                        prevBtn.disabled = currentSlideIdx === 0;
                        nextBtn.disabled = currentSlideIdx === slides.length - 1;
                    };
                    
                    prevBtn.addEventListener('click', () => {
                        if (currentSlideIdx > 0) {
                            currentSlideIdx--;
                            updateSlideState();
                        }
                    });
                    
                    nextBtn.addEventListener('click', () => {
                        if (currentSlideIdx < slides.length - 1) {
                            currentSlideIdx++;
                            updateSlideState();
                        }
                    });

                    // Add download button below the preview container
                    const downloadBtn = document.createElement('a');
                    downloadBtn.href = data.download_url;
                    downloadBtn.setAttribute('download', data.filename);
                    downloadBtn.className = 'download-btn';
                    downloadBtn.style.marginTop = '16px';
                    downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download PowerPoint (.pptx)';
                    botBubbleContent.appendChild(downloadBtn);

                    // Re-enable inputs
                    keywordInput.disabled = false;
                    sendButton.disabled = false;
                    scrollToBottom();
                } 
                else if (data.type === 'error') {
                    eventSource.close();
                    typingIndicator.style.display = 'none';

                    // Update style of current items
                    const lastItem = statusListDiv.lastElementChild;
                    if (lastItem) {
                        const prevIcon = lastItem.querySelector('.status-icon');
                        if (prevIcon) {
                            prevIcon.className = 'fas fa-times';
                            prevIcon.style.color = '#e74c3c'; // Red cross
                        }
                    }

                    const errorP = document.createElement('p');
                    errorP.style.marginTop = '12px';
                    errorP.style.color = '#e74c3c';
                    errorP.style.fontWeight = '500';
                    
                    if (data.error_type === 'timeout') {
                        errorP.innerHTML = `<i class="fas fa-exclamation-triangle" style="margin-right: 6px;"></i> Process timed out (90s limit reached). Please try a different keyword or try again.`;
                    } else {
                        errorP.innerHTML = `<i class="fas fa-exclamation-circle" style="margin-right: 6px;"></i> Scraping failed: ${data.message}. Suggest trying a different keyword.`;
                    }
                    
                    botBubbleContent.appendChild(errorP);

                    keywordInput.disabled = false;
                    sendButton.disabled = false;
                    scrollToBottom();
                }
            } catch (e) {
                console.error("Error parsing stream event data", e);
            }
        };

        eventSource.onerror = (err) => {
            console.error("SSE connection error", err);
            eventSource.close();
            typingIndicator.style.display = 'none';
            
            const errorP = document.createElement('p');
            errorP.style.marginTop = '12px';
            errorP.style.color = '#e74c3c';
            errorP.innerHTML = `<i class="fas fa-wifi" style="margin-right: 6px;"></i> Server connection lost. Please try again.`;
            botBubbleContent.appendChild(errorP);

            keywordInput.disabled = false;
            sendButton.disabled = false;
            scrollToBottom();
        };
    });
});
