from flask import Flask, render_template, request, send_file
from moviepy import VideoFileClip
import os

app = Flask(__name__)

# កំណត់ថតសម្រាប់ផ្ទុកឯកសារបណ្ដោះអាសន្ន (Render អនុញ្ញាតឱ្យប្រើ /tmp)
UPLOAD_FOLDER = '/tmp'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    # បង្ហាញផ្ទាំង HTML ដែលយើងទើបបង្កើត
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    # 1. ទទួលឯកសារវីដេអូពី Form
    video = request.files['video']
    start_min = float(request.form['start_min'])
    end_min = float(request.form['end_min'])
    
    if video.filename == '':
        return "គ្មានឯកសារត្រូវបានជ្រើសរើសទេ", 400

    # 2. រក្សាទុកឯកសារបណ្ដោះអាសន្ន
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
    output_filename = f"trimmed_{video.filename}"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    video.save(input_path)

    try:
        # 3. ប្រើ MoviePy ដើម្បីកាត់វីដេអូ
        clip = VideoFileClip(input_path)
        # បំប្លែងនាទីទៅជាវិនាទី
        start_time = start_min * 60
        end_time = end_min * 60
        
        # កាត់វីដេអូ
        trimmed_clip = clip.subclipped(start_time, end_time)
        
        # សរសេរឯកសារថ្មី (ប្រើ codec ស្រាលដើម្បីកុំឱ្យធ្ងន់)
        trimmed_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
        # បិទឯកសារដើម្បីសន្សំសំចៃ Memory
        clip.close()
        trimmed_clip.close()

        # 4. ផ្ញើឯកសារត្រឡប់ទៅអ្នកប្រើវិញ
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
