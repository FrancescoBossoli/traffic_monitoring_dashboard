import os
import time
import threading
import cv2
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

from backend.camera import ThreadedCamera
from backend.trackers.custom_tracker import CustomTracker
from backend.trackers.tracktrack_tracker import TrackTrackTracker as TTT
from backend.traffic_analyzer import TrafficAnalyzer


# =====================================================================
# HOOK DI AVVIO FASTAPI
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inizializza il thread di elaborazione."""
    threading.Thread(
        target=run_video_pipeline,
        daemon=True
    ).start()

    yield

app = FastAPI(lifespan=lifespan)

# Gestione percorsi e directory statiche
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)
FE_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FE_DIR, exist_ok=True)
app.mount("/frontend", StaticFiles(directory=FE_DIR), name="frontend")

# Gestione CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variabili Globali Sincronizzate
app_metrics = {
    "count_N_W": 0, "count_N_S": 0, "count_N_E": 0,
    "count_S_E": 0, "count_S_N": 0, "count_S_W": 0,
    "count_W_S": 0, "count_W_E": 0, "count_W_N": 0,
    "count_E_N": 0, "count_E_W": 0, "count_E_S": 0,
    "fps": 0,
    "status": "ANALYZING",
    "appraisals": [],
    "infractions": [],
    "total_crosses": 0,
    "active_camera": "day1",
    "tracker": "tracktrack",
}

# Stato di controllo della pipeline
pipeline_config = {"active_tracker": "tracktrack", "active_camera": "day1"}

# Frame globale annotato condiviso con l'endpoint di streaming
current_annotated_frame = None

# Configurazione geometriche dei varchi e delle corsie
PERIMETER = {
    "North_Line": ((242, 346), (664, 308)),
    "South_Line": ((395, 580), (1048, 506)),
    "West_Line": ((100, 390), (154, 542)),
    "East_Line": ((845, 336), (1081, 440)),
}

LINES_CONFIG = {
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
    "East_Right": ((845, 336), (875, 350)),
}

FLUO_COLORS = [
    (255, 255, 0), (255, 0, 255), (0, 255, 255), (0, 255, 128),
]


def get_video_source(cam_id: str) -> str:
    """Restituisce il percorso del video o un fallback sicuro."""
    source = os.path.join(BACKEND_DIR, "data", "raw", f"{cam_id}.mp4")
    if not os.path.exists(source):
        source = os.path.join(BACKEND_DIR, "data", "raw", "day1.mp4")
    return source


def get_native_fps(cap) -> float:
    """Tenta di recuperare gli FPS nativi dalla sorgente video."""
    try:
        fps = cap.cap.get(cv2.CAP_PROP_FPS)
        return fps if fps > 0 else 30.0
    except Exception:
        return 30.0


def reset_runtime_metrics():
    """Ripristina allo stato iniziale il dizionario globale delle metriche."""
    global app_metrics
    app_metrics = {
        "count_N_W": 0, "count_N_S": 0, "count_N_E": 0,
        "count_S_E": 0, "count_S_N": 0, "count_S_W": 0,
        "count_W_S": 0, "count_W_E": 0, "count_W_N": 0,
        "count_E_N": 0, "count_E_W": 0, "count_E_S": 0,
        "fps": 0,
        "status": "ANALYZING",
        "appraisals": [],
        "infractions": [],
        "total_crosses": 0,
        "active_camera": pipeline_config["active_camera"],
        "tracker": pipeline_config["active_tracker"],
    }


def init_trackers():
    """Inizializza l'istanza dei tracker disponibili."""
    return {
        "tracktrack": TTT(os.path.join(BACKEND_DIR, "config.yaml")),
        "custom": CustomTracker(),
    }


# =====================================================================
# BACKGROUND TASK: Pipeline Singola (Avviata all'accensione del server)
# =====================================================================
def run_video_pipeline():
    global app_metrics, current_annotated_frame

    current_cam_id = pipeline_config["active_camera"]
    video_source = get_video_source(current_cam_id)

    print(f"[DEBUG] Avvio pipeline video base: {video_source}")
    cap = ThreadedCamera(video_source, condition=current_cam_id).start()
    native_fps = get_native_fps(cap)

    model = YOLO(os.path.join(BACKEND_DIR, "weights", "yolov8s.pt"))
    trackers_store = init_trackers()
    analyzer = TrafficAnalyzer(LINES_CONFIG)
    prev_time = time.time()

    while True:
        # Controllo cambio telecamera a runtime
        if pipeline_config["active_camera"] != current_cam_id:
            cap.stop()
            current_cam_id = pipeline_config["active_camera"]
            video_source = get_video_source(current_cam_id)
            print(f"[DEBUG] Cambio telecamera in volo -> '{current_cam_id}'")

            cap = ThreadedCamera(
                video_source, condition=current_cam_id
            ).start()
            native_fps = get_native_fps(cap)

            reset_runtime_metrics()
            analyzer = TrafficAnalyzer(LINES_CONFIG)
            trackers_store = init_trackers()
            continue

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        # Calcolo degli FPS del server
        current_time = time.time()
        time_diff = current_time - prev_time
        current_fps = int(1 / time_diff) if time_diff > 0 else 0
        prev_time = current_time

        # Disegno delle linee di perimetro
        for line in PERIMETER.values():
            cv2.line(frame, line[0], line[1], (0, 255, 255), 1)

        # Tracciamento tramite l'engine attivo
        active_engine = trackers_store[pipeline_config["active_tracker"]]
        boxes, track_ids = active_engine.update(model, frame)

        if len(boxes) > 0:
            analyzer.update(boxes, track_ids, fps=native_fps)
            c_ids = analyzer.crossed_ids

            # Preparazione liste per scrittura atomica
            current_appraisals = []
            tracker_label = (
                "Track-Track"
                if pipeline_config["active_tracker"] == "tracktrack"
                else "Custom-Sort"
            )

            for app_data in analyzer.appraisals.values():
                app_data["tracker"] = tracker_label
                current_appraisals.append(app_data.copy())

            # Calcolo analitico rotte di intersezione
            ids_n_w = c_ids["North_Right"].intersection(c_ids["West_In"])
            ids_n_s = (
                c_ids["North_Right"].intersection(c_ids["South_In"])
            ).union(c_ids["North_Mid"].intersection(c_ids["South_In"]))
            ids_n_e = c_ids["North_Left"].intersection(c_ids["East_In"])

            ids_s_e = c_ids["South_Right"].intersection(c_ids["East_In"])
            ids_s_n = c_ids["South_Mid"].intersection(c_ids["North_In"])
            ids_s_w = c_ids["South_Left"].intersection(c_ids["West_In"])

            ids_w_s = c_ids["West_Right"].intersection(c_ids["South_In"])
            ids_w_e = c_ids["West_Mid"].intersection(c_ids["East_In"])
            ids_w_n = c_ids["West_Left"].intersection(c_ids["North_In"])

            ids_e_n = c_ids["East_Right"].intersection(c_ids["North_In"])
            ids_e_w = c_ids["East_Mid"].intersection(c_ids["West_In"])
            ids_e_s = c_ids["East_Left"].intersection(c_ids["South_In"])

            # Costruzione del dizionario locale temporaneo
            local_metrics = {
                "count_N_W": len(ids_n_w), "count_N_S": len(ids_n_s),
                "count_N_E": len(ids_n_e), "count_S_E": len(ids_s_e),
                "count_S_N": len(ids_s_n), "count_S_W": len(ids_s_w),
                "count_W_S": len(ids_w_s), "count_W_E": len(ids_w_e),
                "count_W_N": len(ids_w_n), "count_E_N": len(ids_e_n),
                "count_E_W": len(ids_e_w), "count_E_S": len(ids_e_s),
                "fps": current_fps,
                "status": "ANALYZING",
                "appraisals": current_appraisals,
                "infractions": list(analyzer.infractions),
                "total_crosses": sum(len(s) for s in c_ids.values()),
                "active_camera": current_cam_id,
                "tracker": pipeline_config["active_tracker"],
            }

            # Scrittura atomica
            app_metrics = local_metrics

            # Unione rotte per grafica
            all_completed = set().union(
                ids_n_w, ids_n_s, ids_n_e, ids_s_e, ids_s_n, ids_s_w,
                ids_w_s, ids_w_e, ids_w_n, ids_e_n, ids_e_w, ids_e_s,
            )

            # Annotazione grafica del frame
            for box, raw_track_id in zip(boxes, track_ids):
                track_id = raw_track_id
                while (
                    hasattr(analyzer, "id_aliases")
                    and track_id in analyzer.id_aliases
                ):
                    track_id = analyzer.id_aliases[track_id]

                x1, y1, x2, y2 = map(int, box)
                color = FLUO_COLORS[track_id % len(FLUO_COLORS)]

                is_speeding = any(
                    inf["vehicle"] == str(track_id)
                    for inf in analyzer.infractions
                )

                if is_speeding:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                    cv2.putText(
                        frame, "SPEEDING!", (x1, y1 - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                    )
                elif track_id in all_completed:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 4)
                else:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                cv2.rectangle(
                    frame, (x1, y1 - 20), (x1 + 80, y1), (0, 0, 0), -1
                )
                cv2.putText(
                    frame, f"ID: {track_id}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    color if not is_speeding else (0, 0, 255), 2,
                )

        # Salvataggio atomico del frame per lo streaming web
        current_annotated_frame = frame.copy()


# =====================================================================
# GENERATORE PER LO STREAMING WEB
# =====================================================================
def generate_frames():
    """Legge semplicemente l'ultimo frame annotato dal thread principale."""
    while True:
        if current_annotated_frame is not None:
            ret, buffer = cv2.imencode(".jpg", current_annotated_frame)
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
        # Pausa per limitare il feed web a ~30fps ed evitare spam di rete
        time.sleep(0.03)


# =====================================================================
# ENDPOINTS API WEB
# =====================================================================

@app.get("/api/metrics")
def get_metrics():
    return app_metrics


@app.get("/")
def index():
    return FileResponse(os.path.join(FE_DIR, "index.html"))


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/tracker/{mode}")
def switch_tracker_endpoint(mode: str):
    if mode in ["tracktrack", "custom"]:
        pipeline_config["active_tracker"] = mode
        return {"status": "ok", "current": mode}
    return {"status": "error", "message": "Tracker invalido"}


@app.post("/api/camera/{cam_id}")
def switch_camera_endpoint(cam_id: str):
    if cam_id in ["day1", "day2", "night", "rain", "wind"]:
        pipeline_config["active_camera"] = cam_id
        return {"status": "ok", "current": cam_id}
    return {"status": "error", "message": "Camera invalida"}


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
