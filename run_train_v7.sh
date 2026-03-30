#!/bin/bash
# Run V7 Training from Terminal.app
# Usage: Open Terminal.app → paste this:
#   cd "/Users/vuthanhtrung/Downloads/Bot AI/Bot AI" && bash run_train_v7.sh

echo "🚀 Starting V7 Training..."
echo "   Using .venv Python with all packages"

# Use the venv that has all packages
PYTHON="/Users/vuthanhtrung/Downloads/Bot AI/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "❌ venv not found, using system python3"
    PYTHON="python3"
fi

cd "/Users/vuthanhtrung/Downloads/Bot AI/Bot AI"

# Run training and capture output
$PYTHON train_ai_improved.py 2>&1 | tee logs/train_v7_output.log

echo ""
echo "📝 Training log saved to: logs/train_v7_output.log"
echo "🎉 Done!"
