"""Revoice the finished film using the project's configured Volcengine adapter."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.podcast_audio import VolcengineNarrationSynthesizer

HERE = Path(__file__).resolve().parent
OUT = HERE / 'public' / 'volcengine-male'
OUT.mkdir(parents=True, exist_ok=True)
VOICE = 'zh_male_m191_uranus_bigtts'
SEGMENTS = [
    (0, 7, '孩子的故事，长辈哼的歌，还有妈妈在厨房里的一声笑。'),
    (7, 6, '这些声音，常常来不及保存，就消失在日常里。'),
    (13, 7, '家庭录音豆，替这一家人，轻轻记下它们。'),
    (20, 8, '它找到值得珍藏的片段，经家人确认，把一句原声，变成声音明信片。'),
    (28, 6, '再把几段原声串成故事，收进家庭留声机。'),
    (34, 5, '家人可以聆听、回应，也可以私密地分享。'),
    (39, 6, '多年后，他们再次听见彼此。每一声，都值得被记住。'),
]

def run(args):
    return subprocess.check_output(args, stderr=subprocess.PIPE).decode().strip()

settings = Settings(_env_file=ROOT / 'backend' / '.env').model_copy(update={
    'volcengine_tts_voice': VOICE,
    'volcengine_tts_resource_id': 'seed-tts-2.0',
    'volcengine_tts_speech_rate': -8,
    'volcengine_tts_timeout_seconds': 90,
    'podcast_tts_fallback_to_system': False,
})
adapter = VolcengineNarrationSynthesizer(settings)
if not adapter.available:
    raise SystemExit('Volcengine credentials are not configured.')

def generate(index):
    start, duration, text = SEGMENTS[index]
    stem = OUT / f'raw-{index}'
    raw = stem.with_suffix('.mp3')
    if not raw.exists():
        adapter.synthesize(text, stem)
    length = float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(raw)]))
    speed = max(1, length / (duration - .65))
    fitted = OUT / f'voice-{index}.wav'
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-af',
         f'atempo={speed:.6f},loudnorm=I=-18:TP=-2:LRA=7,afade=t=in:d=0.025,afade=t=out:st={length/speed-.07:.3f}:d=0.07',
         '-ar', '48000', '-ac', '1', str(fitted)])
    print(f'Segment {index+1}/7: {length:.2f}s, timing factor {speed:.3f}', flush=True)
    return {'index': index, 'start': start, 'duration': duration, 'raw_seconds': length, 'timing_factor': speed, 'text': text}

with ThreadPoolExecutor(max_workers=2) as pool:
    records = list(pool.map(generate, range(7)))

cmd = ['ffmpeg', '-v', 'error', '-y']
for i in range(7):
    cmd += ['-i', str(OUT / f'voice-{i}.wav')]
cmd += ['-i', str(HERE / 'public' / 'music.wav')]
filters = []
for i, (start, duration, _) in enumerate(SEGMENTS):
    filters.append(f'[{i}:a]adelay={round((start+.30)*1000)}:all=1[a{i}]')
filters.append('[7:a]volume=0.22[music]')
filters.append(''.join(f'[a{i}]' for i in range(7)) + '[music]amix=inputs=8:duration=longest:normalize=0,alimiter=limit=0.891:level=false,apad=whole_len=2160000,atrim=end_sample=2160000,asetpts=N/SR/TB[out]')
cmd += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-t', '45', '-ar', '48000', str(OUT / 'mix.wav')]
run(cmd)
destination = ROOT / 'docs' / 'showcase' / 'family-voice-memories-45s-volcengine-male.mp4'
run(['ffmpeg', '-v', 'error', '-y', '-i', str(ROOT / 'docs' / 'showcase' / 'family-voice-memories-45s.mp4'),
     '-i', str(OUT / 'mix.wav'), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
     '-t', '45', '-movflags', '+faststart', str(destination)])
(OUT / 'manifest.json').write_text(json.dumps({'provider': adapter.provider, 'voice': VOICE, 'resource': settings.volcengine_tts_resource_id, 'segments': records}, ensure_ascii=False, indent=2))
print(f'COMPLETE: {destination}', flush=True)
