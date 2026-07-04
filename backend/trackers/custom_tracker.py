import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment


class KalmanBox:
    def __init__(self, bbox):
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        self.state = np.array([cx, cy, 0, 0], dtype=float)
        self.P = np.eye(4) * 10.0
        self.F = np.array(
            [[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]],
            dtype=float
        )
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        self.R = np.eye(2) * 5.0
        self.Q = np.eye(4) * 0.1

    def predict(self):
        self.state = self.F @ self.state
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.state[:2]

    def update(self, bbox):
        x1, y1, x2, y2 = bbox
        z = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
        y = z - (self.H @ self.state)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(4) - K @ self.H) @ self.P


class Track:
    def __init__(self, track_id, bbox, frame):
        self.id = track_id
        self.bbox = bbox.copy()
        self.kf = KalmanBox(bbox)
        self.time_since_update = 0
        self.missed = 0
        self.hits = 1
        self.w, self.h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        self.hist = self.extract_hist(frame, bbox)
        self.hist_mem = [self.hist] if self.hist is not None else []

    def extract_hist(self, frame, box):
        x1, y1, x2, y2 = map(int, box)
        h, w = frame.shape[:2]
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist.flatten()

    def predict(self):
        new_center = self.kf.predict()
        self.bbox = np.array([
            new_center[0]-self.w/2, new_center[1]-self.h/2,
            new_center[0]+self.w/2, new_center[1]+self.h/2
        ])
        self.time_since_update += 1
        self.missed += 1

    def update(self, bbox, frame):
        new_area = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1])
        # Soglia occlusione 60%
        is_occluded = new_area < ((self.w * self.h) * 0.6)

        self.kf.R = np.eye(2) * (200.0 if is_occluded else 5.0)
        self.kf.update(bbox)

        if not is_occluded:
            self.w = 0.8 * self.w + 0.2 * (bbox[2]-bbox[0])
            self.h = 0.8 * self.h + 0.2 * (bbox[3]-bbox[1])
            new_hist = self.extract_hist(frame, bbox)
            if new_hist is not None:
                self.hist_mem = (self.hist_mem + [new_hist])[-5:]
                self.hist = np.mean(self.hist_mem, axis=0)

        cx, cy = self.kf.state[0], self.kf.state[1]
        self.bbox = np.array([
            cx-self.w/2, cy-self.h/2, cx+self.w/2, cy+self.h/2
        ])
        self.time_since_update = 0
        self.missed = 0
        self.hits += 1


class CustomTracker:
    def __init__(self, max_age=180):
        self.tracks = []
        self.next_id = 1
        self.max_age = max_age

    def update(self, model, frame):
        results = model(
            frame,
            classes=[2, 3, 5, 7],
            conf=0.5,
            iou=0.4,
            verbose=False
        )
        boxes = results[0].boxes
        dets = boxes.xyxy.cpu().numpy() if boxes is not None else []

        # 1. Predizione Kalman
        for t in self.tracks:
            t.predict()

        # 2. Se non ci sono track, inizializza tutto
        if not self.tracks:
            for d in dets:
                self.tracks.append(Track(self.next_id, d, frame))
                self.next_id += 1
            return self._out()

        # 3. Costruzione Matrice Costi
        cost = np.zeros((len(self.tracks), len(dets)), dtype=np.float32)
        for i, t in enumerate(self.tracks):
            for j, d in enumerate(dets):
                cost[i, j] = 1.0 - self.iou(t.bbox, d)

        # 4. Assegnazione Ungherese
        row, col = linear_sum_assignment(cost)

        matched_tracks = set()
        matched_dets = set()

        for r, c in zip(row, col):
            threshold = (
                0.5 if (self.tracks[r].hits < 5 or self.tracks[r].missed > 0)
                else 0.6
            )

            if cost[r, c] < threshold:
                self.tracks[r].update(dets[c], frame)
                matched_tracks.add(r)
                matched_dets.add(c)

        # 5. Gestione track non matchati (missed)
        for i in range(len(self.tracks)):
            if i not in matched_tracks:
                self.tracks[i].missed += 1

        # 6. Nuovi track (solo per detection non matchate)
        for j in range(len(dets)):
            if j not in matched_dets:
                self.tracks.append(Track(self.next_id, dets[j], frame))
                self.next_id += 1

        self._prune()
        return self._out()

    def iou(self, a, b):
        inter = max(
            0, min(a[2], b[2]) - max(a[0], b[0])
        ) * max(
            0, min(a[3], b[3]) - max(a[1], b[1])
        )
        return inter / (
            (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter + 1e-6
        )

    def _prune(self): self.tracks = [
        t for t in self.tracks if t.missed <= self.max_age
    ]

    def _out(self):
        # DEBUG: Cambiamo la condizione. Se vedi le box con questo,
        # significa che i track non superano mai hits >= 3.
        boxes, ids = [], []
        for t in self.tracks:
            # Rimosso t.hits >= 3 per testare se i track sono vivi
            if t.missed == 0:
                boxes.append(t.bbox)
                ids.append(t.id)
        return np.array(boxes), ids
