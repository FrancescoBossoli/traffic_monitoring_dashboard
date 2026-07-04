import cv2
from threading import Thread
from queue import Queue
import time
import numpy as np

class ThreadedCamera:
    def __init__(self, source, condition="day1", queue_size=256):
        """
        Usa una coda per evitare di perdere i frame del video.
        :param source: Percorso del file video (o ID della webcam)
        :param condition: Condizione atmosferica ('day1', 'day2', 'night', 'rain', 'wind')
        """
        self.cap = cv2.VideoCapture(source)
        self.condition = condition
        # Inizializziamo il buffer (la memoria tampone)
        self.Q = Queue(maxsize=queue_size)
        self.stopped = False

    def start(self):
        Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        """IL PRODUCER: Legge dal disco, ottimizza e riempie la coda."""
        while not self.stopped:
            # Se la coda non è piena, aggiungiamo un frame
            if not self.Q.full():
                ret, raw_frame = self.cap.read()
                
                # Se il video finisce, lo facciamo ripartire da capo (Loop infinito per la Dashboard)
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                
                # ==================================================
                # 1. OTTIMIZZAZIONE GLOBALE: Ridimensionamento
                # ==================================================
                frame_opt = raw_frame
                
                # ==================================================
                # 2. FILTRI SPECIFICI PER CONDIZIONE METEO
                # ==================================================
                if self.condition == "night":
                    # NOTTE: I fari sparati in camera accecano YOLO e distruggono le bounding box.
                    # 1. Capping Alte Luci: schiacciamo i bianchi estremi per limitare l'alone "starburst"
                    hsv = cv2.cvtColor(frame_opt, cv2.COLOR_BGR2HSV)
                    h, s, v = cv2.split(hsv)
                    v = np.where(v > 200, 200, v)  # Taglia i picchi abbaglianti
                    hsv = cv2.merge((h, s, v))
                    frame_opt = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
                    
                    # 2. Correzione Gamma più dolce: schiarisce l'asfalto senza esplodere i fari
                    gamma = 1.3
                    lookUpTable = np.empty((1,256), np.uint8)
                    for i in range(256):
                        lookUpTable[0,i] = np.clip(pow(i / 255.0, 1.0 / gamma) * 255.0, 0, 255)
                    frame_opt = cv2.LUT(frame_opt, lookUpTable)
                    
                    # 3. CLAHE (Morbido): Migliora i dettagli delle lamiere nel buio
                    lab = cv2.cvtColor(frame_opt, cv2.COLOR_BGR2LAB)
                    l, a, b = cv2.split(lab)
                    clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8,8))
                    cl = clahe.apply(l)
                    lab = cv2.merge((cl, a, b))
                    frame_opt = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
                    
                elif self.condition == "rain":
                    # PIOGGIA: Applichiamo Filtro Bilaterale per togliere rumore/pioggia
                    frame_opt = cv2.bilateralFilter(frame_opt, d=9, sigmaColor=75, sigmaSpace=75)
                
                # Inseriamo il frame ottimizzato nella coda
                self.Q.put(frame_opt)
            else:
                # Se la coda è piena, il thread si mette in pausa per non sovraccaricare la RAM
                time.sleep(0.001)

    def read(self):
        """IL CONSUMER: Estrae il frame più vecchio dalla coda (FIFO)."""
        if self.stopped and self.Q.empty():
            return False, None

        # Se la coda è momentaneamente vuota ma il video non è finito, aspetta
        while self.Q.empty() and not self.stopped:
            time.sleep(0.001)

        if not self.Q.empty():
            return True, self.Q.get()
        else:
            return False, None

    def isOpened(self):
        return self.cap.isOpened() or not self.Q.empty()

    def set(self, propId, value):
        """Supporto per il riavvolgimento del video."""
        # Svuotiamo la coda dai frame vecchi prima di riavvolgere
        with self.Q.mutex:
            self.Q.queue.clear()
        self.cap.set(propId, value)
        if self.stopped:
            self.stopped = False
            self.start()

    def stop(self):
        """Alias per compatibilità con il backend che gestisce il cambio telecamere"""
        self.release()

    def release(self):
        self.stopped = True
        self.cap.release()