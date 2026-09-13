FROM python:3.11-slim

# ដំឡើង FFmpeg, git និង Node.js ជំនាន់ថ្មី (Node 22)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ពិនិត្យ Node.js version
RUN node --version && npm --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Clone + build bgutil POT provider server (Node.js) ---
# សំខាន់៖ pip package "bgutil-ytdlp-pot-provider" គឺជា plugin ខាង yt-dlp ប៉ុណ្ណោះ
# (មិនមែន server ទេ) ។ Server ពិតជា Node.js app ដាច់ដោយឡែក ត្រូវ clone+build ដោយខ្លួនឯង។
# ជំនាន់ tag ត្រូវផ្គូផ្គងជាមួយ pip package version ក្នុង requirements.txt (>=1.3.0)។
RUN git clone --depth 1 --branch 1.3.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-provider \
    && cd /opt/bgutil-provider/server \
    && npm ci \
    && npx tsc

COPY . .

# --- Prefetch Whisper model ---
# ទាញ model មុន ក្នុងពេល build ដើម្បីជៀសវាងកុំឲ្យ request ដំបូងចូលត្រូវរង់ចាំទាញ
# model (~150-500MB អាស្រ័យទំហំ) ដែលនឹងធ្វើឲ្យ timeout ។ ត្រូវផ្គូផ្គងជាមួយ
# WHISPER_MODEL_SIZE default ('base') ក្នុង app.py ។
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

EXPOSE 10000

# --timeout ត្រូវបង្កើនឲ្យវែងណាស់ ព្រោះ pipeline ថ្មីមាន download/upload + Whisper
# transcribe + translate + TTS ក្នុងមួយ segment + encode — សរុបអាចលើសពី ១៥ នាទី
# សម្រាប់វីដេអូវែងបន្តិច។ --workers 1 ដើម្បីជៀសវាង process ច្រើនប្រណាំងគ្នាប្រើ RAM
# លើ Render free/starter tier ។
CMD gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 1800 --graceful-timeout 1800 app:app
