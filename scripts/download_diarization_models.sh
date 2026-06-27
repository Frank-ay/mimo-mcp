#!/usr/bin/env bash
# 下载说话人分离(diarization)所需的 sherpa-onnx 模型到 data/models/diarization/。
# 配合 webui ASR 页的「说话人分离」模式使用。
#
# 注意:sherpa-onnx 必须用预编译 wheel 安装,否则缺 onnxruntime 动态库:
#   uv pip install --only-binary=:all: sherpa-onnx soundfile
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$PROJ_DIR/data/models/diarization"
mkdir -p "$DIR"
cd "$DIR"

SEG="sherpa-onnx-pyannote-segmentation-3-0"
EMB="3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
BASE_SEG="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models"
BASE_EMB="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models"

if [ ! -f "$SEG/model.onnx" ]; then
  echo "[1/2] 下载 pyannote 分段模型…"
  curl -fSL -o seg.tar.bz2 "$BASE_SEG/$SEG.tar.bz2"
  tar xf seg.tar.bz2 && rm -f seg.tar.bz2
else
  echo "[1/2] 分段模型已存在,跳过"
fi

if [ ! -f "$EMB" ]; then
  echo "[2/2] 下载 3dspeaker 中文声纹模型…"
  curl -fSL -O "$BASE_EMB/$EMB"
else
  echo "[2/2] 声纹模型已存在,跳过"
fi

echo "完成。模型位于:$DIR"
