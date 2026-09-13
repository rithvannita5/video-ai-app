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

EXPOSE 10000

CMD gunicorn --bind 0.0.0.0:10000 app:app
