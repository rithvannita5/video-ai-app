from flask import Flask, render_template, request, send_file
import os
import subprocess
import time
import traceback
import logging
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip

app = Flask(__name__)

# --- Logging setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = '/tmp'
OUTPUT_FOLDER = '/tmp/output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER


POT_PROVIDER_SERVER_PATH = "/opt/bgutil-provider/server/build/main.js"


def start_pot_provider():
    """
    ចាប់ផ្តើម bgutil POT provider server ។

    សំខាន់៖ pip package 'bgutil-ytdlp-pot-provider' គឺជា *plugin* ខាង yt-dlp
    ដែលនិយាយទៅ server ប៉ុណ្ណោះ — វាគ្មាន module Python ដែលអាចហៅ
    `python -m bgutil_ytdlp_pot_provider server` បានឡើយ។ Server ពិតប្រាកដ
    ជា Node.js application ដាច់ដោយឡែក ដែល Dockerfile បាន clone+build
    ទុកជាមុននៅ /opt/bgutil-provider/server/build/main.js ។
    """
    if not os.path.exists(POT_PROVIDER_SERVER_PATH):
        logger.error(
            "POT Provider server file not found at %s — did the Docker build step "
            "(git clone + npm ci + npx tsc) succeed?",
            POT_PROVIDER_SERVER_PATH,
        )
        return

    try:
        proc = subprocess.Popen(
            ["node", POT_PROVIDER_SERVER_PATH, "--port", "4416"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(3)

        # ពិនិត្យថា process នៅតែដំណើរការ (មិនទាន់ crash)
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=2)
            logger.error(f"POT Provider crashed on startup. stdout={out} stderr={err}")
        else:
            logger.info("POT Provider started successfully (pid=%s)", proc.pid)
    except Exception:
        logger.error("POT Provider failed to start:\n%s", traceback.format_exc())


start_pot_provider()


def download_video_from_link(video_url, output_path):
    # 'impersonate' ត្រូវជា object ImpersonateTarget មិនមែន string ធម្មតាទេ
    # ពេលហៅ yt_dlp.YoutubeDL() ដោយផ្ទាល់ (មិនមែនតាម CLI) — បើផ្ញើ string ត្រង់ៗ
    # វានឹង crash ជាមួយ AssertionError ក្នុង is_supported_target().
    try:
        impersonate_target = ImpersonateTarget.from_str('chrome')
    except Exception:
        logger.warning("Could not build ImpersonateTarget('chrome'); disabling impersonation")
        impersonate_target = None

    ydl_opts = {
        'format': 'mp4/bestvideo+bestaudio/best',
        'outtmpl': output_path,
        'quiet': False,
        'verbose': True,
        'no_warnings': False,
        'ignoreerrors': False,
        'impersonate': impersonate_target,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        'js_runtimes': {'node': {}},
        'extractor_args': {
            'youtubepot-bgutilhttp': {
                'base_url': 'http://127.0.0.1:4416'
            }
        },
        # ផ្ញើ log របស់ yt-dlp ចូល logger របស់យើង ជំនួសឲ្យបាត់ទៅក្នុង stdout ធម្មតា
        'logger': logger,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if info is None:
                raise Exception("yt-dlp មិនអាចទាញយកព័ត៌មានវីដេអូបានទេ (info=None)")
        return output_path
    except yt_dlp.utils.DownloadError as e:
        logger.error("yt-dlp DownloadError:\n%s", traceback.format_exc())
        raise Exception(f"DownloadError: {str(e) or repr(e)}")
    except Exception as e:
        # បង្ហាញ traceback ពេញលេញទៅ log (Render logs / console)
        logger.error("Unexpected error while downloading:\n%s", traceback.format_exc())
        # ដាក់ type(e).__name__ ដើម្បីកុំឲ្យសារនៅទទេ ពេល str(e) ជាទទេ
        detail = str(e) or repr(e) or "គ្មានព័ត៌មានលម្អិត (empty exception message)"
        raise Exception(f"GeneralError: {type(e).__name__}: {detail}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process_video():
    video_file = request.files.get('video')
    video_link = request.form.get('video_link', '').strip()

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

    input_path = None

    if video_file and video_file.filename != '':
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_file.filename)
        video_file.save(input_path)

    elif video_link:
        try:
            filename = f"downloaded_{int(time.time())}.mp4"
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            download_video_from_link(video_link, input_path)

            if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
                return "ការទាញយកវីដេអូបរាជ័យ ឬ ឯកសារទទេ", 400

        except Exception as e:
            logger.error("Failed to download from link:\n%s", traceback.format_exc())
            return f"មិនអាចទាញយកវីដេអូពី Link បានទេ: {str(e)}", 400
    else:
        return "សូម Upload វីដេអូ ឬ ដាក់ Link ជាមុនសិន", 400

    try:
        clip = VideoFileClip(input_path)
        duration = clip.duration
        base_name = os.path.splitext(os.path.basename(input_path))[0]

        output_files = []

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

    except Exception:
        logger.error("Failed while cutting/processing video:\n%s", traceback.format_exc())
        return f"មានបញ្ហាក្នុងការកាត់វីដេអូ: {traceback.format_exc(limit=1)}", 500


if __name__ == '__main__':
    app.run(debug=True)
