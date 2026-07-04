import numpy as np


class TrackTrackTracker:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path

    def update(self, model, frame) -> tuple[np.ndarray, list[int]]:
        results = model.track(
            frame,
            persist=True,
            tracker=self.config_path,
            classes=[2, 3, 5, 7],
            quantize=16,
            verbose=False
        )

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            return boxes, track_ids

        return np.array([]), []
