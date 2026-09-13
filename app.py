from flask import Flask, render_template, request, send_file
import os
import subprocess
import time
import traceback
import logging
import asyncio
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
import edge_tts
from pydub import AudioSegment

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


DUB_WORKDIR = '/tmp/dub_work'
os.makedirs(DUB_WORKDIR, exist_ok=True)

# --- Whisper model (Speech-to-Text) ---
# ប្រើ 'base' ជា default ដើម្បីជៀសវាង OOM លើ Render free/starter tier (RAM កំណត់)។
# អាចប្តូរតាម environment variable WHISPER_MODEL_SIZE (tiny/base/small/medium)។
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")
_whisper_model = None


def get_whisper_model():
    """ផ្ទុក Whisper model តែម្តងគត់ (lazy singleton) ដើម្បីជៀសវាងផ្ទុកជាថ្មីរាល់ request។"""
    global _whisper_model
    if _whisper_model is None:
        logger.info("កំពុងផ្ទុក Whisper model (%s)...", WHISPER_MODEL_SIZE)
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        logger.info("Whisper model ផ្ទុករួចរាល់។")
    return _whisper_model


# --- Edge TTS voice mapping (សំឡេង AI តាមភាសា + ភេទ) ---
EDGE_VOICE_MAP = {
    "km": {"female": "km-KH-SreymomNeural", "male": "km-KH-PisethNeural"},
    "en": {"female": "en-US-JennyNeural", "male": "en-US-GuyNeural"},
    "th": {"female": "th-TH-PremwadeeNeural", "male": "th-TH-NiwatNeural"},
    "vi": {"female": "vi-VN-HoaiMyNeural", "male": "vi-VN-NamMinhNeural"},
    "zh": {"female": "zh-CN-XiaoxiaoNeural", "male": "zh-CN-YunxiNeural"},
}


def pick_voice(target_language, voice_gender):
    voices = EDGE_VOICE_MAP.get(target_language, EDGE_VOICE_MAP["en"])
    # ចំណាំ៖ ជម្រើស "both" (ស្រី+ប្រុស តាមតួអង្គ) ត្រូវការ speaker diarization
    # ដែលមិនទាន់អនុវត្តទេ — fallback ទៅសំឡេងស្រីជា default ។
    if voice_gender not in ("male", "female"):
        logger.warning("voice_gender='%s' មិនទាន់គាំទ្រការញែកតួអង្គ, ប្រើសំឡេងស្រី", voice_gender)
        return voices["female"]
    return voices.get(voice_gender, voices["female"])


async def _synthesize_segment_async(text, voice, out_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def synthesize_segment(text, voice, out_path):
    asyncio.run(_synthesize_segment_async(text, voice, out_path))


def dub_video(input_path, target_language, voice_gender, workdir):
    """
    ធ្វើការបកប្រែសំឡេងក្នុងវីដេអូទាំងមូល៖
    ១. ដកសំឡេងចេញពីវីដេអូ
    ២. Whisper ប្តូរសំឡេងទៅជាអក្សរ (transcribe + timestamps កម្រិត segment)
    ៣. បកប្រែអត្ថបទនីមួយៗទៅភាសាគោលដៅ (Google Translate)
    ៤. បង្កើតសំឡេង AI (edge-tts) សម្រាប់អត្ថបទដែលបានបកប្រែ
    ៥. តម្រឹមរយៈពេលឲ្យប្រហែលនឹងសំឡេងដើម រួចដាក់តាមពេលវេលា timestamp ដើម
    ៦. ជំនួសសំឡេងដើមក្នុងវីដេអូ

    ចំណាំ៖ សមកាលកម្មមាត់ (lip-sync) ត្រឹមតែកម្រិត segment ប៉ុណ្ណោះ មិនមែនល្អ
    ឥតខ្ចោះ១០០%ទេ ព្រោះមិនទាន់ធ្វើ word-level alignment ។
    """
    os.makedirs(workdir, exist_ok=True)
    audio_wav = os.path.join(workdir, "extracted_audio.wav")

    # ១. ដកសំឡេងចេញ
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", audio_wav],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"ffmpeg មិនអាចដកសំឡេងបានទេ: {result.stderr[-500:]}")

    # ២. Transcribe ជាមួយ Whisper
    model = get_whisper_model()
    segments_gen, info = model.transcribe(audio_wav, beam_size=5)
    segments = list(segments_gen)
    logger.info("Whisper detected language=%s (prob=%.2f), %d segments",
                info.language, info.language_probability, len(segments))

    if not segments:
        raise Exception("Whisper មិនអាចដកអត្ថបទចេញពីវីដេអូនេះបានទេ (គ្មានសំឡេងនិយាយច្បាស់?)")

    voice = pick_voice(target_language, voice_gender)
    translator = GoogleTranslator(source="auto", target=target_language)

    total_duration_ms = int(segments[-1].end * 1000) + 500
    final_audio = AudioSegment.silent(duration=total_duration_ms)

    for i, seg in enumerate(segments):
        text = seg.text.strip()
        if not text:
            continue

        # ៣. បកប្រែ
        try:
            translated = translator.translate(text)
        except Exception:
            logger.warning("បកប្រែ segment %d បរាជ័យ, ប្រើអត្ថបទដើម:\n%s", i, traceback.format_exc())
            translated = text

        if not translated:
            continue

        # ៤. បង្កើតសំឡេង AI
        seg_tts_path = os.path.join(workdir, f"seg_{i}.mp3")
        try:
            synthesize_segment(translated, voice, seg_tts_path)
        except Exception:
            logger.error("TTS បរាជ័យសម្រាប់ segment %d:\n%s", i, traceback.format_exc())
            continue

        try:
            tts_clip = AudioSegment.from_file(seg_tts_path)
        except Exception:
            logger.error("មិនអាចអានឯកសារ TTS សម្រាប់ segment %d", i)
            continue

        # ៥. តម្រឹមរយៈពេល ដើម្បីជៀសវាងសំឡេងជាន់គ្នា (បើ TTS វែងជាងដើមខ្លាំង)
        original_duration_ms = (seg.end - seg.start) * 1000
        if original_duration_ms > 0 and len(tts_clip) > original_duration_ms * 1.15:
            speed_factor = min(len(tts_clip) / original_duration_ms, 2.0)
            sped_path = os.path.join(workdir, f"seg_{i}_sped.mp3")
            speed_result = subprocess.run(
                ["ffmpeg", "-y", "-i", seg_tts_path, "-filter:a", f"atempo={speed_factor:.3f}", sped_path],
                capture_output=True, text=True
            )
            if speed_result.returncode == 0:
                tts_clip = AudioSegment.from_file(sped_path)

        start_ms = int(seg.start * 1000)
        final_audio = final_audio.overlay(tts_clip, position=start_ms)

    dubbed_audio_path = os.path.join(workdir, "dubbed_audio.mp3")
    final_audio.export(dubbed_audio_path, format="mp3")

    # ៦. ជំនួសសំឡេងដើមក្នុងវីដេអូ
    dubbed_video_path = os.path.join(workdir, "dubbed_video.mp4")
    mux_result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-i", dubbed_audio_path,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-shortest", dubbed_video_path],
        capture_output=True, text=True
    )
    if mux_result.returncode != 0:
        raise Exception(f"ffmpeg មិនអាចបញ្ចូលសំឡេងចូលវីដេអូបានទេ: {mux_result.stderr[-500:]}")

    return dubbed_video_path


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

    target_language = request.form.get('target_language', 'km').strip()
    voice_gender = request.form.get('voice_gender', 'female').strip()

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

    # --- ការបកប្រែសំឡេង + AI Voice ---
    # បើបរាជ័យ (ឧ. network issue ជាមួយ Google Translate/edge-tts) នឹងបន្ត
    # ដំណើរការជាមួយសំឡេងដើម ជាជាងធ្វើឲ្យ request បរាជ័យទាំងស្រុង។
    dub_dir = os.path.join(DUB_WORKDIR, f"job_{int(time.time())}")
    try:
        logger.info("កំពុងចាប់ផ្តើមបកប្រែសំឡេងទៅជា '%s' (voice=%s)...", target_language, voice_gender)
        dubbed_path = dub_video(input_path, target_language, voice_gender, dub_dir)
        input_path = dubbed_path
        logger.info("ការបកប្រែសំឡេងបានជោគជ័យ: %s", dubbed_path)
    except Exception:
        logger.error("ការបកប្រែសំឡេងបរាជ័យ, នឹងបន្តជាមួយសំឡេងដើម:\n%s", traceback.format_exc())

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
