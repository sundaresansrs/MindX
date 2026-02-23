// ===================================================
// CONFIGURATION
// ===================================================

const CONFIG = {
    // Google Gemini API
    GEMINI_API_KEY: 'AIzaSyCaSSwMeah8pcwSkJsTdUkOZDJwmsgoey0', // Get from https://makersuite.google.com/app/apikey
    GEMINI_ENDPOINT: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent',

    // File upload limits
    MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
    MAX_FILES: 5,
    ALLOWED_TYPES: {
        'image/png': { ext: '.png', icon: '🖼️', processor: 'image' },
        'image/jpeg': { ext: '.jpg', icon: '🖼️', processor: 'image' },
        'image/jpg': { ext: '.jpg', icon: '🖼️', processor: 'image' },
        'image/gif': { ext: '.gif', icon: '🖼️', processor: 'image' },
        'image/webp': { ext: '.webp', icon: '🖼️', processor: 'image' },
        'application/pdf': { ext: '.pdf', icon: '📄', processor: 'pdf' },
        'application/msword': { ext: '.doc', icon: '📝', processor: 'docx' },
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': { ext: '.docx', icon: '📝', processor: 'docx' },
        'text/plain': { ext: '.txt', icon: '📃', processor: 'text' }
    },

    // Voice recognition
    VOICE_SILENCE_DELAY: 3000, // 3 seconds
    VOICE_MIN_LENGTH: 3, // Minimum characters

    // Character limits
    MAX_CHARS: 4000
};
