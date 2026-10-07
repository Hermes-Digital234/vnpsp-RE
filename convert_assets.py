#!/usr/bin/env python3
"""Convert VNDS assets into the binary formats our PSP engine reads.

    python3 convert_assets.py <game_dir> [--bitrate RATE] [--max-files N] [--force]
                               [--keep-sources] [--preview DIR]

Walks background/, foreground/ and sound/ under <game_dir> and writes
  .bpp  images: 8-bit paletted and swizzled, ready to use as a PSP texture
  .mp3  audio : 44100 Hz stereo, played by the PSP's hardware decoder
next to each source, then deletes the source: the converted file replaces it.
Asset names in script/*.scr are repointed at the new extensions.
Pass --keep-sources to keep the originals.

A folder holding more than --max-files files (default 1000) is split into numbered
subfolders (_00, _01, ...), and the names in the scripts are rewritten to match, e.g.
"setimg sprite.bpp" becomes "setimg _03/sprite.bpp". The split is recomputed on every
run, so adding files later and running again just rebalances the folders. Small folders
are left alone.

Assets converted by the previous version of this script (.bpp in the old BPP1
layout, raw .a8 audio) are upgraded too: .bpp files are rewritten in place and
.a8 files become .mp3. An .mp3 that is not already 44100 Hz stereo is re-encoded
in place. Those inputs were already lossy, so if you still have the original
images and sounds, converting from them gives better results.
"""

import argparse
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------- format constants
# Engine-facing formats. Everything that defines an output layout lives here.
#
# .bpp layout (little-endian), read by bpp.cpp:
#   0     4     magic "BPP8"
#   4     2     width            (real image size)
#   6     2     height
#   8     2     texture width    (power of two, >= 16, >= width)
#   10    2     texture height   (power of two, >= 16, >= height)
#   12    4     reserved (0)
#   16    1024  palette: 256 entries, R,G,B,A each (unused entries are 0)
#   1040  tw*th pixel data, one palette index per byte, swizzled in blocks of
#               16 bytes x 8 rows (the PSP's native texture layout). Padding beyond
#               the real image repeats the edge pixels.
BPP_MAGIC = b"BPP8"
BPP_HEADER = "<HHHHI"          # width, height, tex width, tex height, reserved
BPP_HEADER_BYTES = 16
CLUT_ENTRIES = 256
CLUT_BYTES = CLUT_ENTRIES * 4
TEX_MIN, TEX_MAX = 16, 512     # the GE cannot use textures larger than 512
BLOCK_W, BLOCK_H = 16, 8       # swizzle block size for 8-bit textures
BPP_SUFFIX = ".bpp"

# The previous formats, still accepted as input.
LEGACY_BPP_MAGIC = b"BPP1"
A8_SUFFIX = ".a8"              # raw unsigned 8-bit mono PCM
A8_RATE = 22050

# Every sound is an MP3 the PSP's hardware decoder can play. The engine requires
# exactly this sample rate and channel count.
MP3_SUFFIX = ".mp3"
MP3_RATE = 44100
MP3_CHANNELS = 2
MP3_CODEC = "libmp3lame"
DEFAULT_BITRATE = "96k"
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

IMAGE, AUDIO = "image", "audio"
FOLDERS = {"background": IMAGE, "foreground": IMAGE, "sound": AUDIO}
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
AUDIO_EXTS = {".aac", ".ogg", ".mp3", ".wav"}
# .bpp and .a8 are inputs too (old-format files from the previous script).
IMAGE_INPUT_EXTS = IMAGE_EXTS | {BPP_SUFFIX}
AUDIO_INPUT_EXTS = AUDIO_EXTS | {A8_SUFFIX}

LOG_NAME = "convert_assets.log"

# Folders with more files than this are split into numbered subfolders.
DEFAULT_MAX_FILES = 1000
BUCKET_RE = re.compile(r"^_\d+$")   # name of a split subfolder: _00, _01, ...

# VNDS scripts name their assets with the original extension, so the asset names in
# <game_dir>/script/*.scr have to be repointed at the converted files (and, for split
# folders, at the subfolder they now live in). Rewriting is done on raw bytes: the names
# are ASCII, so any script encoding stays intact.
SCRIPTS_GLOB = "**/*.scr"
SCR_ROOTS = {  # script command -> asset folder its first argument lives in
    b"bgload": "background",
    b"setimg": "foreground",
    b"delimg": "foreground",
    b"sound": "sound",
    b"music": "sound",
    b"se": "sound",
    b"stopse": "sound",
}
SCR_REF = re.compile(rb"(?im)^(\s*(" + b"|".join(SCR_ROOTS) + rb")\s+)(\S+)")
CONVERTED_EXT = {  # source extension -> converted extension
    ext: out
    for exts, out in ((IMAGE_EXTS, BPP_SUFFIX), (AUDIO_INPUT_EXTS, MP3_SUFFIX))
    for ext in exts
}


def target_for(kind, src):
    """Output path for a source file, or None if its extension is not ours.

    The result can equal src (an old-format .bpp, or an .mp3): those are upgraded
    in place.
    """
    if kind == IMAGE and src.suffix.lower() in IMAGE_INPUT_EXTS:
        return src.with_suffix(BPP_SUFFIX)
    if kind == AUDIO and src.suffix.lower() in AUDIO_INPUT_EXTS:
        return src.with_suffix(MP3_SUFFIX)
    return None


def collect_jobs(game_dir):
    """Return [(kind, path)] for every file inside background/, foreground/, sound/."""
    jobs, stack = [], [(game_dir, None)]
    while stack:
        folder, kind = stack.pop()
        with os.scandir(folder) as scan:
            entries = sorted(scan, key=lambda e: e.name.lower())
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                sub = kind or FOLDERS.get(entry.name.lower())
                if sub:
                    stack.append((Path(entry.path), sub))
            elif entry.is_file(follow_symlinks=False) and kind:
                jobs.append((kind, Path(entry.path)))
    return sorted(jobs, key=lambda job: str(job[1]).lower())


# ------------------------------------------------------------------------ images

def pow2_at_least(value):
    """Smallest power of two >= value, never below the GE's minimum texture size."""
    size = TEX_MIN
    while size < value:
        size <<= 1
    return size


def swizzle(data, tw, th):
    """Row-major 8-bit pixels -> the PSP's layout: 16x8 pixel blocks, left to right,
    top to bottom, each block stored row by row."""
    out = bytearray()
    for by in range(th // BLOCK_H):
        for bx in range(tw // BLOCK_W):
            for j in range(BLOCK_H):
                start = (by * BLOCK_H + j) * tw + bx * BLOCK_W
                out += data[start : start + BLOCK_W]
    return bytes(out)


def unswizzle(data, tw, th):
    """Inverse of swizzle, used to preview converted images."""
    out = bytearray(tw * th)
    pos = 0
    for by in range(th // BLOCK_H):
        for bx in range(tw // BLOCK_W):
            for j in range(BLOCK_H):
                start = (by * BLOCK_H + j) * tw + bx * BLOCK_W
                out[start : start + BLOCK_W] = data[pos : pos + BLOCK_W]
                pos += BLOCK_W
    return bytes(out)


def quantize(rgba):
    """Return (indices, palette) for an RGBA image: one byte per pixel and exactly
    CLUT_BYTES of R,G,B,A palette (unused entries zero).

    Images with transparency use the octree quantizer, the only one Pillow supports
    for RGBA, and keep their partial alpha in the palette. Opaque images use median
    cut with dithering, which looks much better on gradients and photos.
    """
    if rgba.getchannel("A").getextrema()[0] < 255:
        indexed = rgba.quantize(colors=CLUT_ENTRIES, method=Image.Quantize.FASTOCTREE)
        flat = indexed.getpalette("RGBA")
    else:
        indexed = rgba.convert("RGB").quantize(
            colors=CLUT_ENTRIES, method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.FLOYDSTEINBERG)
        rgb = indexed.getpalette("RGB")
        flat = []
        for i in range(0, len(rgb), 3):
            flat += rgb[i : i + 3] + [255]
    return indexed.tobytes(), bytes(flat[:CLUT_BYTES]).ljust(CLUT_BYTES, b"\x00")


def resize_for_psp(image):
    """Downscale an image proportionally when either dimension exceeds the PSP limit."""
    width, height = image.size
    if width <= TEX_MAX and height <= TEX_MAX:
        return image, (width, height)

    scale = min(TEX_MAX / width, TEX_MAX / height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS), (width, height)


def build_bpp(image):
    """Pack a Pillow image into .bpp bytes: header, palette, swizzled pixels."""
    rgba = image.convert("RGBA")  # JPEG has no alpha, so this fills in 255
    rgba, _ = resize_for_psp(rgba)
    width, height = rgba.size
    tw, th = pow2_at_least(width), pow2_at_least(height)

    indices, palette = quantize(rgba)

    # Pad to the texture size by repeating the edge pixels, so the linear filter never
    # blends the picture with garbage along its border.
    rows = []
    for y in range(th):
        row = indices[min(y, height - 1) * width : (min(y, height - 1) + 1) * width]
        rows.append(row + row[-1:] * (tw - width))

    header = BPP_MAGIC + struct.pack(BPP_HEADER, width, height, tw, th, 0)
    return header + palette + swizzle(b"".join(rows), tw, th)


def decode_bpp1(path):
    """Read a file in the previous BPP1 layout (4/8/32 bpp) into a Pillow image.

    BPP1 header: magic, u16 width, u16 height, u8 bpp, u8 reserved, u16 palette entry
    count, then R,G,B,A per entry, then row-major pixels (4 bpp: two per byte, left
    pixel in the low nibble, rows padded to a whole byte).
    """
    data = path.read_bytes()
    if data[:4] != LEGACY_BPP_MAGIC:
        raise ValueError("not a .bpp file in a known format")
    width, height, bpp, _, entries = struct.unpack("<HHBBH", data[4:12])
    if bpp not in (4, 8, 32):
        raise ValueError(f"unsupported bpp {bpp}")
    palette = [data[12 + i * 4 : 16 + i * 4] for i in range(entries)]
    pixels = data[12 + entries * 4 :]
    if bpp == 32:
        return Image.frombytes("RGBA", (width, height), pixels)
    out = bytearray()
    stride = width if bpp == 8 else (width + 1) // 2
    for y in range(height):
        for x in range(width):
            if bpp == 8:
                out += palette[pixels[y * width + x]]
            else:
                byte = pixels[y * stride + (x >> 1)]
                out += palette[(byte & 0x0F) if x % 2 == 0 else byte >> 4]
    return Image.frombytes("RGBA", (width, height), bytes(out))


def decode_bpp(path):
    """Inverse of build_bpp: read a BPP8 file back into a Pillow image."""
    data = path.read_bytes()
    if data[:4] != BPP_MAGIC:
        raise ValueError("not a BPP8 file")
    width, height, tw, th, _ = struct.unpack(BPP_HEADER, data[4:BPP_HEADER_BYTES])
    palette = data[BPP_HEADER_BYTES : BPP_HEADER_BYTES + CLUT_BYTES]
    pixels = data[BPP_HEADER_BYTES + CLUT_BYTES :]
    if len(pixels) != tw * th:
        raise ValueError("truncated pixel data")
    linear = unswizzle(pixels, tw, th)
    out = bytearray()
    for y in range(height):
        for index in linear[y * tw : y * tw + width]:
            out += palette[index * 4 : index * 4 + 4]
    return Image.frombytes("RGBA", (width, height), bytes(out))


def convert_image(src, out):
    """Write out.bpp from an image file (or from an old-format .bpp)."""
    if src.suffix.lower() == BPP_SUFFIX:
        image = decode_bpp1(src)
        original_size = image.size
        data = build_bpp(image)
        image.close()
    else:
        with Image.open(src) as image:
            original_size = image.size
            data = build_bpp(image)

    width, height = struct.unpack(BPP_HEADER, data[4:BPP_HEADER_BYTES])[0:2]
    tmp = tmp_path(out)
    tmp.write_bytes(data)
    os.replace(tmp, out)
    return original_size, (width, height)


# ------------------------------------------------------------------------- audio

def _valid_wav_fmt(fmt):
    if len(fmt) < 16:
        return False
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if not (1 <= channels <= 64 and 1 <= rate <= 384000):
        return False
    if byte_rate == 0 or block_align == 0 or bits == 0:
        return False
    return tag in (1, 2, 3, 0x11, 0x16, 0xFFFE) or len(fmt) >= 18


def _find_wav_chunk(data, chunk_id, start):
    search = start
    while True:
        marker = data.find(chunk_id, search)
        if marker < 0 or marker + 8 > len(data):
            return None
        size = struct.unpack_from("<I", data, marker + 4)[0]
        payload_start = marker + 8
        available = len(data) - payload_start
        if available > 0:
            return marker, size, payload_start, available
        search = marker + 4


def _wav_chunks(data):
    if len(data) < 12 or data[8:12] != b"WAVE":
        raise ValueError("WAVE header not found")

    fmt_info = _find_wav_chunk(data, b"fmt ", 12)
    if fmt_info is None:
        raise ValueError("WAV fmt chunk not found")

    marker, declared, payload_start, available = fmt_info
    length = min(declared, available)
    fmt = data[payload_start:payload_start + length]
    if not _valid_wav_fmt(fmt):
        raise ValueError("invalid WAV fmt chunk")

    data_info = _find_wav_chunk(data, b"data", payload_start)
    if data_info is None:
        raise ValueError("WAV data chunk not found")

    marker, declared, payload_start, available = data_info
    if declared == 0 or declared > available:
        length = available
    else:
        length = declared
        tail = payload_start + declared
        if tail < len(data):
            tail_id = data[tail:tail + 4]
            if tail_id not in {b"LIST", b"JUNK", b"fact", b"cue ", b"smpl", b"INFO", b"id3 ", b"PAD ", b"bext"}:
                length = available

    audio = data[payload_start:payload_start + length]
    if not audio:
        raise ValueError("WAV data chunk is empty")

    fact_info = _find_wav_chunk(data, b"fact", payload_start)
    fact = None
    if fact_info is not None:
        _, declared, fact_start, available = fact_info
        if 0 < declared <= available:
            fact = data[fact_start:fact_start + declared]

    return fmt, fact, audio


def _wav_pcm_info(fmt):
    if len(fmt) < 16:
        return None
    tag, channels, rate, _byte_rate, _align, bits = struct.unpack_from("<HHIIHH", fmt, 0)

    if tag == 0xFFFE and len(fmt) >= 40:
        tag = struct.unpack_from("<H", fmt, 24)[0]

    raw_formats = {
        (1, 8): "u8",
        (1, 16): "s16le",
        (1, 24): "s24le",
        (1, 32): "s32le",
        (3, 32): "f32le",
        (3, 64): "f64le",
    }
    raw_format = raw_formats.get((tag, bits))
    if raw_format is None or channels <= 0 or rate <= 0:
        return None
    return raw_format, channels, rate


def _ffmpeg_error(proc):
    stderr = proc.stderr.decode("utf-8", "replace").strip()
    lines = stderr.splitlines()
    return lines[-1].strip() if lines else f"ffmpeg exit {proc.returncode}"


def _encode_args(tmp, bitrate):
    return [
        "-vn",
        "-ac", str(MP3_CHANNELS),
        "-ar", str(MP3_RATE),
        "-c:a", MP3_CODEC,
        "-b:a", bitrate,
        "-map_metadata", "-1",
        "-write_xing", "0",
        "-id3v2_version", "0",
        "-write_id3v1", "0",
        "-f", "mp3",
        str(tmp),
    ]


def _run_ffmpeg(cmd, input_data=None):
    return subprocess.run(cmd, input=input_data, capture_output=True, text=False)


def _repair_wav_bytes(raw):
    fmt, fact, audio = _wav_chunks(raw)
    chunks = []
    for chunk_id, payload in ((b"fmt ", fmt), (b"fact", fact), (b"data", audio)):
        if payload is None:
            continue
        chunks.append(
            chunk_id +
            struct.pack("<I", len(payload)) +
            payload +
            (b"\x00" if len(payload) & 1 else b"")
        )
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def convert_audio(src, out, bitrate):
    """Convert audio to PSP-friendly 44100 Hz stereo MP3."""
    tmp = tmp_path(out)
    suffix = src.suffix.lower()

    if suffix == A8_SUFFIX:
        cmd = [FFMPEG, "-y", "-v", "error", "-f", "u8", "-ar", str(A8_RATE), "-ac", "1", "-i", str(src)]
        proc = _run_ffmpeg(cmd + _encode_args(tmp, bitrate))
        if proc.returncode != 0:
            raise RuntimeError(_ffmpeg_error(proc))
        os.replace(tmp, out)
        return

    if suffix != ".wav":
        cmd = [FFMPEG, "-y", "-v", "error", "-i", str(src)]
        proc = _run_ffmpeg(cmd + _encode_args(tmp, bitrate))
        if proc.returncode != 0:
            raise RuntimeError(_ffmpeg_error(proc))
        os.replace(tmp, out)
        return

    raw = src.read_bytes()
    fmt, _fact, audio = _wav_chunks(raw)
    pcm = _wav_pcm_info(fmt)

    if pcm is not None:
        raw_format, channels, rate = pcm
        cmd = [
            FFMPEG, "-y", "-v", "error",
            "-f", raw_format,
            "-ar", str(rate),
            "-ac", str(channels),
            "-i", "pipe:0",
        ] + _encode_args(tmp, bitrate)
        proc = _run_ffmpeg(cmd, audio)
        if proc.returncode == 0:
            os.replace(tmp, out)
            return

    direct_cmd = [
        FFMPEG, "-y", "-v", "error",
        "-ignore_length", "1",
        "-probesize", "100M",
        "-analyzeduration", "100M",
        "-i", str(src),
    ] + _encode_args(tmp, bitrate)
    proc = _run_ffmpeg(direct_cmd)
    if proc.returncode == 0:
        os.replace(tmp, out)
        return
    direct_error = _ffmpeg_error(proc)

    repaired = _repair_wav_bytes(raw)
    repair_path = src.with_name(src.name + ".repaired.wav.part")
    repair_path.write_bytes(repaired)
    try:
        repaired_cmd = [
            FFMPEG, "-y", "-v", "error",
            "-ignore_length", "1",
            "-probesize", "100M",
            "-analyzeduration", "100M",
            "-i", str(repair_path),
        ] + _encode_args(tmp, bitrate)
        proc = _run_ffmpeg(repaired_cmd)
        if proc.returncode == 0:
            os.replace(tmp, out)
            return
        repaired_error = _ffmpeg_error(proc)
    finally:
        try:
            repair_path.unlink()
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass

    tag, channels, rate, _byte_rate, _align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    raise RuntimeError(
        f"WAV decode failed (format 0x{tag:04X}, {rate} Hz, {channels} ch, {bits} bit): "
        f"{repaired_error}; direct: {direct_error}"
    )


def mp3_is_ready(path):
    """True when path is already an MP3 at the engine's sample rate and channel count,
    so it can be used as it is. Without ffprobe the answer is always no."""
    if not shutil.which(FFPROBE):
        return False
    cmd = [FFPROBE, "-v", "error", "-select_streams", "a:0",
           "-show_entries", "stream=codec_name,sample_rate,channels",
           "-of", "default=noprint_wrappers=1", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    info = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return (info.get("codec_name") == "mp3"
            and info.get("sample_rate") == str(MP3_RATE)
            and info.get("channels") == str(MP3_CHANNELS))


# ------------------------------------------------------------------ the main loop

def tmp_path(path):
    """Staging path in the same folder, so a crash never leaves a truncated output."""
    return path.with_name(path.name + ".part")


def is_up_to_date(src, out):
    """True when out exists and is not older than src."""
    return out.exists() and out.stat().st_mtime >= src.stat().st_mtime


def already_converted(kind, path):
    """For an in-place job (source and output are the same file): a reason string if
    the file already is in the final format, else None."""
    if kind == IMAGE:
        with path.open("rb") as handle:
            if handle.read(4) == BPP_MAGIC:
                return "already BPP8"
        return None
    if mp3_is_ready(path):
        return f"already {MP3_RATE} Hz stereo mp3"
    return None


def keep_original(path):
    """Copy an in-place file to <name>.orig before it is overwritten (--keep-sources)."""
    backup = path.with_name(path.name + ".orig")
    if not backup.exists():
        shutil.copy2(path, backup)


class Log:
    """One line per file plus a summary, echoed to stdout and saved in the game dir."""

    def __init__(self, path):
        self.path = path
        self.lines = []

    def add(self, status, src, out, detail=""):
        line = f"{status}  {src} -> {out}"
        if detail:
            line += f"  [{detail}]"
        self.lines.append(line)
        print(line)

    def finish(self, counts):
        summary = "Summary: {} files, ".format(len(self.lines)) + ", ".join(
            f"{key} {counts[key]}" for key in ("OK", "SKIP", "FAIL")
        )
        print(summary)
        self.path.write_text("\n".join(self.lines + [summary]) + "\n", encoding="utf-8")


def convert_one(kind, src, game_dir, args, claimed):
    """Convert a single source file, log it and drop the original. Returns the status.

    None means the file is not ours. The source is only removed once the output is
    there, so an interrupted run never loses an asset that has no replacement yet.
    When the output path is the source itself (old-format .bpp, .mp3) the file is
    upgraded in place instead, and nothing is removed.
    """
    out = target_for(kind, src)
    if out is None:
        return None
    in_place = out == src
    try:
        if out in claimed:
            raise RuntimeError(f"name collision with {os.path.relpath(claimed[out], game_dir)}")
        claimed[out] = src
        if in_place:
            skip = already_converted(kind, src)
        else:
            skip = "up to date" if is_up_to_date(src, out) and not args.force else None
        if skip:
            status, detail = "SKIP", skip
        else:
            if in_place and args.keep_sources:
                keep_original(src)
            if kind == IMAGE:
                original_size, output_size = convert_image(src, out)
                if original_size != output_size:
                    size_detail = f", downscaled {original_size[0]}x{original_size[1]} -> {output_size[0]}x{output_size[1]}"
                else:
                    size_detail = ""
                status, detail = "OK", f"8 bpp, swizzled{size_detail}{', upgraded in place' if in_place else ''}"
            else:
                convert_audio(src, out, args.bitrate)
                status, detail = "OK", f"{MP3_RATE} Hz stereo mp3 {args.bitrate}{', re-encoded in place' if in_place else ''}"
        if not in_place and not args.keep_sources:
            status, detail = replace_source(src, status, detail)
    except Exception as exc:  # one bad file must not stop the run
        status, detail = "FAIL", str(exc) or type(exc).__name__
    args.log.add(status, os.path.relpath(src, game_dir), os.path.relpath(out, game_dir), detail)
    return status


def replace_source(src, status, detail):
    """Delete the original asset now that its converted file exists. Returns (status, detail)."""
    try:
        src.unlink()
    except OSError as exc:
        return "FAIL", f"{detail}, source kept: {exc.strerror}"
    return status, f"{detail}, source removed"


# ----------------------------------------------------------------- splitting folders

def stem_of(name):
    """File name without its extension. A backup (x.bpp.orig) belongs to the same asset
    as the file it backs up (x), so it moves together with it."""
    if name.lower().endswith(".orig"):
        name = name[: -len(".orig")]
    return os.path.splitext(name)[0]


def logical_parts(parts):
    """Path components with the split subfolders (_00, _01, ...) taken out: where a file
    belongs as far as the scripts are concerned."""
    return [part for part in parts if not BUCKET_RE.match(part)]


def asset_roots(game_dir):
    """The background/, foreground/ and sound/ folders (any capitalisation)."""
    roots = [e for e in game_dir.iterdir() if e.is_dir() and e.name.lower() in FOLDERS]
    return sorted(roots, key=lambda e: e.name.lower())


def plan_buckets(stems, max_files):
    """Assign each asset (a stem with all its files) to a subfolder: {stem: name or ''}.

    Assets are taken in name order and packed so that no subfolder holds more than
    max_files files. An asset's files always stay together. A folder small enough to
    stay in one piece gets '' (no subfolder).
    """
    total = sum(len(files) for files in stems.values())
    if total <= max_files:
        return {stem: "" for stem in stems}
    index, used, assigned = 0, 0, {}
    for stem in sorted(stems):
        size = len(stems[stem])
        if used and used + size > max_files:
            index, used = index + 1, 0
        assigned[stem] = index
        used += size
    width = max(2, len(str(index)))
    return {stem: "_" + str(i).zfill(width) for stem, i in assigned.items()}


def split_folders(game_dir, max_files, log):
    """Rearrange background/, foreground/ and sound/ so that no folder holds more than
    max_files files. Returns (layout, counts).

    layout is {asset folder: {lowercase logical path without extension: subfolder name
    or ''}}, which is what patch_script needs to rewrite the names in the scripts.
    The arrangement is computed from scratch each run, so files are moved back and
    forth as needed and a run on an already-split game changes nothing.
    """
    layout = {}
    counts = {"OK": 0, "SKIP": 0, "FAIL": 0}
    for root in asset_roots(game_dir):
        groups = {}  # lowercase logical folder -> {"parts": [...], "stems": {stem: [(path, name)]}}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).parts
            parts = logical_parts(rel[:-1])
            group = groups.setdefault("/".join(parts).lower(), {"parts": parts, "stems": {}})
            group["stems"].setdefault(stem_of(rel[-1]).lower(), []).append((path, rel[-1]))

        root_layout = layout.setdefault(root.name.lower(), {})
        for gkey, group in sorted(groups.items()):
            folder = root.joinpath(*group["parts"])
            shown = os.path.relpath(folder, game_dir)
            names = [name.lower() for files in group["stems"].values() for _, name in files]
            if len(names) != len(set(names)):
                log.add("FAIL", shown, shown, "same file name in more than one split folder; not rearranged")
                counts["FAIL"] += 1
                continue

            buckets = plan_buckets(group["stems"], max_files)
            moved = 0
            try:
                for stem, files in group["stems"].items():
                    for path, name in files:
                        target = folder / buckets[stem] / name
                        if target == path:
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists():
                            raise RuntimeError(f"{os.path.relpath(target, game_dir)} already exists")
                        os.replace(path, target)
                        moved += 1
            except Exception as exc:
                log.add("FAIL", shown, shown, str(exc) or type(exc).__name__)
                counts["FAIL"] += 1
                continue
            for stem in group["stems"]:
                root_layout["/".join(group["parts"] + [stem]).lower()] = buckets[stem]

            used = sorted(set(buckets.values()) - {""})
            if used and moved:
                log.add("OK", shown, shown, f"split {len(names)} files into {len(used)} folders of at most {max_files}")
                counts["OK"] += 1
            elif used:
                log.add("SKIP", shown, shown, f"already split into {len(used)} folders")
                counts["SKIP"] += 1
            elif moved:
                log.add("OK", shown, shown, f"{len(names)} files back in one folder")
                counts["OK"] += 1

        # Folders left empty by the moves.
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir() and BUCKET_RE.match(path.name) and not any(path.iterdir()):
                path.rmdir()
    return layout, counts


def remap_asset(arg, root, layout):
    """New text for one asset name in a script: converted extension, plus the split
    subfolder if the file now lives in one. The name's own capitalisation is kept."""
    text = arg.decode("latin-1")  # one byte per character, so the round trip is exact
    path, ext = posixpath.splitext(text)
    ext = CONVERTED_EXT.get(ext.lower(), ext)
    parts = path.split("/")
    logical = logical_parts(parts)           # forget any subfolder an earlier run added
    bucket = layout.get(root, {}).get("/".join(logical).lower())
    if bucket is None:                        # not one of our assets: leave the path alone
        return (path + ext).encode("latin-1")
    new = logical[:-1] + ([bucket] if bucket else []) + logical[-1:]
    return ("/".join(new) + ext).encode("latin-1")


def patch_script(path, layout):
    """Repoint asset names in one .scr script at the converted files.

    Returns how many names changed. A .orig copy of the script is kept on the first
    change, so the original VNDS script is never lost.
    """
    data = path.read_bytes()
    changed = 0

    def swap(match):
        nonlocal changed
        arg = match.group(3)
        new = remap_asset(arg, SCR_ROOTS[match.group(2).lower()], layout)
        if new != arg:
            changed += 1
        return match.group(1) + new

    patched = SCR_REF.sub(swap, data)
    if patched != data:
        backup = path.with_name(path.name + ".orig")
        if not backup.exists():
            shutil.copy2(path, backup)  # keeps the original script
        path.write_bytes(patched)
    return changed


def patch_one(script, game_dir, layout, log):
    """Rewrite one script's asset names and log it. Returns the status."""
    rel = os.path.relpath(script, game_dir)
    try:
        changed = patch_script(script, layout)
        if changed:
            status, detail = "OK", f"{changed} names repointed, original kept as {script.name}.orig"
        else:
            status, detail = "SKIP", "already points at converted files"
    except Exception as exc:  # one bad script must not stop the run
        status, detail = "FAIL", str(exc) or type(exc).__name__
    log.add(status, rel, rel, detail)
    return status


def preview_one(path, game_dir, out_dir, log):
    """Write a viewable .png (images) or .wav (audio) copy of one converted file."""
    rel = os.path.relpath(path, game_dir)
    dest = out_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.suffix.lower() == BPP_SUFFIX:
            shown = dest.with_suffix(".png")
            decode_bpp(path).save(shown)
        else:
            shown = dest.with_suffix(".wav")
            cmd = [FFMPEG, "-y", "-v", "error", "-i", str(path), str(shown)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip().splitlines()[-1])
        status, detail = "OK", f"preview at {shown}"
    except Exception as exc:
        status, detail = "FAIL", str(exc) or type(exc).__name__
    log.add(status, rel, rel, detail)
    return status


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("game_dir", help="VNDS game root holding background/, foreground/, sound/")
    parser.add_argument("--bitrate", default=DEFAULT_BITRATE,
                        help=f"MP3 bitrate (default: {DEFAULT_BITRATE}; 64k is smaller, 128k cleaner)")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, metavar="N",
                        help=f"split folders holding more than N files into subfolders (default: {DEFAULT_MAX_FILES})")
    parser.add_argument("--force", action="store_true",
                        help="reconvert even if the output is already up to date")
    parser.add_argument("--keep-sources", action="store_true",
                        help="keep the original assets (files upgraded in place get a .orig copy)")
    parser.add_argument("--preview", metavar="DIR",
                        help="also decode every .bpp/.mp3 into .png/.wav under DIR, for eyeballing")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.max_files < 1:
        print("error: --max-files must be at least 1", file=sys.stderr)
        return 2
    game_dir = Path(args.game_dir).resolve()
    if not game_dir.is_dir():
        print(f"error: not a directory: {game_dir}", file=sys.stderr)
        return 2
    if not shutil.which(FFMPEG):
        print("error: ffmpeg not found", file=sys.stderr)
        return 2

    args.log = Log(game_dir / LOG_NAME)
    counts = {"OK": 0, "SKIP": 0, "FAIL": 0}
    claimed = {}  # output path -> source path, to catch name collisions
    for kind, src in collect_jobs(game_dir):
        status = convert_one(kind, src, game_dir, args, claimed)
        if status:
            counts[status] += 1
    layout, split_counts = split_folders(game_dir, args.max_files, args.log)
    for key, value in split_counts.items():
        counts[key] += value
    for script in sorted(game_dir.glob(SCRIPTS_GLOB)):
        counts[patch_one(script, game_dir, layout, args.log)] += 1
    if args.preview:
        out_dir = Path(args.preview).resolve()
        for path in sorted(game_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in (BPP_SUFFIX, MP3_SUFFIX):
                counts[preview_one(path, game_dir, out_dir, args.log)] += 1
    args.log.finish(counts)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())

