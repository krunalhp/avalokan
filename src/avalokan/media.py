import json
import math
import subprocess
from pathlib import Path

FORMATS = {".mp4": "mov", ".mov": "mov", ".mkv": "matroska"}


def probe(path, format, max_duration=600):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                format,
                "-select_streams",
                "v:0",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=15,
            check=True,
        )
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        duration = float(stream.get("duration", metadata["format"].get("duration", 0)))
        width, height = int(stream["width"]), int(stream["height"])
        if not math.isfinite(duration) or not 0 < duration <= max_duration:
            raise ValueError("Clip must have a known duration between 0 and 600 seconds")
        if width < 16 or height < 16 or width > 3840 or height > 2160:
            raise ValueError("Clip dimensions must be between 16×16 and 3840×2160")
        if any(abs(float(s.get("rotation", 0))) > 0 for s in stream.get("side_data_list", [])):
            raise ValueError("Rotated video is unsupported; export an upright CCTV clip")
        if stream.get("codec_name") not in {"h264", "hevc", "mpeg4", "vp8", "vp9", "av1"}:
            raise ValueError("Unsupported video codec")
        return {
            "duration_s": duration,
            "width": width,
            "height": height,
            "codec": stream["codec_name"],
        }
    except (subprocess.SubprocessError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read video; use a valid MP4, MOV or MKV clip") from exc


def prepare_playback(media):
    """Remux H.264; otherwise make a one-thread review proxy, never overwrite source.

    The engine checks that the playable copy starts at zero. VFR proxy encoding
    preserves presentation spacing; events use the source's first-frame offset.
    """
    source = Path(media["path"])
    destination = source.with_suffix(".playback.mp4")
    temporary = source.with_suffix(".partial.mp4")
    if destination.exists():
        return destination
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-threads",
        "1",
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        media["format"],
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
    ]
    if media["codec"] == "h264":
        command += ["-c:v", "copy"]
    else:
        command += [
            "-vf",
            "setpts=PTS-STARTPTS",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "passthrough",
            "-threads",
            "1",
        ]
    command += ["-movflags", "+faststart", str(temporary)]
    try:
        subprocess.run(command, capture_output=True, timeout=180, check=True)
        temporary.replace(destination)
    except subprocess.SubprocessError as exc:
        raise ValueError("Could not prepare browser playback within its resource limit") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return destination
