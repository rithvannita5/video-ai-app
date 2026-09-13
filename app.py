# app.py - ជំនាន់កែសម្រួលសម្រាប់ទាំង MoviePy v1 និង v2
from flask import Flask, render_template, request, send_file
import os

try:
    # សម្រាប់ MoviePy v2.x (ជំនាន់ថ្មី)
    from moviepy import VideoFileClip
except ImportError:
    # សម្រាប់ MoviePy v1.x (ជំនាន់ចាស់)
    from moviepy.editor import VideoFileClip

app = Flask(__name__)

# កំណត់ថតសម្រាប់ផ្ទុកឯកសារបណ្ដោះអាសន្ន
UPLOAD_FOLDER = '/tmp'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    video = request.files['video']
    start_min = float(request.form['start_min'])
    end_min = float(request.form['end_min'])
    
    if video.filename == '':
        return "គ្មានឯកសារត្រូវបានជ្រើសរើសទេ", 400

    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
    output_filename = f"trimmed_{video.filename}"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    video.save(input_path)

    try:
        clip = VideoFileClip(input_path)
        
        start_time = start_min * 60
        end_time = end_min * 60
        
        # ចំណាំ: v2 ប្រើ subclipped(), v1 ប្រើ subclip()
        try:
            trimmed_clip = clip.subclipped(start_time, end_time)
        except AttributeError:
            trimmed_clip = clip.subclip(start_time, end_time)
        
        trimmed_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
        clip.close()
        trimmed_clip.close()

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
