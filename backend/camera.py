from queue import Queue
from threading import Thread
import time
import cv2
import numpy as np


class ThreadedCamera:
    """
    Gestisce la lettura asincrona di un video tramite un thread dedicato.
    Usa una coda (buffer) per evitare di perdere frame e applica filtri
    meteo specifici per ottimizzare l'immagine prima del tracking.
    """

    def __init__(self, source, condition="day1", queue_size=256):
        """Inizializza la cattura video e la coda tampone."""
        self.cap = cv2.VideoCapture(source)
        self.condition = condition
        self.Q = Queue(maxsize=queue_size)
        self.stopped = False

    def start(self):
        """Avvia il thread parallelo per la lettura dei frame."""
        Thread(target=self.update, args=(), daemon=True).start()
        return self

    def _apply_night_filters(self, frame):
        """Applica filtri per limitare l'abbagliamento dei fari notturni."""
        # Capping Alte Luci in spazio HSV per ridurre gli aloni
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        v = np.where(v > 200, 200, v)
        hsv = cv2.merge((h, s, v))
        frame_opt = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        # Correzione Gamma per schiarire le zone d'ombra
        gamma = 1.3
        lut = np.empty((1, 256), np.uint8)
        for i in range(256):
            lut[0, i] = np.clip(
                pow(i / 255.0, 1.0 / gamma) * 255.0, 0, 255
            )
        frame_opt = cv2.LUT(frame_opt, lut)

        # CLAHE morbido per esaltare i dettagli delle lamiere al buio
        lab = cv2.cvtColor(frame_opt, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
        cl = clahe.apply(l_ch)
        lab = cv2.merge((cl, a_ch, b_ch))

        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _apply_rain_filters(self, frame):
        """
        Applica un filtro bilaterale per attenuare il rumore della pioggia.
        """
        return cv2.bilateralFilter(
            frame, d=9, sigmaColor=75, sigmaSpace=75
        )

    def update(self):
        """IL PRODUCER: Legge dal disco, elabora e riempie la coda."""
        while not self.stopped:
            if not self.Q.full():
                ret, raw_frame = self.cap.read()

                # Loop infinito per la Dashboard se il video termina
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_opt = raw_frame

                # Applicazione condizionale dei filtri meteo dedicati
                if self.condition == "night":
                    frame_opt = self._apply_night_filters(frame_opt)
                elif self.condition == "rain":
                    frame_opt = self._apply_rain_filters(frame_opt)

                self.Q.put(frame_opt)
            else:
                # Evita il surriscaldamento della CPU se la coda è piena
                time.sleep(0.001)

    def read(self):
        """IL CONSUMER: Estrae il frame più vecchio dalla coda (FIFO)."""
        if self.stopped and self.Q.empty():
            return False, None

        # Attesa in caso di coda temporaneamente vuota ma con thread attivo
        while self.Q.empty() and not self.stopped:
            time.sleep(0.001)

        if not self.Q.empty():
            return True, self.Q.get()

        return False, None

    def isOpened(self):
        """Verifica se la risorsa video o il buffer sono attivi."""
        return self.cap.isOpened() or not self.Q.empty()

    def set(self, propId, value):
        """Permette il riavvolgimento o il cambio di traccia del video."""
        with self.Q.mutex:
            self.Q.queue.clear()
        self.cap.set(propId, value)
        if self.stopped:
            self.stopped = False
            self.start()

    def stop(self):
        """Interrompe la cattura e rilascia le risorse."""
        self.release()

    def release(self):
        """Rilascia l'istanza di OpenCV e ferma il loop del thread."""
        self.stopped = True
        self.cap.release()
