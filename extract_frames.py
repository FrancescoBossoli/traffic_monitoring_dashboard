import os
import cv2


def extract_frames(video_path, output_dir, num_frames=30):
    """
    Estrae un numero fisso di frame equidistanti da un video.
    Salva i frames estratti all'interno della directory specificata.
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        print(f"[ERROR] Impossibile leggere il video: {video_path}")
        cap.release()
        return

    # Calcola il passo in frame tra un'estrazione e l'altra
    step = max(1, total_frames // num_frames)

    print(f"[INFO] Elaborazione di: {video_path} ({total_frames} frame)")

    count = 0
    while count < num_frames:
        # Imposta la testina del lettore video sul frame corretto
        target_frame = count * step
        if target_frame >= total_frames:
            break

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        success, image = cap.read()

        if not success:
            break

        # Salva il frame con formattazione numerica a tre cifre
        file_path = os.path.join(output_dir, f"frame_{count:03d}.jpg")
        cv2.imwrite(file_path, image)
        count += 1

    cap.release()


# =====================================================================
# ESECUZIONE ESTRATTORE DATASET DI TEST
# =====================================================================
if __name__ == "__main__":
    # Generazione dei campioni per le diverse condizioni meteo e di luce
    extract_frames("backend/data/raw/day1.mp4", "dataset_test/day")
    extract_frames("backend/data/raw/night.mp4", "dataset_test/night")
    extract_frames("backend/data/raw/rain.mp4", "dataset_test/rain")
