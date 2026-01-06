import json
import matplotlib.pyplot as plt
import numpy as np
import os

def euler_to_rot_mat(u, v, w):
    """
    Euler angles (degrees) to Rotation Matrix.
    Assuming RPY (Roll-Pitch-Yaw) Z-Y-X convention for visualization.
    """
    ur, vr, wr = np.radians(u), np.radians(v), np.radians(w)
    
    # Rotation matrices around X, Y, Z axes
    Rx = np.array([[1, 0, 0],
                   [0, np.cos(ur), -np.sin(ur)],
                   [0, np.sin(ur), np.cos(ur)]])
                   
    Ry = np.array([[np.cos(vr), 0, np.sin(vr)],
                   [0, 1, 0],
                   [-np.sin(vr), 0, np.cos(vr)]])
                   
    Rz = np.array([[np.cos(wr), -np.sin(wr), 0],
                   [np.sin(wr), np.cos(wr), 0],
                   [0, 0, 1]])
    
    # R = Rz * Ry * Rx
    R = Rz @ Ry @ Rx
    return R

def visualize_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    traj = np.array(data.get("motion_trajectory", []))
    if traj.shape[0] == 0:
        print("No trajectory data found.")
        return

    # Extract positions (x, y, z) and orientations (u, v, w)
    xs, ys, zs = traj[:, 0], traj[:, 1], traj[:, 2]
    us, vs, ws = traj[:, 3], traj[:, 4], traj[:, 5]

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # Plot trajectory line
    ax.plot(xs, ys, zs, label='Trajectory', color='black', linewidth=1.5, alpha=0.6)
    ax.scatter(xs[0], ys[0], zs[0], color='green', s=50, marker='o', label='Start')
    ax.scatter(xs[-1], ys[-1], zs[-1], color='red', s=50, marker='x', label='End')

    # Plot coordinate frames (RGB = XYZ)
    # 데이터가 많을 경우 20개 구간으로 나누어 샘플링
    step = max(1, len(traj) // 20)
    axis_length = 20.0  # 화살표 길이 (mm 단위, 데이터 스케일에 맞춰 조절 필요)
    
    for i in range(0, len(traj), step):
        x, y, z = xs[i], ys[i], zs[i]
        u, v, w = us[i], vs[i], ws[i]
        
        R = euler_to_rot_mat(u, v, w)
        
        # X axis (Red)
        ax.quiver(x, y, z, R[0, 0], R[1, 0], R[2, 0], length=axis_length, color='r', normalize=True)
        # Y axis (Green)
        ax.quiver(x, y, z, R[0, 1], R[1, 1], R[2, 1], length=axis_length, color='g', normalize=True)
        # Z axis (Blue)
        ax.quiver(x, y, z, R[0, 2], R[1, 2], R[2, 2], length=axis_length, color='b', normalize=True)

    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm)')
    ax.set_title(f'Motion Trajectory: {os.path.basename(file_path)}')
    ax.legend()
    
    plt.show()

if __name__ == "__main__":
    # 현재 스크립트 위치 기준 motion_data 폴더 탐색
    base_dir = os.path.dirname(os.path.abspath(__file__))
    motion_dir = os.path.join(base_dir, "motion_data")
    
    while True:
        filename = input(f"\nEnter filename in 'motion_data' (e.g. CMD_1000.json) or 'q' to quit: ").strip()
        
        if filename.lower() == 'q':
            break
        
        file_path = os.path.join(motion_dir, filename)
        
        if os.path.exists(file_path):
            visualize_json(file_path)
        else:
            print(f"File not found: {file_path}")