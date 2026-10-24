"""Just enough MP3 parsing to prove bytes are real Layer III audio: walk the frames and add up their duration."""

BITRATES_KBPS = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _skip_id3(data: bytes) -> int:
    if data[:3] != b"ID3":
        return 0
    size = data[6] << 21 | data[7] << 14 | data[8] << 7 | data[9]
    return 10 + size


def mp3_duration_s(data: bytes) -> float:
    """Seconds of audio in consecutive Layer III frames; raises ValueError if the stream isn't MP3."""
    pos, frames, seconds = _skip_id3(data), 0, 0.0
    while pos + 4 <= len(data):
        header = int.from_bytes(data[pos:pos + 4], "big")
        if header >> 21 != 0x7FF:
            break
        version, layer = header >> 19 & 3, header >> 17 & 3
        bitrate_i, rate_i, padding = header >> 12 & 15, header >> 10 & 3, header >> 9 & 1
        if layer != 1 or version == 1 or bitrate_i in (0, 15) or rate_i == 3:
            raise ValueError(f"not a Layer III frame at byte {pos}")
        mpeg1 = version == 3
        bitrate = BITRATES_KBPS[1 if mpeg1 else 2][bitrate_i] * 1000
        rate = SAMPLE_RATES[version][rate_i]
        pos += (144 if mpeg1 else 72) * bitrate // rate + padding
        frames += 1
        seconds += (1152 if mpeg1 else 576) / rate
    if frames < 10:
        raise ValueError(f"only {frames} MP3 frames")
    return seconds
