import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist


def bbox_to_center(bbox):
    """Converte le coordinate [x1, y1, x2, y2] in [cx, cy, w, h]."""
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    cx = bbox[0] + w / 2
    cy = bbox[1] + h / 2
    return cx, cy, w, h


class Track:
    """Rappresenta una singola traccia monitorata dal tracker."""

    def __init__(self, detection, track_id, appearance_feat=None):
        self.track_id = track_id

        # Stato Kalman: [cx, cy, vx, vy, ax, ay, w, h]
        cx, cy, w, h = bbox_to_center(detection)
        self.state = np.array([cx, cy, 0, 0, 0, 0, w, h], dtype=float)

        # Matrice di covarianza iniziale P
        self.covariance = np.eye(8) * 10.0

        # Modello di aspetto (EMA)
        self.appearance = appearance_feat
        self.alpha_ema = 0.9  # Peso della storia pregressa

        # Gestione dello stato della traccia
        self.time_since_update = 0
        self.hits = 1
        self.state_enum = "Tentative"  # 'Tentative', 'Confirmed', 'Lost'

    def update_appearance(self, new_feat):
        """Aggiorna le feature di aspetto usando una media mobile (EMA)."""
        if self.appearance is None:
            self.appearance = new_feat
        else:
            self.appearance = (
                self.alpha_ema * self.appearance
                + (1 - self.alpha_ema) * new_feat
            )

    def _bbox_to_center_track(self, bbox):
        return (
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2,
            bbox[2] - bbox[0],
            bbox[3] - bbox[1],
        )

    def _bbox_to_center(self, bbox):
        # Converte [x1, y1, x2, y2] in [cx, cy, w, h]
        return (
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2,
            bbox[2] - bbox[0],
            bbox[3] - bbox[1]
        )


class CustomTracker:
    """Tracker multi-oggetto basato su Filtro di Kalman e matching indici."""

    def __init__(self, max_age=30, min_hits=3, iou_threshold=0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks = []
        self.track_id_counter = 1

    def update(self, model, frame, appearances=None):
        """Esegue il ciclo principale di tracking sul frame corrente."""
        # 1. Inferenza YOLO interna e filtraggio classi COCO
        results = model(frame, verbose=False)[0]
        raw_detections = results.boxes.data.cpu().numpy()

        valid_classes = [2, 3, 5, 7]  # Auto, Moto, Bus, Camion
        min_conf = 0.45

        valid_dets = []
        if raw_detections is not None and len(raw_detections) > 0:
            for d in raw_detections:
                if int(d[5]) in valid_classes and d[4] >= min_conf:
                    valid_dets.append(d)

        detections = np.array(valid_dets)

        # Gestione caso senza detection
        if len(detections) == 0:
            for track in self.tracks:
                self._kalman_predict(track)
                track.time_since_update += 1
            self._manage_track_states([], detections, appearances)
            return self._format_output()

        # 2. Predizione Filtro di Kalman
        for track in self.tracks:
            self._kalman_predict(track)
            track.time_since_update += 1

        # Separazione delle tracce per matching a cascata
        active_tracks = [
            t
            for t in self.tracks
            if t.state_enum in ["Confirmed", "Tentative"]
        ]
        lost_tracks = [t for t in self.tracks if t.state_enum == "Lost"]
        unmatched_dets = list(range(len(detections)))

        # 3. Cascade Matching (Tracce attive)
        matched_a, unmatched_dets, _ = self._cascade_matching(
            active_tracks, detections, appearances, unmatched_dets
        )

        # 4. Riassociazione Locale (Tracce perse)
        matched_b, unmatched_dets, _ = self._local_reassociation(
            lost_tracks, detections, appearances, unmatched_dets
        )

        # 5. Aggiornamento tracce associate
        self._update_matched_tracks(matched_a, active_tracks,
                                    detections, appearances)
        self._update_matched_tracks(matched_b, lost_tracks,
                                    detections, appearances)

        # 6. Gestione cicli di vita e nuove tracce
        self._manage_track_states(unmatched_dets, detections, appearances)

        return self._format_output()

    def _update_matched_tracks(self, matches, track_list,
                               detections, appearances):
        """Aggiorna lo stato di Kalman e l'aspetto delle tracce associate."""
        for local_idx, det_idx in matches:
            track = track_list[local_idx]
            self._kalman_update(track, detections[det_idx])
            track.time_since_update = 0
            track.hits += 1
            if appearances is not None:
                track.update_appearance(appearances[det_idx])

    def _compute_iou(self, kalman_state, detection):
        """Calcola l'Intersection over Union (IoU) tra Kalman e YOLO."""
        cx, cy, w, h = (
            kalman_state[0],
            kalman_state[1],
            kalman_state[6],
            kalman_state[7],
        )
        k_x1, k_y1 = cx - w / 2, cy - h / 2
        k_x2, k_y2 = cx + w / 2, cy + h / 2

        d_x1, d_y1, d_x2, d_y2 = detection[:4]

        xx1 = max(k_x1, d_x1)
        yy1 = max(k_y1, d_y1)
        xx2 = min(k_x2, d_x2)
        yy2 = min(k_y2, d_y2)

        w_inter = max(0, xx2 - xx1)
        h_inter = max(0, yy2 - yy1)
        area_inter = w_inter * h_inter

        area_union = w * h + (d_x2 - d_x1) * (d_y2 - d_y1) - area_inter

        return area_inter / area_union if area_union > 0 else 0.0

    def _compute_cost_matrix(self, tracks, detections,
                             appearances, det_indices):
        """Genera la matrice di costo combinando IoU, aspetto e velocità."""
        cost_matrix = np.zeros((len(tracks), len(det_indices)))
        gate_cost = 10000.0

        # Bilanciamento pesi metriche
        if appearances is None:
            w_iou, w_app, w_vel = 0.8, 0.0, 0.2
        else:
            w_iou, w_app, w_vel = 0.4, 0.4, 0.2

        for i, track in enumerate(tracks):
            for j, det_idx in enumerate(det_indices):
                iou = self._compute_iou(track.state, detections[det_idx])
                iou_cost = 1.0 - iou

                app_cost = 0.0
                if track.appearance is not None and appearances is not None:
                    feat_t = [track.appearance]
                    feat_d = [appearances[det_idx]]
                    app_cost = cdist(feat_t, feat_d, "cosine")[0][0]

                vel_cost = self._velocity_consistency_cost(
                    track, detections[det_idx]
                )

                cost = w_iou * iou_cost + w_app * app_cost + w_vel * vel_cost

                # Sconto per tracce perse di recente
                if track.state_enum == "Lost" and track.time_since_update < 10:
                    cost *= 0.5

                cost_matrix[i, j] = (
                    gate_cost if iou < self.iou_threshold else cost
                )

        return cost_matrix

    def _cascade_matching(self, tracks, detections,
                          appearances, unmatched_dets):
        """Esegue il matching a cascata basato sull'età della traccia."""
        matches = []
        unmatched_trks_indices = list(range(len(tracks)))

        for level in range(1, self.max_age + 1):
            if len(unmatched_dets) == 0:
                break

            level_track_indices = [
                i
                for i in unmatched_trks_indices
                if tracks[i].time_since_update == level
            ]

            if len(level_track_indices) == 0:
                continue

            level_tracks = [tracks[i] for i in level_track_indices]
            cost_matrix = self._compute_cost_matrix(
                level_tracks, detections, appearances, unmatched_dets
            )

            row_indices, col_indices = linear_sum_assignment(cost_matrix)

            matched_dets_this_level = []
            matched_trks_this_level = []

            for row, col in zip(row_indices, col_indices):
                if cost_matrix[row, col] < 10000.0:
                    track_idx = level_track_indices[row]
                    det_idx = unmatched_dets[col]

                    matches.append((track_idx, det_idx))
                    matched_dets_this_level.append(det_idx)
                    matched_trks_this_level.append(track_idx)

            unmatched_dets = [
                d for d in unmatched_dets if d not in matched_dets_this_level
            ]
            unmatched_trks_indices = [
                t
                for t in unmatched_trks_indices
                if t not in matched_trks_this_level
            ]

        return matches, unmatched_dets, unmatched_trks_indices

    def _local_reassociation(self, lost_tracks, detections,
                             appearances, unmatched_dets):
        """Tenta una riassociazione locale per le tracce perse."""
        if len(lost_tracks) == 0 or len(unmatched_dets) == 0:
            return [], unmatched_dets, list(range(len(lost_tracks)))

        cost_matrix = self._compute_cost_matrix(
            lost_tracks, detections, appearances, unmatched_dets
        )
        row_indices, col_indices = linear_sum_assignment(cost_matrix)

        matches = []
        matched_dets_this_level = []
        matched_trks_this_level = []

        for row, col in zip(row_indices, col_indices):
            if cost_matrix[row, col] < 10000.0:
                matches.append((row, unmatched_dets[col]))
                matched_dets_this_level.append(unmatched_dets[col])
                matched_trks_this_level.append(row)

        unmatched_dets = [
            d for d in unmatched_dets if d not in matched_dets_this_level
        ]
        unmatched_trks = [
            i
            for i in range(len(lost_tracks))
            if i not in matched_trks_this_level
        ]

        return matches, unmatched_dets, unmatched_trks

    def _velocity_consistency_cost(self, track, detection):
        """Valuta la coerenza direzionale tra vettore velocità e detection."""
        vx, vy = track.state[2], track.state[3]

        if abs(vx) < 1e-2 and abs(vy) < 1e-2:
            return 0.0

        k_cx, k_cy = track.state[0], track.state[1]
        d_cx, d_cy = bbox_to_center(detection)[:2]

        dir_x = d_cx - k_cx
        dir_y = d_cy - k_cy

        norm_v = np.hypot(vx, vy)
        norm_dir = np.hypot(dir_x, dir_y)

        if norm_dir < 1e-2:
            return 0.0

        cos_sim = (vx * dir_x + vy * dir_y) / (norm_v * norm_dir)
        return (1.0 - cos_sim) / 2.0

    def _kalman_predict(self, track):
        """Esegue lo step di predizione dello stato nel Filtro di Kalman."""
        F = np.eye(8)
        F[0, 2] = F[1, 3] = F[2, 4] = F[3, 5] = 1.0
        F[0, 4] = F[1, 5] = 0.5

        Q = np.eye(8) * 0.01

        track.state = np.dot(F, track.state)
        track.covariance = (
            np.linalg.multi_dot([F, track.covariance, F.T]) + Q
        )

    def _kalman_update(self, track, detection):
        """Aggiorna lo stato di Kalman integrando la nuova osservazione."""
        measurement_matrix = np.zeros((4, 8))
        measurement_matrix[0, 0] = 1.0
        measurement_matrix[1, 1] = 1.0
        measurement_matrix[2, 6] = 1.0
        measurement_matrix[3, 7] = 1.0

        measurement = np.array(bbox_to_center(detection))
        measurement_covariance = np.eye(4) * 0.1

        # Calcolo dell'innovazione (residuale)
        innovation = measurement - np.dot(measurement_matrix, track.state)

        # Calcolo della covarianza dell'innovazione
        innovation_covariance = (
            np.linalg.multi_dot(
                [measurement_matrix, track.covariance, measurement_matrix.T]
            )
            + measurement_covariance
        )

        # Calcolo del guadagno di Kalman
        kalman_gain = np.linalg.multi_dot(
            [
                track.covariance,
                measurement_matrix.T,
                np.linalg.inv(innovation_covariance),
            ]
        )

        # Aggiornamento dello stato
        track.state = track.state + np.dot(kalman_gain, innovation)

        # Aggiornamento della covarianza dello stato
        identity_matrix = np.eye(8)
        gain_measurement_product = np.dot(kalman_gain, measurement_matrix)
        track.covariance = np.dot(
            (identity_matrix - gain_measurement_product), track.covariance
        )

    def _manage_track_states(self, unmatched_dets, detections, appearances):
        """Gestisce il ciclo di vita delle tracce e ne inizializza di nuove."""
        for track in self.tracks:
            if track.time_since_update == 0:
                if (
                    track.state_enum == "Tentative"
                    and track.hits >= self.min_hits
                ):
                    track.state_enum = "Confirmed"
            else:
                if track.state_enum == "Confirmed":
                    track.state_enum = "Lost"

        # Rimozione tracce obsolete
        self.tracks = [
            t for t in self.tracks if t.time_since_update <= self.max_age
        ]

        # Inizializzazione nuove tracce orfane
        for det_idx in unmatched_dets:
            app = appearances[det_idx] if appearances is not None else None
            new_track = Track(
                detections[det_idx], self.track_id_counter, app
            )
            self.tracks.append(new_track)
            self.track_id_counter += 1

    def _format_output(self):
        """Formatta l'output restituendo le bounding box e gli ID attivi."""
        boxes = []
        track_ids = []

        for track in self.tracks:
            if track.state_enum == "Confirmed":
                cx, cy, w, h = (
                    track.state[0],
                    track.state[1],
                    track.state[6],
                    track.state[7],
                )

                x1 = cx - w / 2
                y1 = cy - h / 2
                x2 = cx + w / 2
                y2 = cy + h / 2

                boxes.append([x1, y1, x2, y2])
                track_ids.append(track.track_id)

        if len(boxes) == 0:
            return np.empty((0, 4)), np.empty((0,), dtype=int)

        return np.array(boxes), np.array(track_ids, dtype=int)
