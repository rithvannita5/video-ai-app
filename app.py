from flask import Flask, render_template, request, send_file
import os
import yt_dlp

# ព្យាយាម import ទាំងពីរជំនាន់
try:
    from moviepy import VideoFileClip  # MoviePy v2.x
except ImportError:
    from moviepy.editor import VideoFileClip  # MoviePy v1.x

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
    video_link = request.form.get('video_link', '').strip()
    
    # កែបញ្ហា ValueError: បើទទេ ឬ មិនត្រឹមត្រូវ ឱ្យប្រើ 10 ជំនួស
    try:
        minutes_raw = request.form.get('minutes_per_part', '10').strip()
        minutes_per_part = float(minutes_raw) if minutes_raw else 10.0
        if minutes_per_part <= 0:
            minutes_per_part = 10.0
    except (ValueError, TypeError):
        minutes_per_part = 10.0

    target_language = request.form.get('target_language', 'km')
    voice_gender = request.form.get('voice_gender', 'female')

    input_path = None

    # ជម្រើសទី 1: Upload ឯកសារ
    if video_file and video_file.filename != '':
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
        video_file.save(input_path)

    # ជម្រើសទី 2: ដាក់ Link
    elif video_link:
        try:
            ydl_opts = {
                'format': 'mp4/bestvideo+bestaudio/best',
                'outtmpl': os.path.join(app.config['UPLOAD_FOLDER'], '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_link, download=True)
                input_path = ydl.prepare_filename(info)
        except Exception as e:
            return f"មិនអាចទាញយកវីដេអូពី Link បានទេ: {str(e)}", 400
    else:
        return "សូម Upload វីដេអូ ឬ ដាក់ Link ជាមុនសិន", 400

    try:
        clip = VideoFileClip(input_path)
        duration = clip.duration
        part_duration = minutes_per_part * 60

        num_parts = int(duration // part_duration)
        if duration % part_duration > 0:
            num_parts += 1

        output_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]

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
