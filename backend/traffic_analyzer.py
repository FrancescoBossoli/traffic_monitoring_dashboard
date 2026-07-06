import datetime
import math
import cv2
import numpy as np


def intersect(A, B, C, D):
    """Verifica se due segmenti AB e CD si intersecano geometricamente."""

    def ccw(pt_a, pt_b, pt_c):
        return (pt_c[1] - pt_a[1]) * (pt_b[0] - pt_a[0]) > (
            pt_b[1] - pt_a[1]
        ) * (pt_c[0] - pt_a[0])

    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)


class TrafficAnalyzer:
    """Analizzatore del traffico per velocità, rotte e infrazioni."""

    def __init__(self, lines_config, cam_id="day1"):
        self.lines = lines_config
        self.crossed_ids = {name: set() for name in lines_config.keys()}

        self.history = {}
        self.infractions = []

        # Memoria per lo Stitching (Riparazione ID frammentati)
        self.id_aliases = {}
        self.last_seen = {}

        # Dizionario per valutazioni globali dei veicoli
        self.appraisals = {}

        self.frame_count = 0
        self.speed_limit = 50.0

        # Configurazione calibrazione prospettica (omografia)
        self.src_pts = np.array(
            [
                [90, 360],  # Nord-Ovest
                [769, 299],  # Nord-Est
                [1182, 490],  # Sud-Est
                [175, 606],  # Sud-Ovest
            ],
            dtype=np.float32,
        )

        real_width_m = 20.0
        real_height_m = 20.0

        self.dst_pts = np.array(
            [
                [0, 0],
                [real_width_m, 0],
                [real_width_m, real_height_m],
                [0, real_height_m],
            ],
            dtype=np.float32,
        )

        self.M = cv2.getPerspectiveTransform(self.src_pts, self.dst_pts)

    def _transform_point(self, pt):
        """Converte un punto in pixel in coordinate reali (metri)."""
        pt_array = np.array([[[pt[0], pt[1]]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt_array, self.M)
        return transformed[0][0]

    def _repair_track_id(self, cx, cy, raw_tid):
        """Risolve le catene di alias e le occlusioni temporanee."""
        tid = raw_tid

        while tid in self.id_aliases:
            tid = self.id_aliases[tid]

        if tid not in self.history:
            best_match = None
            min_dist = float("inf")

            for old_tid, data in list(self.last_seen.items()):
                frames_lost = self.frame_count - data["frame"]
                if 0 < frames_lost < 30:
                    dist = math.hypot(
                        cx - data["pos"][0], cy - data["pos"][1]
                    )
                    if dist < 80 and dist < min_dist:
                        min_dist = dist
                        best_match = old_tid

            if best_match is not None:
                self.id_aliases[raw_tid] = best_match
                tid = best_match
                del self.last_seen[best_match]
                print(
                    f"[TRACK REPAIR] ID {raw_tid} riagganciato "
                    f"all'ID originale {tid}"
                )

        self.last_seen[tid] = {"pos": (cx, cy), "frame": self.frame_count}
        return tid

    def _update_routes_and_appraisals(self, tid):
        """Gestisce il superamento delle linee virtuali e gli appraisal."""
        if len(self.history[tid]) < 2:
            return

        pt1 = self.history[tid][-2][:2]
        pt2 = self.history[tid][-1][:2]

        for line_name, line_coords in self.lines.items():
            if intersect(pt1, pt2, line_coords[0], line_coords[1]):
                self.crossed_ids[line_name].add(tid)

                direction = line_name.split("_")[0].lower()
                ts = datetime.datetime.now().strftime("%H:%M:%S")

                if tid not in self.appraisals:
                    self.appraisals[tid] = {
                        "id": tid,
                        "timestamp": ts,
                        "origin": direction,
                        "destination": None,
                        "infraction": "none",
                        "tracker": "",
                        "speed": 0.0,
                    }
                else:
                    if self.appraisals[tid]["origin"] != direction:
                        self.appraisals[tid]["destination"] = direction
                    self.appraisals[tid]["timestamp"] = ts

    def _calculate_speed(self, tid, fps):
        """Calcola la velocità del veicolo tramite Bird's Eye View."""
        valid_points = [
            dt
            for dt in self.history[tid]
            if cv2.pointPolygonTest(self.src_pts, (dt[0], dt[1]), False)
            >= 0
        ]

        if len(valid_points) < 5:
            return

        start_data = valid_points[0]
        end_data = valid_points[-1]

        pt_start_m = self._transform_point((start_data[0], start_data[1]))
        pt_end_m = self._transform_point((end_data[0], end_data[1]))

        dist_m = math.hypot(
            pt_end_m[0] - pt_start_m[0], pt_end_m[1] - pt_start_m[1]
        )
        frames_elapsed = end_data[2] - start_data[2]

        if dist_m > 2.0 and frames_elapsed >= 5:
            time_s = frames_elapsed / fps
            speed_kmh = (dist_m / time_s) * 3.6
            speed_rounded = round(speed_kmh, 1)

            # Inizializza l'appraisal se il veicolo non ha ancora preso linee
            if tid not in self.appraisals:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.appraisals[tid] = {
                    "id": tid,
                    "timestamp": ts,
                    "origin": "—",
                    "destination": None,
                    "infraction": "none",
                    "tracker": "",
                    "speed": 0.0,
                }

            # Aggiorna la velocità massima solo se quella attuale è maggiore
            if speed_rounded > self.appraisals[tid]["speed"]:
                self.appraisals[tid]["speed"] = speed_rounded

            # Controllo dello stato di infrazione basato sulla velocità MAX
            if self.appraisals[tid]["speed"] > self.speed_limit:
                self.appraisals[tid]["infraction"] = "speeding"
                # Sincronizza l'array classico delle infrazioni
                self._register_infraction(tid, self.appraisals[tid]["speed"])

    def _register_infraction(self, tid, max_speed):
        """Registra o aggiorna atomicamente l'infrazione classica."""
        existing = next(
            (inf for inf in self.infractions if inf["vehicle"] == str(tid)),
            None,
        )

        if not existing:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            new_report = {
                "ts": ts,
                "origin": self.appraisals[tid]["origin"],
                "dest": self.appraisals[tid]["destination"] or "—",
                "vehicle": str(tid),
                "type": "Speeding",
                "tracker": "tracktrack",
                "confidence": 0.99,
                "speed": max_speed,
            }
            self.infractions.append(new_report)
        else:
            # Sincronizza sempre il picco massimo di velocità e le rotte
            existing["speed"] = max_speed
            existing["dest"] = self.appraisals[tid]["destination"] or "—"
            existing["ts"] = datetime.datetime.now().strftime("%H:%M:%S")

    def update(self, boxes, track_ids, fps=30.0):
        """Esegue il ciclo completo di analisi del traffico per il frame."""
        if fps <= 0:
            fps = 30.0

        self.frame_count += 1
        resolved_tids = []

        for box, raw_tid in zip(boxes, track_ids):
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            tid = self._repair_track_id(cx, cy, raw_tid)
            resolved_tids.append(tid)

        for box, tid in zip(boxes, resolved_tids):
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2

            if tid not in self.history:
                self.history[tid] = []

            self.history[tid].append((cx, cy, self.frame_count))

            if len(self.history[tid]) > 90:
                self.history[tid].pop(0)

            self._update_routes_and_appraisals(tid)
            self._calculate_speed(tid, fps)
