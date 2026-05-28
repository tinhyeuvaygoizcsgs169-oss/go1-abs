#!/bin/bash
# ==========================================
# ABS 环境安装脚本
# 用法: bash /home/robot/abs/env/setup.sh
# ==========================================
set -e

ABS_ROOT=/home/robot/abs
ISAACGYM_PATH=/home/robot/go2/isaacgym/python

echo ">>> Step 1: 创建 conda 环境..."
conda create -n abs python=3.8 -y

echo ">>> Step 2: 激活环境并安装 PyTorch..."
source $(conda info --base)/etc/profile.d/conda.sh
conda activate abs
pip install torch==2.0.1 torchvision==0.15.2 --extra-index-url https://download.pytorch.org/whl/cu116
pip install numpy==1.21 tensorboard setuptools==59.5.0

echo ">>> Step 3: 链接 Isaac Gym..."
SITE_PKGS=$(python -c "import site; print(site.getsitepackages()[0])")
echo "$ISAACGYM_PATH" > "$SITE_PKGS/isaacgym.pth"
python -c "import isaacgym; print('Isaac Gym OK')"

echo ">>> Step 4: 安装 ABS 训练代码..."
cd $ABS_ROOT/code/training
pip install -e rsl_rl
pip install -e legged_gym

echo ">>> Step 5: 冒烟测试..."
cd legged_gym/legged_gym
python scripts/train.py --task=go1_pos_rough --num_envs=4 --max_iterations=3 --headless

echo ""
echo "=========================================="
echo "  环境搭建完成！"
echo "  激活环境: conda activate abs"
echo "  训练目录: $ABS_ROOT/code/training/legged_gym/legged_gym"
echo "=========================================="
