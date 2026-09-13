# ប្រើ Python 3.10 ដែលគាំទ្រ moviepy បានល្អ
FROM python:3.10-slim

# ដំឡើង FFmpeg ដែលចាំបាច់សម្រាប់ moviepy
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# កំណត់ថតធ្វើការ
WORKDIR /app

# ចម្លង requirements.txt និងដំឡើង
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ចម្លងកូដទាំងអស់
COPY . .

# បើក port 10000 (Render ប្រើ port នេះ)
EXPOSE 10000

# បញ្ជាសម្រាប់ដំណើរការ
CMD gunicorn --bind 0.0.0.0:10000 app:app
