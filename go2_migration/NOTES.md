# Go2 迁移笔记

## 已有资源（可直接用）

### URDF & 模型
- Go2 URDF: /home/robot/go2/go2_rl_gym/resources/robots/go2/urdf/go2.urdf
- Go2 Meshes: /home/robot/go2/go2_rl_gym/resources/robots/go2/meshes/

### 参考配置
- Go2 基础配置: /home/robot/go2/go2_rl_gym/legged_gym/envs/go2/go2_config.py
- Go2 环境实现: /home/robot/go2/go2_rl_gym/legged_gym/envs/go2/go2_env.py
- Go2 SDK: /home/robot/go2/go2_rl_gym/unitree_sdk2_python/
- Go2 Isaac Gym: /home/robot/go2/isaacgym/

### Go2 Joint Name (URDF 定义)
- FL_hip_joint, FL_thigh_joint, FL_calf_joint
- FR_hip_joint, FR_thigh_joint, FR_calf_joint
- RL_hip_joint, RL_thigh_joint, RL_calf_joint
- RR_hip_joint, RR_thigh_joint, RR_calf_joint

与 Go1 命名一致！这是好消息。

## Go1 vs Go2 配置对比

参见 ABS Go1 配置: /home/robot/abs/code/training/legged_gym/legged_gym/envs/go1/

### 需要修改的配置项（从 go1_pos_config.py → go2_pos_config.py）

1. asset.file → go2.urdf
2. asset.name → "go2"
3. init_state.pos → [0, 0, 0.42]
4. init_state.default_joint_angles → Go2 的默认值:
   - Hip: FL/RL=0.1, FR/RR=-0.1
   - Thigh: FL/FR=0.8, RL/RR=1.0
   - Calf: 全部 -1.5
5. rewards.base_height_target → 0.38 (Go2 更高)
6. domain_rand.added_mass_range → 可能需要调整（Go2 重一些）

### 需要新增的文件

仿照 go1_pos_config.py + go1_rec_config.py 创建：
- go2_pos_config.py（敏捷策略）
- go2_rec_config.py（恢复策略）

仿照 go1_pos_rough / go1_rec_rough 注册新 task。

## 从 Go1 → Go2 部署改造要点

### 底层控制
Go1 (ABS 论文) 用 unitree_legged_sdk:
```python
import robot_interface as sdk
lowudp = sdk.UDP(LOWLEVEL, 8080, "192.168.123.10", 8007)
low_state = sdk.LowState()  # 12 motors
```

Go2 用 unitree_sdk2，需要确认 low-level API：
- 参考: /home/robot/go2/go2_rl_gym/unitree_sdk2_python/unitree_sdk2py/test/lowlevel/
- 通信方式可能不同（DDS vs UDP）

### 深度相机
Go1: ZED Mini (SDK: pyzed)
Go2: 内置深度相机 → 需要确认：
- 相机型号
- 分辨率、FOV
- 是否能拿到 raw depth array
- 是否需要重新训练 Ray-Prediction Network

### 额外硬件
Go1 用了 Orin NX 16GB 外挂计算，Go2 内置 Jetson 够不够还需要确认。
