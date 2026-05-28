from legged_gym import LEGGED_GYM_ROOT_DIR
import os
import time
import isaacgym
from legged_gym.envs import *
from legged_gym.utils import  get_args, export_policy_as_jit, task_registry, Logger

import numpy as np
import torch
import time
import matplotlib.pyplot as plt
import shutil
import argparse

RECORD_FRAMES = False
MOVE_CAMERA = False

# 障碍物预设组合，方便并行采集不同障碍物数据
OBSTACLE_PRESETS = {
    'cylinder': {
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/cylindar.urdf': 0.4,
    },
    'chairs': {
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/DiningChair/model.urdf': 0.4,
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/OfficeChair/model.urdf': 0.4,
    },
    'all': {
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/DiningChair/model.urdf': 0.4,
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/OfficeChair/model.urdf': 0.4,
        '{LEGGED_GYM_ROOT_DIR}/resources/objects/cylindar.urdf': 0.4,
    },
}

def play(args, cam_args):
    env_cfg, train_cfg = task_registry.get_cfgs(name=args.task)

    # ---- 可命令行控制的参数 ----
    env_cfg.env.num_envs = cam_args.num_envs
    env_cfg.env.episode_length_s = 5

    env_cfg.terrain.num_rows = 4
    env_cfg.terrain.num_cols = 4
    env_cfg.terrain.curriculum = False

    env_cfg.sensors.depth_cam.enable = True

    env_cfg.noise.add_noise = False
    env_cfg.domain_rand.randomize_friction = False
    env_cfg.domain_rand.push_robots = True
    env_cfg.domain_rand.max_push_vel_xy = 0.0
    env_cfg.domain_rand.randomize_dof_bias = False

    # 选择障碍物预设
    env_cfg.asset.object_files = OBSTACLE_PRESETS.get(
        cam_args.obstacle, OBSTACLE_PRESETS['all']
    )
    print(f'Using obstacle preset: {cam_args.obstacle}')
    print(f'Objects: {list(env_cfg.asset.object_files.keys())}')

    # prepare environment
    env, _ = task_registry.make_env(name=args.task, args=args, env_cfg=env_cfg)
    env.debug_viz = False
    obs = env.get_observations()
    env.terrain_levels[:] = 9

    # load policy
    train_cfg.runner.resume = True
    ppo_runner, train_cfg = task_registry.make_alg_runner(env=env, name=args.task, args=args, train_cfg=train_cfg)
    policy = ppo_runner.get_inference_policy(device=env.device)

    log_root = cam_args.log_root
    os.makedirs(log_root, exist_ok=True)

    # shift 用于并行采集时避免文件夹冲突
    shift = cam_args.shift
    existing = len(os.listdir(log_root))
    log_folder = f'cam_{existing + shift + 1:04d}'
    last_log_folder = f'cam_{existing + shift:04d}'
    last_success = os.path.isfile(os.path.join(log_root, last_log_folder, 'label.pkl'))
    print(f'Last recording succeed? {last_success}')

    if not last_success and os.path.isdir(os.path.join(log_root, last_log_folder)):
        print(f'{last_log_folder} failed, removing and re-recording')
        shutil.rmtree(os.path.join(log_root, last_log_folder))
        log_folder = last_log_folder

    log_folder = os.path.join(log_root, log_folder)
    os.makedirs(log_folder, exist_ok=True)
    print(f'Saving to: {log_folder}')

    # 计算总步数和预期帧数
    total_steps = cam_args.steps
    frames_per_save = env_cfg.env.num_envs  # 每个保存点存储 num_envs 张图
    save_interval = 5
    expected_frames = (total_steps // save_interval) * frames_per_save
    print(f'Total steps: {total_steps}, envs: {env_cfg.env.num_envs}')
    print(f'Expected frames: ~{expected_frames} ({total_steps}/{save_interval} saves × {env_cfg.env.num_envs} envs)')

    labels = {}
    for i in range(total_steps):
        env.terrain_levels[:] = torch.randint_like(env.terrain_levels[:], low=0, high=10)

        actions = policy(obs.detach())
        obs, _, rews, dones, infos = env.step(actions.detach())

        if i % save_interval == 2:
            for robot in range(env.num_envs):
                save_name = f'robot_{robot}_step{i}'
                cam_data = env.cam_obs[robot].detach().cpu().numpy()
                ray2d_label = env.ray2d_obs[robot].detach().cpu().numpy()
                labels[save_name] = ray2d_label
                np.save(os.path.join(log_folder, f'{save_name}.npy'), cam_data)
            print(f'[{log_folder}] step {i}/{total_steps}  saved {len(labels)} frames')

    # 保存标签文件（所有进程数据可通过合并文件夹汇总）
    import pickle
    label_path = os.path.join(log_folder, 'label.pkl')
    with open(label_path, 'wb') as f:
        pickle.dump(labels, f)

    # 验证
    with open(label_path, 'rb') as f:
        _labels = pickle.load(f)
        print(f'Verified: {len(_labels)} labels saved to {label_path}')


if __name__ == '__main__':
    import isaacgym.gymutil as gymutil
    import argparse as _argparse

    custom_parameters = [
        {"name": "--task", "type": str, "default": "go1_pos_rough"},
        {"name": "--resume", "action": "store_true", "default": False},
        {"name": "--experiment_name", "type": str},
        {"name": "--run_name", "type": str},
        {"name": "--load_run", "type": str},
        {"name": "--checkpoint", "type": int},
        {"name": "--headless", "action": "store_true", "default": False},
        {"name": "--horovod", "action": "store_true", "default": False},
        {"name": "--rl_device", "type": str, "default": "cuda:0"},
        {"name": "--num_envs", "type": int},
        {"name": "--seed", "type": int},
        {"name": "--max_iterations", "type": int},
        {"name": "--trainRA", "action": "store_true", "default": False},
        {"name": "--testRA", "action": "store_true", "default": False},
        # camrec 自定义参数
        {"name": "--cam_shift", "type": int, "default": 100,
         "help": "Shift for folder numbering"},
        {"name": "--cam_steps", "type": int, "default": 1000,
         "help": "Total simulation steps"},
        {"name": "--cam_obstacle", "type": str, "default": "all",
         "help": "Obstacle preset: cylinder, chairs, all"},
        {"name": "--cam_num_envs", "type": int, "default": 9,
         "help": "Number of parallel environments"},
    ]
    args = gymutil.parse_arguments(description="Cam Rec", custom_parameters=custom_parameters)
    args.sim_device_id = args.compute_device_id
    args.sim_device = args.sim_device_type
    if args.sim_device == 'cuda':
        args.sim_device += f":{args.sim_device_id}"

    cam_args = argparse.Namespace(
        shift=args.cam_shift,
        steps=args.cam_steps,
        obstacle=args.cam_obstacle,
        num_envs=args.cam_num_envs,
        log_root=os.path.join(LEGGED_GYM_ROOT_DIR, 'logs/rec_cam'),
    )

    print('=' * 60)
    print(f'Shift: {cam_args.shift} | Steps: {cam_args.steps} | Envs: {cam_args.num_envs}')
    print(f'Obstacle: {cam_args.obstacle} | Log: {cam_args.log_root}')
    print(f'Expected frames: ~{(cam_args.steps // 5) * cam_args.num_envs}')
    print('=' * 60)

    play(args, cam_args)
