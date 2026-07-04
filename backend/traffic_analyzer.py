import math
import datetime
import numpy as np
import cv2

def intersect(A, B, C, D):
    """Verifica se due segmenti AB e CD si intersecano geometricamente."""
    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

class TrafficAnalyzer:
    def __init__(self, lines_config, cam_id="day1"):
        self.lines = lines_config
        self.crossed_ids = {name: set() for name in lines_config.keys()}
        
        self.history = {}
        self.infractions = []

        # Memoria per lo Stitching (Riparazione ID frammentati)
        self.id_aliases = {}
        self.last_seen = {}
        
        # Dizionario per tenere traccia delle valutazioni globali dei veicoli
        self.appraisals = {}
        
        self.frame_count = 0
        self.speed_limit = 50.0
        
        # ==========================================
        # CALIBRAZIONE PROSPETTICA
        # ==========================================
        self.src_pts = np.array([
            [90, 360],      # Angolo Alto-Sinistra (Nord-Ovest)
            [769, 299],     # Angolo Alto-Destra (Nord-Est)
            [1182, 490],    # Angolo Basso-Destra (Sud-Est)
            [175, 606]      # Angolo Basso-Sinistra (Sud-Ovest)
        ], dtype=np.float32)

        real_width_m = 20.0
        real_height_m = 20.0

        self.dst_pts = np.array([
            [0, 0],                               # Alto-Sinistra
            [real_width_m, 0],                    # Alto-Destra
            [real_width_m, real_height_m],        # Basso-Destra
            [0, real_height_m]                    # Basso-Sinistra
        ], dtype=np.float32)

        self.M = cv2.getPerspectiveTransform(self.src_pts, self.dst_pts)

    def _transform_point(self, pt):
        """Converte un punto (x,y) in pixel nella sua coordinata (x,y) in METRI vista dall'alto."""
        pt_array = np.array([[[pt[0], pt[1]]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt_array, self.M)
        return transformed[0][0]

    def update(self, boxes, track_ids, fps=30.0):
        if fps <= 0:
            fps = 30.0
            
        self.frame_count += 1

        # Array per contenere gli ID corretti/riparati
        resolved_tids = []
        
        # Risolve le occlusioni e i cambi ID dovuti ai fari accecanti
        for box, raw_tid in zip(boxes, track_ids):
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2

            tid = raw_tid

            # Risolviamo la catena di alias per mantenere l'ID originale
            while tid in self.id_aliases:
                tid = self.id_aliases[tid]
            
            # Se è un ID nuovo, cerchiamo di agganciarlo a uno perso da poco
            if tid not in self.history:
                best_match = None
                min_dist = float('inf')

                for old_tid, data in list(self.last_seen.items()):
                    frames_lost = self.frame_count - data["frame"]
                    # Se perso da meno di 30 frame (~1 secondo)
                    if 0 < frames_lost < 30:
                        dist = math.hypot(cx - data["pos"][0], cy - data["pos"][1])
                        # Tolleranza: l'auto può essersi spostata (es. max 80 pixel) durante il buio
                        if dist < 80 and dist < min_dist:
                            min_dist = dist
                            best_match = old_tid
                            
                if best_match is not None:
                    self.id_aliases[raw_tid] = best_match
                    tid = best_match
                    del self.last_seen[best_match] # Rimosso per non farlo sdoppiare
                    print(f"[TRACK REPAIR] ID {raw_tid} riagganciato all'ID originale {tid} (dopo occlusione fari)")
            
            resolved_tids.append(tid)
            self.last_seen[tid] = {"pos": (cx, cy), "frame": self.frame_count}

        # --- 2. LOGICA STANDARD USANDO GLI ID RIPARATI ---
        for box, tid in zip(boxes, resolved_tids):
            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2
            
            if tid not in self.history:
                self.history[tid] = []
                
            # Salviamo (x, y, indice frame)
            self.history[tid].append((cx, cy, self.frame_count))
            
            # Memoria aumentata a 90 frame
            if len(self.history[tid]) > 90:
                self.history[tid].pop(0)
                
            # 1. CONTROLLO INCROCIO LINEE E ROTTE
            if len(self.history[tid]) >= 2:
                pt1 = self.history[tid][-2][:2]
                pt2 = self.history[tid][-1][:2]
                
                for line_name, line_coords in self.lines.items():
                    if intersect(pt1, pt2, line_coords[0], line_coords[1]):
                        self.crossed_ids[line_name].add(tid)
                        
                        # --- NUOVA LOGICA APPRAISALS ---
                        direction = line_name.split("_")[0].lower() # Prende 'north', 'south', ecc.
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        
                        if tid not in self.appraisals:
                            self.appraisals[tid] = {
                                "id": tid,
                                "timestamp": ts,
                                "origin": direction,
                                "destination": None,
                                "infraction": "none",
                                "tracker": "", # Verrà compilato da main.py
                                "speed": 0.0
                            }
                        else:
                            # Se la nuova linea ha una direzione diversa, diventa la destinazione
                            if self.appraisals[tid]["origin"] != direction:
                                self.appraisals[tid]["destination"] = direction
                            self.appraisals[tid]["timestamp"] = ts
                        
            # 2. CALCOLO DELLA VELOCITÀ TRAMITE BIRD'S EYE VIEW
            valid_points = [
                data for data in self.history[tid] 
                if cv2.pointPolygonTest(self.src_pts, (data[0], data[1]), False) >= 0
            ]
            
            if len(valid_points) >= 5:
                start_data = valid_points[0]
                end_data = valid_points[-1]
                
                pt_start_px = (start_data[0], start_data[1])
                pt_end_px = (end_data[0], end_data[1])
                
                pt_start_m = self._transform_point(pt_start_px)
                pt_end_m = self._transform_point(pt_end_px)
                
                dist_m = math.hypot(pt_end_m[0] - pt_start_m[0], pt_end_m[1] - pt_start_m[1])
                frames_elapsed = end_data[2] - start_data[2]
                
                if dist_m > 2.0 and frames_elapsed >= 5:
                    time_s = frames_elapsed / fps
                    speed_kmh = (dist_m / time_s) * 3.6
                    
                    # --- AGGIORNAMENTO VELOCITÀ NEGLI APPRAISALS ---
                    current_speed_rounded = round(speed_kmh, 1)
                    if tid in self.appraisals:
                        if current_speed_rounded > self.appraisals[tid]["speed"]:
                            self.appraisals[tid]["speed"] = current_speed_rounded
                        if self.appraisals[tid]["speed"] > self.speed_limit:
                            self.appraisals[tid]["infraction"] = "speeding"
                    
                    # 3. REGISTRAZIONE INFRAZIONI CLASSICA (mantenuta per compatibilità box rossi)
                    if speed_kmh > self.speed_limit:
                        existing_infraction = next((inf for inf in self.infractions if inf['vehicle'] == str(tid)), None)
                        
                        if not existing_infraction:
                            ts = datetime.datetime.now().strftime("%H:%M:%S")
                            new_report = {
                                "ts": ts,
                                "origin": "—", 
                                "dest": "—",
                                "vehicle": str(tid),
                                "type": "Speeding",
                                "tracker": "tracktrack",
                                "confidence": 0.99,
                                "speed": current_speed_rounded
                            }
                            self.infractions.append(new_report)
                        else:
                            if current_speed_rounded > existing_infraction['speed']:
                                existing_infraction['speed'] = current_speed_rounded
                                existing_infraction['ts'] = datetime.datetime.now().strftime("%H:%M:%S")