import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

class Track:
    def __init__(self, detection, track_id, appearance_feat=None):
        self.track_id = track_id
        # Inizializzazione Stato Kalman: [cx, cy, vx, vy, ax, ay, w, h]
        cx, cy, w, h = self._bbox_to_center_track(detection)
        self.state = np.array([cx, cy, 0, 0, 0, 0, w, h], dtype=float)
        self.covariance = np.eye(8) * 10.0 # P matrix iniziale
        
        # Appearance Model (EMA)
        self.appearance = appearance_feat
        self.alpha_ema = 0.9 # Peso della storia pregressa
        
        # Lost Track Manager states
        self.time_since_update = 0
        self.hits = 1
        self.state_enum = 'Tentative' # 'Tentative', 'Confirmed', 'Lost'

    def update_appearance(self, new_feat):
        if self.appearance is None:
            self.appearance = new_feat
        else:
            # Formula EMA
            self.appearance = self.alpha_ema * self.appearance + (1 - self.alpha_ema) * new_feat

    def _bbox_to_center_track(self, bbox):
        return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _bbox_to_center(self, bbox):
        # Converte [x1, y1, x2, y2] in [cx, cy, w, h]
        return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, bbox[2] - bbox[0], bbox[3] - bbox[1]

class CustomTracker:
    def __init__(self, max_age=30, min_hits=3, iou_threshold=0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks = []
        self.track_id_counter = 1
        
        # Adaptive Thresholds base
        self.gating_threshold = 9.4877 # Chi-square 0.05 a 4 gradi di libertà

    def update(self, model, frame, appearances=None):
        # 1. Inferenza YOLO interna
        results = model(frame, verbose=False)[0]
        raw_detections = results.boxes.data.cpu().numpy()
        
        # --- FIX 1: FILTRO CLASSI E CONFIDENZA ---
        # COCO classes: 2=Car, 3=Motorcycle, 5=Bus, 7=Truck
        valid_classes = [2, 3, 5, 7]
        min_conf = 0.45 # Alziamo la confidenza per evitare "flickering" o falsi positivi
        
        valid_dets = []
        if raw_detections is not None and len(raw_detections) > 0:
            for d in raw_detections:
                if int(d[5]) in valid_classes and d[4] >= min_conf:
                    valid_dets.append(d)
                    
        detections = np.array(valid_dets)
        # -----------------------------------------

        # Guard clause (ora usa detections filtrato)
        if len(detections) == 0:
            for track in self.tracks:
                self._kalman_predict(track)
                track.time_since_update += 1
            
            self._manage_track_states([], detections, appearances)
            return self._format_output()

        # 2. Kalman Predict
        for track in self.tracks:
            self._kalman_predict(track)
            track.time_since_update += 1

        active_tracks = [t for t in self.tracks if t.state_enum in ['Confirmed', 'Tentative']]
        lost_tracks = [t for t in self.tracks if t.state_enum == 'Lost']
        
        unmatched_dets = list(range(len(detections)))

        # 3. Primo step: Cascade Matching
        matched_a, unmatched_dets, unmatched_trks_a = self._cascade_matching(
            active_tracks, detections, appearances, unmatched_dets
        )

        # 4. Secondo step: Re-associazione locale
        matched_b, unmatched_dets, unmatched_trks_b = self._local_reassociation(
            lost_tracks, detections, appearances, unmatched_dets
        )

        # 5. Aggiornamento tracce matchate
        for local_idx, det_idx in matched_a:
            track = active_tracks[local_idx]
            self._kalman_update(track, detections[det_idx])
            track.time_since_update = 0
            track.hits += 1
            if appearances is not None:
                track.update_appearance(appearances[det_idx])
                
        for local_idx, det_idx in matched_b:
            track = lost_tracks[local_idx]
            self._kalman_update(track, detections[det_idx])
            track.time_since_update = 0
            track.hits += 1
            if appearances is not None:
                track.update_appearance(appearances[det_idx])

        # 6. Gestione Lost Track Manager e Inizializzazione
        self._manage_track_states(unmatched_dets, detections, appearances)

        return self._format_output()

    def _compute_iou(self, kalman_state, detection):
        # Estrazione coordinate dal vettore di stato di Kalman
        cx, cy, w, h = kalman_state[0], kalman_state[1], kalman_state[6], kalman_state[7]
        k_x1, k_y1 = cx - w / 2, cy - h / 2
        k_x2, k_y2 = cx + w / 2, cy + h / 2
        
        # Estrazione coordinate dalla detection di YOLO
        d_x1, d_y1, d_x2, d_y2 = detection[:4]
        
        # Calcolo coordinate dell'intersezione
        xx1 = max(k_x1, d_x1)
        yy1 = max(k_y1, d_y1)
        xx2 = min(k_x2, d_x2)
        yy2 = min(k_y2, d_y2)
        
        w_inter = max(0, xx2 - xx1)
        h_inter = max(0, yy2 - yy1)
        area_inter = w_inter * h_inter
        
        # Calcolo dell'unione
        area_k = w * h
        area_d = (d_x2 - d_x1) * (d_y2 - d_y1)
        area_union = area_k + area_d - area_inter

        if area_union <= 0:
            return 0.0

        return area_inter / area_union

    def _compute_cost_matrix(self, tracks, detections, appearances, det_indices):
        cost_matrix = np.zeros((len(tracks), len(det_indices)))
        GATE_COST = 10000.0 
        
        # --- FIX: Redistribuzione dinamica dei pesi ---
        if appearances is None:
            w_iou, w_app, w_vel = 0.8, 0.0, 0.2 # 80% Spazio, 20% Direzione
        else:
            w_iou, w_app, w_vel = 0.4, 0.4, 0.2
        # ----------------------------------------------
        
        for i, track in enumerate(tracks):
            for j, det_idx in enumerate(det_indices):
                iou = self._compute_iou(track.state, detections[det_idx])
                iou_cost = 1.0 - iou
                
                app_cost = 0.0
                if track.appearance is not None and appearances is not None:
                    app_cost = cdist([track.appearance], [appearances[det_idx]], 'cosine')[0][0]
                
                vel_cost = self._velocity_consistency_cost(track, detections[det_idx])
                
                cost = w_iou * iou_cost + w_app * app_cost + w_vel * vel_cost
                
                # --- FIX: Bonus di perdono per tracce perse di recente ---
                if isinstance(track, Track) and track.state_enum == 'Lost':
                    # Riduciamo il costo se la traccia è stata persa da poco (es. < 10 frame)
                    if track.time_since_update < 10:
                        cost *= 0.5 
                # ---------------------------------------------------------
                
                if iou < self.iou_threshold:
                    cost_matrix[i, j] = GATE_COST
                else:
                    cost_matrix[i, j] = cost

        return cost_matrix
    
    def _cascade_matching(self, tracks, detections, appearances, unmatched_dets):
        matches = []
        
        # Inizializza tutte le tracce come "non associate" all'inizio
        unmatched_trks_indices = list(range(len(tracks)))

        # Cicla dall'età 1 (visto al frame precedente) fino alla max_age
        for level in range(1, self.max_age + 1):
            if len(unmatched_dets) == 0:
                break # Non ci sono più detections da assegnare
                
            # Filtra le tracce che hanno esattamente questa "età"
            level_track_indices = [
                i for i in unmatched_trks_indices 
                if tracks[i].time_since_update == level
            ]
            
            if len(level_track_indices) == 0:
                continue
                
            level_tracks = [tracks[i] for i in level_track_indices]
            
            # Genera la matrice di costo (IoU + Appearance + Velocity)
            cost_matrix = self._compute_cost_matrix(
                level_tracks, detections, appearances, unmatched_dets
            )
            
            # Algoritmo Ungherese per trovare l'assegnazione ottima
            row_indices, col_indices = linear_sum_assignment(cost_matrix)
            
            # Liste temporanee per tenere traccia di chi è stato matchato in questo livello
            matched_dets_this_level = []
            matched_trks_this_level = []

            # Salva solo le assegnazioni valide che superano il Gating (costo < 10000.0)
            for row, col in zip(row_indices, col_indices):
                if cost_matrix[row, col] < 10000.0:  # <-- FIX QUI
                    track_idx = level_track_indices[row]
                    det_idx = unmatched_dets[col]
                    
                    matches.append((track_idx, det_idx))
                    
                    # Aggiungiamo alle liste temporanee
                    matched_dets_this_level.append(det_idx)
                    matched_trks_this_level.append(track_idx)
            
            # Rimuoviamo in modo sicuro gli elementi matchati dalle liste globali
            unmatched_dets = [d for d in unmatched_dets if d not in matched_dets_this_level]
            unmatched_trks_indices = [t for t in unmatched_trks_indices if t not in matched_trks_this_level]

        # Le tracce non associate passano al giro di "Local Re-association" o vengono perse
        unmatched_tracks = unmatched_trks_indices
        
        return matches, unmatched_dets, unmatched_tracks

    def _local_reassociation(self, lost_tracks, detections, appearances, unmatched_dets):
        if len(lost_tracks) == 0 or len(unmatched_dets) == 0:
            return [], unmatched_dets, list(range(len(lost_tracks)))
            
        # Calcoliamo la matrice di costo tra le tracce perse e le detection orfane
        cost_matrix = self._compute_cost_matrix(lost_tracks, detections, appearances, unmatched_dets)
        
        row_indices, col_indices = linear_sum_assignment(cost_matrix)
        
        matches = []
        matched_dets_this_level = []
        matched_trks_this_level = []
        
        for row, col in zip(row_indices, col_indices):
            # Il Gating scarta le associazioni impossibili
            if cost_matrix[row, col] < 10000.0:
                track_idx = row # Indice locale relativo alla lista lost_tracks
                det_idx = unmatched_dets[col]
                
                matches.append((track_idx, det_idx))
                matched_dets_this_level.append(det_idx)
                matched_trks_this_level.append(track_idx)
                
        # Aggiorniamo le liste degli orfani
        unmatched_dets = [d for d in unmatched_dets if d not in matched_dets_this_level]
        unmatched_trks_indices = [i for i in range(len(lost_tracks)) if i not in matched_trks_this_level]
        
        return matches, unmatched_dets, unmatched_trks_indices

    def _velocity_consistency_cost(self, track, detection):
        # Stato stimato: [cx, cy, vx, vy, ax, ay, w, h]
        vx, vy = track.state[2], track.state[3]
        
        # Se il veicolo è fermo o appena nato, il costo direzionale è ininfluente
        if abs(vx) < 1e-2 and abs(vy) < 1e-2:
            return 0.0

        k_cx, k_cy = track.state[0], track.state[1]
        d_cx, d_cy = self._bbox_to_center(detection)[:2]
        
        # Vettore direzione dalla predizione alla nuova misurazione
        dir_x = d_cx - k_cx
        dir_y = d_cy - k_cy
        
        norm_v = np.hypot(vx, vy)
        norm_dir = np.hypot(dir_x, dir_y)
        
        if norm_dir < 1e-2:
            return 0.0
            
        # Cosine similarity: (v * d) / (|v| * |d|)
        cos_sim = (vx * dir_x + vy * dir_y) / (norm_v * norm_dir)
        
        # Mappiamo da [-1, 1] a [0, 1]
        # 0 = Perfettamente concordi (Stessa direzione)
        # 1 = Perfettamente discordi (Direzione opposta)
        cost = (1.0 - cos_sim) / 2.0
        return cost

    def _kalman_predict(self, track):
        # Matrice di transizione F (8x8)
        F = np.eye(8)
        F[0, 2] = F[1, 3] = F[2, 4] = F[3, 5] = 1.0
        F[0, 4] = F[1, 5] = 0.5
        
        # Matrice di rumore di processo Q 
        # (Da tunare: valori più alti rendono il filtro più "reattivo" ma meno "fluido")
        Q = np.eye(8) * 0.01 
        
        # Predizione dello stato e della covarianza
        track.state = np.dot(F, track.state)
        track.covariance = np.linalg.multi_dot([F, track.covariance, F.T]) + Q

    def _bbox_to_center(self, bbox):
        # Aggiunta qui per essere usata da _kalman_update
        return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _kalman_update(self, track, detection):
        # Matrice di misurazione H (4x8) - Mappa [cx, cy, vx, vy, ax, ay, w, h] su [cx, cy, w, h]
        H = np.zeros((4, 8))
        H[0, 0] = H[1, 1] = H[2, 6] = H[3, 7] = 1.0
        
        # Misurazione z [cx, cy, w, h]
        z = np.array(self._bbox_to_center(detection))
        
        # Rumore di misurazione R (incertezza delle bounding box di YOLO)
        R = np.eye(4) * 0.1 
        
        # Calcolo dell'innovazione y e della covarianza dell'innovazione S
        y = z - np.dot(H, track.state)
        S = np.linalg.multi_dot([H, track.covariance, H.T]) + R
        
        # Guadagno di Kalman K
        K = np.linalg.multi_dot([track.covariance, H.T, np.linalg.inv(S)])
        
        # Aggiornamento stato e covarianza
        track.state = track.state + np.dot(K, y)
        I = np.eye(8)
        track.covariance = np.dot((I - np.dot(K, H)), track.covariance)

    def _manage_track_states(self, unmatched_dets, detections, appearances):
        # 1. Aggiornamento degli stati
        for track in self.tracks:
            # Se la traccia è stata appena matchata (time_since_update == 0), è viva
            if track.time_since_update == 0:
                if track.state_enum == 'Tentative' and track.hits >= self.min_hits:
                    track.state_enum = 'Confirmed'
            else:
                # Se non matchata, invecchia
                if track.state_enum == 'Confirmed':
                    track.state_enum = 'Lost'
        
        # 2. Pulizia tracce (più permissiva)
        # Eliminiamo solo quelle che sono 'Lost' da troppo tempo (max_age) 
        # O le 'Tentative' che non hanno mai fatto un hit valido
        self.tracks = [
            t for t in self.tracks 
            if t.time_since_update <= self.max_age
        ]

        # 3. Inizializzazione nuove tracce
        for det_idx in unmatched_dets:
            app = appearances[det_idx] if appearances is not None else None
            new_track = Track(detections[det_idx], self.track_id_counter, app)
            # Le nuove tracce partono come Tentative
            self.tracks.append(new_track)
            self.track_id_counter += 1

    def _format_output(self):
        # Separiamo fin da subito le bounding box dagli ID
        boxes = []
        track_ids = []
        
        for track in self.tracks:
            if track.state_enum == 'Confirmed':
                cx, cy, w, h = track.state[0], track.state[1], track.state[6], track.state[7]
                
                x1 = cx - w / 2
                y1 = cy - h / 2
                x2 = cx + w / 2
                y2 = cy + h / 2
                
                boxes.append([x1, y1, x2, y2])
                track_ids.append(track.track_id)
                
        # Gestione del caso in cui non ci siano tracce attive (evita l'errore "got 0")
        if len(boxes) == 0:
            return np.empty((0, 4)), np.empty((0,), dtype=int)
            
        return np.array(boxes), np.array(track_ids, dtype=int)