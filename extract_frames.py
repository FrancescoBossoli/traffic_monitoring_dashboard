import cv2
import os


def extract_frames(video_path, output_dir, num_frames=30):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = total_frames // num_frames

    count = 0
    success, image = cap.read()
    while success and count < num_frames:
        cv2.imwrite(f"{output_dir}/frame_{count:03d}.jpg", image)
        cap.set(cv2.CAP_PROP_POS_FRAMES, count * step)
        count += 1
        success, image = cap.read()


extract_frames("backend/data/raw/day1.mp4", "dataset_test/day")
extract_frames("backend/data/raw/night.mp4", "dataset_test/night")
extract_frames("backend/data/raw/rain.mp4", "dataset_test/rain")
