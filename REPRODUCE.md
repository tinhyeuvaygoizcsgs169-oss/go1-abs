# ABS (Agile But Safe) 复现全流程

论文: Agile But Safe: Learning Collision-Free High-Speed Legged Locomotion
会议: RSS 2024 (Outstanding Student Paper Award Finalist)
作者: Tairan He, Chong Zhang, Wenli Xiao, Guanqi He, Changliu Liu, Guanya Shi
机构: CMU + ETH Zurich
代码: https://github.com/LeCAR-Lab/ABS
页面: https://agile-but-safe.github.io/

## 目录结构

```
/home/robot/abs/
├── REPRODUCE.md          # 本文档
├── code/                 # ABS 原始代码（从 /tmp/ABS 复制）
│   ├── training/         # 仿真训练
│   │   ├── rsl_rl/       # 修改版 RSL RL 库
│   │   └── legged_gym/   # Isaac Gym 环境 + 策略
│   └── deployment/       # 实机部署（Go1）
├── go2_migration/       # Go2 迁移方案（Phase 2-3）
├── models/              # 训练好的模型权重
├── logs/                # 训练日志
└── env/                 # conda 环境配置
```

## Phase 1: Go1 仿真复现

### 1.1 环境准备

新建 conda 环境（Python 3.8，Isaac Gym 要求）：
```bash
conda create -n abs python=3.8 -y
conda activate abs

# 安装 PyTorch（ABS 用的版本）
pip install torch==2.0.1 torchvision==0.15.2 --extra-index-url https://download.pytorch.org/whl/cu116

# 安装依赖
pip install numpy==1.21 tensorboard setuptools==59.5.0
```

### 1.2 安装 Isaac Gym

复用现有 Isaac Gym（/home/robot/go2/isaacgym），添加到 Python path：
```bash
# 方法：在 site-packages 下创建 .pth 文件
echo "/home/robot/go2/isaacgym/python" > $(python -c "import site; print(site.getsitepackages()[0])")/isaacgym.pth

# 验证
python -c "import isaacgym; print('Isaac Gym OK')"
```

### 1.3 安装 ABS 训练代码

```bash
cd /home/robot/abs/code/training
pip install -e rsl_rl
pip install -e legged_gym
```

### 1.4 验证环境

```bash
cd legged_gym/legged_gym
python scripts/train.py --task=go1_pos_rough --num_envs=4 --max_iterations=3 --headless
```
预期：前 3 个 iteration 正常完成，不报错。

### 1.5 训练 — 四个模块按顺序

#### A. Agile Policy（最耗时，~几小时到一天）

```bash
cd /home/robot/abs/code/training/legged_gym/legged_gym

# 敏捷策略（默认 4000 iterations, 1280 envs）
python scripts/train.py --task=go1_pos_rough --max_iterations=4000

# 训练完成后导出模型
python scripts/play.py --task=go1_pos_rough
```

#### B. Reach-Avoid Value Network

```bash
# 先用 testbed 收集 200k episodes 数据
python scripts/testbed.py --task=go1_pos_rough --num_envs=1000 --headless --trainRA

# 测试 RA 网络
python scripts/testbed.py --task=go1_pos_rough --num_envs=1 --testRA
```

#### C. Recovery Policy

```bash
# 恢复策略（1000 iterations，比 agile 快很多）
python scripts/train.py --task=go1_rec_rough --max_iterations=1000
```

#### D. Ray-Prediction Network

```bash
# 收集深度图+射线距离数据对
python scripts/camrec.py --task=go1_pos_rough --num_envs=3

# 训练 ResNet-18 射线预测网络
# 参照 train_depth_resnet.py 模板
python scripts/train_depth_resnet.py
```

### 1.6 评估

```bash
# 全面评估（1000 envs, headless）
python scripts/testbed.py --task=go1_pos_rough --num_envs=1000 --headless --testRA

# 预期指标（论文 Table III, nominal setting）：
#   Success Rate: ~79%
#   Collision Rate: ~5.7%
#   Avg Speed: ~2.08 m/s
#   Peak Speed: ~3.48 m/s
```

---

## Phase 2: Go2 仿真迁移

### 2.1 Go1 vs Go2 关键差异

| 参数 | Go1 | Go2 |
|------|-----|-----|
| 初始高度 | 0.39m | 0.42m |
| Hip 默认角度 | 全 0.0 | FL/RL=+0.1, FR/RR=-0.1 |
| 后腿 Thigh 默认 | 0.8 | 1.0 |
| base_height_target | 0.25m | 0.38m |
| 质量 | ~12kg | ~15kg |
| Joint 名称 | 相同 (FL_hip_joint 等) | 相同 |
| URDF | go1.urdf | go2.urdf（在 /home/robot/go2/go2_rl_gym/） |

### 2.2 需要做的事情

1. 复制 Go2 URDF + meshes → ABS 代码的 resources/robots/go2/
2. 基于 ABS 的 go1_pos_config.py 创建 go2_pos_config.py，适配：
   - 默认关节角度
   - 初始高度
   - base_height_target
   - 质量/Kp/Kd
3. 同理创建 go2_rec_config.py（恢复策略）
4. 重训四个模块
5. 对比 Go1 vs Go2 仿真结果

---

## Phase 3: Go2 实机部署

### 3.1 Go2 硬件差异

| 组件 | Go1 (论文) | Go2 (我们) |
|------|-----------|-----------|
| 深度相机 | ZED Mini（外挂） | 内置深度相机 |
| 机载计算 | Orin NX 16GB | 内置 Jetson |
| SDK | unitree_legged_sdk (C++) | unitree_sdk2 (Python/C++) |
| 控制模式 | Low-level UDP (0xff) | sdk2 low-level API |
| 电机协议 | 相同 (12 joint) | 相同 |
| Joint 映射 | policy→unitree 需要重排 | 需要确认映射 |

### 3.2 部署文件改造

原 ABS 部署文件（deployment/src/abs_src/）：
- `publisher_depthimg_linvel.py` → 改为 Go2 内置相机（可能不需要 ZED SDK）
  → ROS topic 发布深度图、里程计、射线预测
- `depth_obstacle_depth_goal_ros.py` → 主控制循环
  → 改 unitree_legged_sdk → unitree_sdk2 底层 API
  → 改 Joint 到电机的索引映射
  → PD 参数可能调整为 Go2 的
- `led_control_ros.py` → LED 灯控制（非必需）
- `onnx_model_converter.py` → 不变

### 3.3 Go2 资源配置

已有资源：
- URDF: /home/robot/go2/go2_rl_gym/resources/robots/go2/urdf/go2.urdf
- Meshes: /home/robot/go2/go2_rl_gym/resources/robots/go2/meshes/
- SDK: /home/robot/go2/go2_rl_gym/unitree_sdk2_python/
- Go2 训练配置: /home/robot/go2/go2_rl_gym/legged_gym/envs/go2/go2_config.py

---

## 预期时间线

| 阶段 | 内容 | 预计耗时 |
|------|------|----------|
| Phase 1.1-1.4 | 环境搭建+验证 | 1-2h |
| Phase 1.5A | Agile Policy 训练 | 6-24h (GPU) |
| Phase 1.5B | RA Value 训练 | 2-6h |
| Phase 1.5C | Recovery Policy 训练 | 1-3h |
| Phase 1.5D | Ray-Prediction 训练 | 1-3h |
| Phase 1.6 | 评估 | 0.5h |
| Phase 2 | Go2 仿真迁移 | 1-2 天 |
| Phase 3 | Go2 实机部署 | 1-2 周（依赖硬件） |
