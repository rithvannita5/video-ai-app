FROM python:3.10-slim

# ដំឡើង FFmpeg និង Node.js (សម្រាប់ POT Provider)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ដំឡើង bgutil POT Provider
RUN npm install -g bgutil-ytdlp-pot-provider

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# បើក port សម្រាប់ POT Provider និង Flask
EXPOSE 10000 4416

# ចាប់ផ្តើម POT Provider និង Flask ក្នុងពេលតែមួយ
CMD bgutil-pot server --port 4416 & gunicorn --bind 0.0.0.0:10000 app:app
