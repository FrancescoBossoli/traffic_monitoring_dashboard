import cv2
import time
import uvicorn
import os
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

from backend.traffic_analyzer import TrafficAnalyzer
from backend.camera import ThreadedCamera
from backend.trackers.tracktrack_tracker import TrackTrackTracker as TTT
from backend.trackers.custom_tracker import CustomTracker

app = FastAPI()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)
FE_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FE_DIR, exist_ok=True)  # Crea la cartella in automatico
app.mount("/frontend", StaticFiles(directory=FE_DIR), name="frontend")

# Gestione CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Variabili globali aggiunte le chiavi per la mappa e il trigger per il log
app_metrics = {
    "count_N_W": 0, "count_N_S": 0, "count_N_E": 0,
    "count_S_E": 0, "count_S_N": 0, "count_S_W": 0,
    "count_W_S": 0, "count_W_E": 0, "count_W_N": 0,
    "count_E_N": 0, "count_E_W": 0, "count_E_S": 0,
    "fps": 0,
    "status": "ANALYZING",
    "appraisals": [],
    "total_crosses": 0
}

# Stato di controllo della pipeline
pipeline_config = {
    "active_tracker": "tracktrack",
    "active_camera": "day1"
}


def generate_frames():
    current_cam_id = pipeline_config["active_camera"]
    video_source = os.path.join(BACKEND_DIR, "data", "raw", f"{current_cam_id}.mp4")
    
    # Se il file richiesto non esiste (perché magari ti mancano dei video), fa un fallback su day1
    if not os.path.exists(video_source):
        print(f"[WARN] File {video_source} non trovato. Fallback su day1.mp4")
        video_source = os.path.join(BACKEND_DIR, "data", "raw", "day1.mp4")

    print(f"[DEBUG] Avvio telecamera: {video_source} in modalità '{current_cam_id}'")
    cap = ThreadedCamera(video_source, condition=current_cam_id).start()

    # Estraiamo gli FPS originali del video per calcoli fisici accurati
    try:
        native_fps = cap.cap.get(cv2.CAP_PROP_FPS)
        if native_fps <= 0: native_fps = 30.0
    except:
        native_fps = 30.0

    model_path = os.path.join(BACKEND_DIR, "weights", "yolov8s.pt")
    model = YOLO(model_path)    

    trackers_store = {
        "tracktrack": TTT(os.path.join(BACKEND_DIR, "config.yaml")),
        "custom": CustomTracker()
    }

    fluo_colors = [(255, 255, 0), (255, 0, 255), (0, 255, 255), (0, 255, 128)]

    perimeter = {
        "North_Line": ((242, 346), (664, 308)),
        "South_Line": ((395, 580), (1048, 506)),
        "West_Line": ((100, 390), (154, 542)),
        "East_Line": ((845, 336), (1081, 440)),
    }

    lines_config = {
        "North_In": ((507, 322), (664, 308)),
        "North_Left": ((434, 328), (507, 322)),
        "North_Mid": ((356, 336), (434, 328)),
        "North_Right": ((242, 346), (356, 336)),

        "South_In": ((395, 580), (703, 546)),
        "South_Left": ((703, 546), (806, 534)),
        "South_Mid": ((806, 534), (923, 520)),
        "South_Right": ((923, 520), (1048, 506)),

        "West_In": ((100, 390), (116, 434)),
        "West_Left": ((116, 434), (127, 464)),
        "West_Mid": ((127, 464), (140, 500)),
        "West_Right": ((140, 500), (154, 542)),

        "East_In": ((964, 389), (1081, 440)),
        "East_Left": ((915, 367), (964, 389)),
        "East_Mid": ((875, 350), (915, 367)),
        "East_Right": ((845, 336), (875, 350))
    }
    analyzer = TrafficAnalyzer(lines_config)

    prev_time = time.time()

    while True:
        # 1. CONTROLLO CAMBIO TELECAMERA IN TEMPO REALE
        if pipeline_config["active_camera"] != current_cam_id:
            cap.stop()
            current_cam_id = pipeline_config["active_camera"]
            new_source = os.path.join(BACKEND_DIR, "data", "raw", f"{current_cam_id}.mp4")
            if not os.path.exists(new_source): new_source = os.path.join(BACKEND_DIR, "data", "raw", "day1.mp4")
            
            print(f"[DEBUG] Cambio telecamera in volo -> '{current_cam_id}'")
            cap = ThreadedCamera(new_source, condition=current_cam_id).start()

            # Ricalcolo degli FPS in caso di video diverso
            try:
                native_fps = cap.cap.get(cv2.CAP_PROP_FPS)
                if native_fps <= 0: native_fps = 30.0
            except:
                native_fps = 30.0
            
            # Reset delle metriche 
            for key in app_metrics:
                if key.startswith("count_"): app_metrics[key] = 0
            app_metrics["appraisals"] = []
            app_metrics["total_crosses"] = 0
            app_metrics["infractions"] = []
            analyzer = TrafficAnalyzer(lines_config)  # Reset incroci registrati

            # Reset completo della memoria dei Tracker
            trackers_store = {
                "tracktrack": TTT(os.path.join(BACKEND_DIR, "config.yaml")),
                "custom": CustomTracker()
            }
            continue

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        # Calcolo FPS
        current_time = time.time()
        time_diff = current_time - prev_time
        if time_diff > 0:
            app_metrics["fps"] = int(1 / time_diff)  # FPS del server (performance)
        prev_time = current_time

        # Perimetro a visione
        for line in perimeter.values():
            cv2.line(frame, line[0], line[1], (0, 255, 255), 1)

        # Tracciamento e logica Analyzer
        active_engine = trackers_store[pipeline_config["active_tracker"]]
        boxes, track_ids = active_engine.update(model, frame)

        if len(boxes) > 0:
            # Passiamo i veri FPS del video all'analizzatore
            analyzer.update(boxes, track_ids, fps=native_fps)
            c_ids = analyzer.crossed_ids

            # Salviamo le infrazioni calcolate (classiche)
            app_metrics["infractions"] = analyzer.infractions

            # ==========================================
            # TRASFERIMENTO APPRAISALS 
            # ==========================================
            tracker_label = "Track-Track" if pipeline_config["active_tracker"] == "tracktrack" else "Custom-Sort"
            
            appraisals_list = []
            for app_data in analyzer.appraisals.values():
                app_data["tracker"] = tracker_label
                appraisals_list.append(app_data)
                
            app_metrics["appraisals"] = appraisals_list

            # Gestione totali (rimasto invariato)
            current_total_crosses = 0
            for line_name, crossed_set in c_ids.items():
                current_total_crosses += len(crossed_set)
            
            app_metrics["total_crosses"] = current_total_crosses
            # ==========================================

            # ==========================================
            # 2. CALCOLO DELLE 12 ROTTE TRAMITE INTERSEZIONE
            # ==========================================
            # Da Nord
            ids_n_w = c_ids["North_Right"].intersection(c_ids["West_In"])
            ids_n_s = (
                c_ids["North_Right"].intersection(c_ids["South_In"])
            ).union(
                c_ids["North_Mid"].intersection(c_ids["South_In"])
            )
            ids_n_e = c_ids["North_Left"].intersection(c_ids["East_In"])

            # Da Sud
            ids_s_e = c_ids["South_Right"].intersection(c_ids["East_In"])
            ids_s_n = c_ids["South_Mid"].intersection(c_ids["North_In"])
            ids_s_w = c_ids["South_Left"].intersection(c_ids["West_In"])

            # Da Ovest
            ids_w_s = c_ids["West_Right"].intersection(c_ids["South_In"])
            ids_w_e = c_ids["West_Mid"].intersection(c_ids["East_In"])
            ids_w_n = c_ids["West_Left"].intersection(c_ids["North_In"])

            # Da Est
            ids_e_n = c_ids["East_Right"].intersection(c_ids["North_In"])
            ids_e_w = c_ids["East_Mid"].intersection(c_ids["West_In"])
            ids_e_s = c_ids["East_Left"].intersection(c_ids["South_In"])

            # AGGIORNAMENTO DI TUTTE LE METRICHE GLOBALI
            app_metrics.update({
                "count_N_W": len(ids_n_w), "count_N_S": len(ids_n_s),
                "count_N_E": len(ids_n_e), "count_S_E": len(ids_s_e),
                "count_S_N": len(ids_s_n), "count_S_W": len(ids_s_w),
                "count_W_S": len(ids_w_s), "count_W_E": len(ids_w_e),
                "count_W_N": len(ids_w_n), "count_E_N": len(ids_e_n),
                "count_E_W": len(ids_e_w), "count_E_S": len(ids_e_s)
            })

            # Set che unisce tutti i veicoli che hanno completato manovre
            all_completed = set().union(
                ids_n_w, ids_n_s, ids_n_e, ids_s_e, ids_s_n, ids_s_w,
                ids_w_s, ids_w_e, ids_w_n, ids_e_n, ids_e_w, ids_e_s
            )

            for box, raw_track_id in zip(boxes, track_ids):
                # FIX: Risolviamo l'ID nel caso in cui l'analizzatore lo abbia "riparato/cucito" dopo un'occlusione fari
                track_id = raw_track_id
                while hasattr(analyzer, 'id_aliases') and track_id in analyzer.id_aliases:
                    track_id = analyzer.id_aliases[track_id]
                    
                x1, y1, x2, y2 = map(int, box)
                color = fluo_colors[track_id % len(fluo_colors)]

                # Aggiunto Alert Rosso per Speeding
                is_speeding = any(inf['vehicle'] == str(track_id) for inf in analyzer.infractions)

                # Logica visiva
                if is_speeding:
                    # Red Box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                    cv2.putText(
                        frame, "SPEEDING!", (x1, y1 - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2
                    )
                elif track_id in all_completed:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 4)
                else:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Green Box
                cv2.rectangle(
                    frame, (x1, y1 - 20), (x1 + 80, y1), (0, 0, 0), -1
                )
                cv2.putText(
                    frame, f"ID: {track_id}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color
                    if not is_speeding else (0, 0, 255), 2
                )

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )


# ==========================================
# ENDPOINTS WEB
# ==========================================
@app.get("/api/metrics")
def get_metrics():
    app_metrics["active_camera"] = pipeline_config["active_camera"]
    app_metrics["tracker"] = pipeline_config["active_tracker"]
    return app_metrics


@app.get("/api/reports")
def get_reports():
    return {"infractions": app_metrics.get("infractions", [])}


@app.get("/")
def index():
    return FileResponse(os.path.join(FE_DIR, "index.html"))


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/api/tracker/{mode}")
def switch_tracker_endpoint(mode: str):
    if mode in ["tracktrack", "custom"]:
        pipeline_config["active_tracker"] = mode
        return {"status": "ok", "current": mode}
    return {"status": "error", "message": "Tracker invalido"}


# Cambio Telecamera/Meteo
@app.post("/api/camera/{cam_id}")
def switch_camera_endpoint(cam_id: str):
    if cam_id in ["day1", "day2", "night", "rain", "wind"]:
        pipeline_config["active_camera"] = cam_id
        return {"status": "ok", "current": cam_id}
    return {"status": "error", "message": "Camera invalida"}


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)