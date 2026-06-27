"""说话人分离转写(diarization + ASR)。

sherpa-onnx 负责 speaker diarization(本地、离线,输出"谁在 A~B 时段说话"),
MiMo 负责每段转写——两者解耦:diarization 只给时间轴,转写质量用 MiMo。
diarization 的时间段天然就是时间戳,speaker 标签即区分发音人。

流程:音频 → ffmpeg 转 16kHz mono → sherpa-onnx diarization → 按说话人段切片
→ 逐段 MiMo /chat/completions 转写 → 合并成带 speaker + 时间戳 的结果。

模型(放 data/models/diarization/,见 scripts/download_diarization_models.sh):
- 分段:sherpa-onnx-pyannote-segmentation-3-0/model.onnx
- 声纹:3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx

注意:sherpa-onnx 需用预编译 wheel 安装(否则缺 onnxruntime 动态库):
  uv pip install --only-binary=:all: sherpa-onnx
"""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ..client import MimoClient
from ..config import get_settings

log = logging.getLogger(__name__)

_SEG_MODEL_DIR = "sherpa-onnx-pyannote-segmentation-3-0"
_EMB_MODEL = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
_SAMPLE_RATE = 16000


def _model_paths() -> tuple[Path, Path]:
    base = get_settings().data_dir / "models" / "diarization"
    return base / _SEG_MODEL_DIR / "model.onnx", base / _EMB_MODEL


def models_ready() -> bool:
    return all(p.is_file() for p in _model_paths())


def _build_diarizer(num_speakers: int) -> Any:
    """构建 OfflineSpeakerDiarization。num_speakers<=0 时自动聚类。"""
    import sherpa_onnx

    seg, emb = _model_paths()
    missing = [str(p) for p in (seg, emb) if not p.is_file()]
    if missing:
        raise RuntimeError(
            "说话人分离模型缺失,请先运行 scripts/download_diarization_models.sh。缺:"
            + ", ".join(missing)
        )

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(seg)
            ),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb)),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers if num_speakers and num_speakers > 0 else -1,
            threshold=0.5,
        ),
    )
    if not config.validate():
        raise RuntimeError("说话人分离配置无效(请检查模型文件是否完整)")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


async def _ffmpeg_to_wav16(src: Path) -> Path:
    """ffmpeg 转 16kHz mono PCM wav(diarization 与 soundfile 都要 16kHz mono)。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("说话人分离需要 ffmpeg,请先 `brew install ffmpeg`。")
    out = src.parent / f"{src.stem}_16k.wav"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-ac", "1", "-ar", str(_SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(out),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 转码失败:{stderr.decode('utf-8', errors='replace')[:200]}"
        )
    return out


def _wav_bytes(samples: Any, sample_rate: int) -> bytes:
    """把 float32 采样写成 wav 字节(给 MiMo input_audio)。"""
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _seg_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices") or []
    if not choices:
        return ""
    return ((choices[0].get("message") or {}).get("content") or "").strip()


async def transcribe_diarized(
    audio_path: str, *, language: str = "auto", num_speakers: int = -1
) -> AsyncIterator[dict[str, Any]]:
    """说话人分离转写。yield 事件(``kind`` 区分):

    - ``status``:进度提示(diarization 是同步计算,先发一条占位)
    - ``plan``:总段数 + 说话人数 + 每段 (speaker, start, end)
    - ``segment``:单段转写完(含 speaker / start / end / text)
    - ``summary``:全部段(供前端导出 txt/srt/json)
    """
    settings = get_settings()
    src = Path(audio_path)
    if not src.is_file():
        raise FileNotFoundError(f"音频文件不存在:{src}")

    wav16: Path | None = None
    try:
        wav16 = await _ffmpeg_to_wav16(src)

        import soundfile as sf

        samples, sr = sf.read(str(wav16), dtype="float32", always_2d=True)
        samples = samples[:, 0]  # 取单声道
        duration = len(samples) / float(sr) if sr else 0.0

        yield {"kind": "status", "message": "正在本地分离说话人…"}

        # diarization 是 CPU 密集的同步计算,丢到线程池避免阻塞事件循环
        diarizer = _build_diarizer(num_speakers)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: diarizer.process(samples).sort_by_start_time()
        )
        segments = [(float(r.start), float(r.end), int(r.speaker)) for r in result]
        speakers = sorted({spk for _, _, spk in segments})

        yield {
            "kind": "plan",
            "total": len(segments),
            "duration": duration,
            "num_speakers": len(speakers),
            "segments": [
                {"index": i, "speaker": spk, "start": st, "end": en}
                for i, (st, en, spk) in enumerate(segments)
            ],
        }

        out: list[dict[str, Any]] = []
        async with MimoClient(settings) as client:
            for i, (start, end, speaker) in enumerate(segments):
                seg = samples[int(start * sr) : int(end * sr)]
                text = ""
                if len(seg) > 0:
                    try:
                        raw = await client.transcribe(
                            _wav_bytes(seg, sr),
                            model=settings.default_asr_model,
                            language=language,
                            content_type="audio/wav",
                        )
                        text = _seg_text(raw)
                    except Exception as e:  # 单段失败不中断整体
                        log.warning("说话人段 %d 转写失败:%s", i, e)
                row = {
                    "index": i,
                    "speaker": speaker,
                    "start": start,
                    "end": end,
                    "text": text,
                }
                out.append(row)
                yield {"kind": "segment", **row}

        yield {
            "kind": "summary",
            "duration": duration,
            "num_speakers": len(speakers),
            "segments": out,
        }
    finally:
        if wav16 is not None:
            wav16.unlink(missing_ok=True)
