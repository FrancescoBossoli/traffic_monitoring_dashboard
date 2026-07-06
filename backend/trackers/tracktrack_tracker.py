import numpy as np


class TrackTrackTracker:
    """Tracker che delega il tracking multi-oggetto direttamente al modello."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path

    def update(self, model, frame) -> tuple[np.ndarray, list[int]]:
        """
        Esegue il tracking nativo sul frame corrente.
        Restituisce le bounding box e i rispettivi ID univoci.
        """
        # Esecuzione del tracking integrato sfruttando il file di config
        results = model.track(
            frame,
            persist=True,
            tracker=self.config_path,
            classes=[2, 3, 5, 7],  # Auto, Moto, Bus, Camion
            quantize=16,
            verbose=False,
        )

        # Verifica della presenza di box e ID validi nel risultato
        if (
            results[0].boxes is not None
            and results[0].boxes.id is not None
        ):
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            return boxes, track_ids

        # Restituzione di array vuoti strutturati in caso di mancata detection
        return np.empty((0, 4)), []
