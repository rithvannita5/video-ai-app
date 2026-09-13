from flask import Flask, render_template, request, send_file
import os
import time

# គាំទ្រទាំង MoviePy v2.x និង v1.x
try:
    from moviepy import VideoFileClip  # v2.x
except ImportError:
    from moviepy.editor import VideoFileClip  # v1.x

app = Flask(__name__)

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
    video_file = request.files.get('video')
    
    # ការកំណត់ចំនួននាទីក្នុងមួយផ្នែក
    minutes_raw = request.form.get('minutes_per_part', '').strip()
    if minutes_raw == '' or minutes_raw is None:
        minutes_per_part = None
    else:
        try:
            minutes_per_part = float(minutes_raw)
            if minutes_per_part <= 0:
                minutes_per_part = None
        except (ValueError, TypeError):
            minutes_per_part = None

    target_language = request.form.get('target_language', 'km')
    voice_gender = request.form.get('voice_gender', 'female')

    # ពិនិត្យថាមាន Upload វីដេអូ
    if not video_file or video_file.filename == '':
        return "សូម Upload វីដេអូជាមុនសិន", 400

    # រក្សាទុកឯកសារ
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
    video_file.save(input_path)

    try:
        clip = VideoFileClip(input_path)
        duration = clip.duration
        base_name = os.path.splitext(os.path.basename(input_path))[0]

        output_files = []

        if minutes_per_part is None:
            # មិនកាត់ - ចេញវីដេអូពេញលេញ
            output_filename = f"{base_name}_full.mp4"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
            
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )
            output_files.append(output_path)
        else:
            # កាត់ជាចំណែកៗ
            part_duration = minutes_per_part * 60
            num_parts = int(duration // part_duration)
            if duration % part_duration > 0:
                num_parts += 1

            for i in range(num_parts):
                start = i * part_duration
                end = min((i + 1) * part_duration, duration)

                output_filename = f"{base_name}_part{i+1}.mp4"
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

                # គាំទ្រទាំង subclipped (v2) និង subclip (v1)
                try:
                    sub_clip = clip.subclipped(start, end)
                except AttributeError:
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

        return send_file(
            output_files[0],
            as_attachment=True,
            download_name=os.path.basename(output_files[0])
        )

    except Exception as e:
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {str(e)}", 500


if __name__ == '__main__':
    app.run(debug=True)
