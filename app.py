from flask import Flask, render_template, request, send_file
import os
from moviepy.editor import VideoFileClip

app = Flask(__name__)

# កំណត់ថតផ្ទុកឯកសារបណ្ដោះអាសន្ន (Render អនុញ្ញាត /tmp)
UPLOAD_FOLDER = '/tmp'
OUTPUT_FOLDER = '/tmp/output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process_video():
    # ទទួលឯកសារពី Form
    video_file = request.files.get('video')
    minutes_per_part = float(request.form.get('minutes_per_part', 10))
    target_language = request.form.get('target_language', 'km')
    voice_gender = request.form.get('voice_gender', 'female')

    # ពិនិត្យថាមាន Upload វីដេអូ
    if not video_file or video_file.filename == '':
        return "សូម Upload វីដេអូជាមុនសិន", 400

    # រក្សាទុកឯកសារ
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
    video_file.save(input_path)

    try:
        # បើកវីដេអូដោយ MoviePy
        clip = VideoFileClip(input_path)
        duration = clip.duration  # រយៈពេលសរុបគិតជាវិនាទី
        part_duration = minutes_per_part * 60  # បំប្លែងនាទីទៅវិនាទី

        # គណនាចំនួនផ្នែកដែលត្រូវកាត់
        num_parts = int(duration // part_duration)
        if duration % part_duration > 0:
            num_parts += 1

        output_files = []

        # កាត់វីដេអូជាចំណែកៗ
        for i in range(num_parts):
            start = i * part_duration
            end = min((i + 1) * part_duration, duration)

            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_filename = f"{base_name}_part{i+1}.mp4"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            # ប្រើ subclip សម្រាប់ MoviePy 1.0.3
            sub_clip = clip.subclip(start, end)
            sub_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )
            sub_clip.close()
            output_files.append(output_path)

        clip.close()

        # ជាបណ្ដោះអាសន្ន ផ្ញើឯកសារដំបូងត្រឡប់ទៅវិញ
        # (នៅពេលក្រោយយើងនឹងធ្វើឱ្យវាបង្ហាញបញ្ជីឯកសារទាំងអស់)
        return send_file(
            output_files[0],
            as_attachment=True,
            download_name=os.path.basename(output_files[0])
        )

    except Exception as e:
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {str(e)}", 500


if __name__ == '__main__':
    app.run(debug=True)
