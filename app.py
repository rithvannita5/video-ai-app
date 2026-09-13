from flask import Flask, render_template, request, send_file, jsonify
import os
import yt_dlp  # សម្រាប់ទាញយកវីដេអូពី Link
from moviepy import VideoFileClip

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'
OUTPUT_FOLDER = '/tmp/output'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    video_file = request.files.get('video')
    video_link = request.form.get('video_link', '').strip()
    minutes_per_part = float(request.form.get('minutes_per_part', 10))
    
    input_path = None
    
    # ជម្រើសទី 1: បើអ្នកប្រើ Upload ឯកសារ
    if video_file and video_file.filename != '':
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
        video_file.save(input_path)
    
    # ជម្រើសទី 2: បើអ្នកប្រើដាក់ Link
    elif video_link:
        try:
            ydl_opts = {
                'format': 'mp4',
                'outtmpl': os.path.join(app.config['UPLOAD_FOLDER'], '%(title)s.%(ext)s'),
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_link, download=True)
                input_path = ydl.prepare_filename(info)
        except Exception as e:
            return f"មិនអាចទាញយកវីដេអូពី Link បានទេ: {str(e)}", 400
    else:
        return "សូម Upload វីដេអូ ឬ ដាក់ Link ជាមុនសិន", 400

    try:
        # កាត់វីដេអូជាចំណែកៗ
        clip = VideoFileClip(input_path)
        duration = clip.duration  # រយៈពេលវីដេអូសរុបគិតជាវិនាទី
        part_duration = minutes_per_part * 60
        num_parts = int(duration // part_duration) + (1 if duration % part_duration > 0 else 0)
        
        output_files = []
        for i in range(num_parts):
            start = i * part_duration
            end = min((i + 1) * part_duration, duration)
            
            # បង្កើតឈ្មោះឯកសារសម្រាប់ផ្នែកនីមួយៗ
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_filename = f"{base_name}_part{i+1}.mp4"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
            
            sub_clip = clip.subclipped(start, end)
            sub_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
            sub_clip.close()
            output_files.append(output_path)
        
        clip.close()
        
        # សម្រាប់ការសាកល្បង យើងនឹងផ្ញើឯកសារដំបូងត្រឡប់ទៅវិញ
        # (នៅពេលក្រោយយើងនឹងធ្វើឱ្យវាបង្ហាញបញ្ជីឯកសារទាំងអស់)
        return send_file(output_files[0], as_attachment=True, download_name=os.path.basename(output_files[0]))

    except Exception as e:
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
