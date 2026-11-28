"""Narration (Piper neural TTS) -> durations -> record app with synced actions -> mux. Run from demo_video/."""
import json, os, subprocess
PIPER = os.path.expanduser("~/.piper_venv/bin/python")
txt = json.load(open("narration.json")); os.makedirs("audio", exist_ok=True)
dur = []
for i, t in enumerate(txt):
    subprocess.run([PIPER, "-m", "piper", "-m", "voices/en_US-lessac-medium.onnx", "--length-scale", "1.08", "-f", f"audio/s{i}.wav"], input=t, text=True, check=True, capture_output=True)
    dur.append(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"audio/s{i}.wav"], capture_output=True, text=True).stdout))
json.dump(dur, open("durations.json", "w")); print("durations", [round(d) for d in dur])
subprocess.run(["node", "record.js"], check=True)
fr = json.load(open("frames.json")); st = json.load(open("starts.json"))
with open("concat.txt", "w") as f:
    for i, (n, t) in enumerate(fr):
        d = (fr[i + 1][1] - t) if i + 1 < len(fr) else 0.05
        f.write(f"file '{n}'\nduration {max(d, 0.001):.4f}\n")
    f.write(f"file '{fr[-1][0]}'\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "26", "silent.mp4"], check=True)
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", "silent.mp4"]; fl = []
for i, s in enumerate(st):
    cmd += ["-i", f"audio/s{i}.wav"]; ms = int(s * 1000); fl.append(f"[{i+1}:a]adelay={ms}|{ms}[a{i}]")
fl.append("".join(f"[a{i}]" for i in range(len(st))) + f"amix=inputs={len(st)}:normalize=0[aout]")
cmd += ["-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "TaskFactory_Demo.mp4"]
subprocess.run(cmd, check=True)
