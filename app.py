from flask import Flask, render_template, request, send_file
import os
import requests

try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'
OUTPUT_FOLDER = '/tmp/output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER


def download_video_from_link(video_url, output_path):
    """
    ប្រើ Cobalt API ដើម្បីទាញយកវីដេអូពី Link
    គាំទ្រ YouTube, Dailymotion, Twitter, TikTok, Instagram ជាដើម
    """
    # Cobalt API Instance (ឥតគិតថ្លៃ)
    api_url = "https://api.cobalt.tools/api/json"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    payload = {
        "url": video_url,
        "vQuality": "720",  # គុណភាពវីដេអូ
        "isAudioOnly": False,
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "error":
            raise Exception(data.get("text", "Unknown error from Cobalt API"))
        
        # Cobalt ត្រឡប់ URL នៃវីដេអូដែលបានរៀបចំរួច
        download_url = data.get("url")
        if not download_url:
            raise Exception("Cobalt API មិនបានត្រឡប់ URL ទាញយកទេ")
        
        # ទាញយកវីដេអូពី URL នោះ
        video_response = requests.get(download_url, stream=True, timeout=120)
        video_response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return output_path
    
    except Exception as e:
        raise Exception(f"Cobalt API Error: {str(e)}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process_video():
    video_file = request.files.get('video')
    video_link = request.form.get('video_link', '').strip()
    
    # កែ: បើមិនបំពេញនាទី ឱ្យចេញវីដេអូពេញលេញធម្មតា
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

    input_path = None

    # ជម្រើសទី 1: Upload ឯកសារ
    if video_file and video_file.filename != '':
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
        video_file.save(input_path)

    # ជម្រើសទី 2: ដាក់ Link (ប្រើ Cobalt API)
    elif video_link:
        try:
            # កំណត់ឈ្មោះឯកសារតាមពេលវេលា
            import time
            filename = f"downloaded_{int(time.time())}.mp4"
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            download_video_from_link(video_link, input_path)
            
            if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
                return "ការទាញយកវីដេអូបរាជ័យ ឬ ឯកសារទទេ", 400
                
        except Exception as e:
            return f"មិនអាចទាញយកវីដេអូពី Link បានទេ: {str(e)}", 400
    else:
        return "សូម Upload វីដេអូ ឬ ដាក់ Link ជាមុនសិន", 400

    try:
        clip = VideoFileClip(input_path)
        duration = clip.duration
        base_name = os.path.splitext(os.path.basename(input_path))[0]

        output_files = []

        # បើ minutes_per_part ជា None → មិនកាត់ ចេញវីដេអូពេញលេញ
        if minutes_per_part is None:
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
