import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Radio } from "lucide-react";

// Genera il mirino angolare (reticolo) tipico delle telecamere di sicurezza.
function ReticleCorners() {
    const baseClass = "pointer-events-none absolute h-5 w-5 border-white/30";
    return (
        <>
            <span className={`${baseClass} left-2 top-2 border-l-2 border-t-2`} />
            <span className={`${baseClass} right-2 top-2 border-r-2 border-t-2`} />
            <span className={`${baseClass} bottom-2 left-2 border-b-2 border-l-2`} />
            <span className={`${baseClass} bottom-2 right-2 border-b-2 border-r-2`} />
        </>
    );
}

// Indicatore di stato in alto a sinistra (Live/Offline + ID Telecamera).
function StreamStatus({ connected, camera }) {
    return (
        <div className="absolute left-3 top-3 flex items-center gap-2 rounded bg-black/55 px-2.5 py-1 backdrop-blur-sm">
            <Radio size={13} className={connected ? "text-red-500 live-dot" : "text-[#6B7280]"} />
            <span className="font-mono-data text-[11px] uppercase tracking-widest text-white/80">
                {connected ? "Live" : "Offline"} · CAM-{camera?.toUpperCase()}
            </span>
        </div>
    );
}

// Indicatore dell'algoritmo di tracciamento attivo (in alto a destra).
function TrackerBadge({ tracker }) {
    return (
        <div 
            className="absolute right-3 top-3 rounded bg-black/55 px-2.5 py-1 font-mono-data 
                       text-[11px] uppercase tracking-widest text-white/70 backdrop-blur-sm"
        >
            {tracker === "tracktrack" ? "Track-Track" : "Custom-SORT"}
        </div>
    );
}

// Barra inferiore con le metriche in tempo reale (FPS, veicoli tracciati).
function BottomMetrics({ fps, activeVehicles }) {
    return (
        <div 
            className="absolute inset-x-0 bottom-0 flex items-center justify-between 
                       bg-gradient-to-t from-black/70 to-transparent px-3 pb-3 pt-8"
        >
            {/* Metrica Sinistra: FPS */}
            <div className="font-mono-data text-[11px] text-white/75 bg-black/55 backdrop-blur-sm px-2.5 py-1 rounded">
                <span className="text-[#6B7280] mr-1">FPS</span>
                <span className="text-[#34D399]">{fps ?? "—"}</span>
            </div>

            {/* Metrica Destra: Tracking */}
            <div className="font-mono-data text-[11px] text-white/75 bg-black/55 backdrop-blur-sm px-2.5 py-1 rounded">
                <span className="text-[#6B7280] mr-1">TRACKING</span>
                <span>{activeVehicles ?? 0}</span>
            </div>
        </div>
    );
}

// Componente principale per la visualizzazione dello streaming video (MJPEG).
export default function VideoFeed({ src, tracker, camera, fps, activeVehicles, connected }) {
    const [videoUrl, setVideoUrl] = useState(src);

    // Evita l'uso della cache del browser forzando il caricamento di un nuovo frame 
    // tramite un timestamp univoco quando la telecamera o la connessione cambiano.
    useEffect(() => {
        if (connected) setVideoUrl(`${src}?cam=${camera}&t=${Date.now()}`);        
    }, [connected, src, camera]);

    return (
        <motion.section 
            layout 
            className="relative aspect-video h-[500px] w-auto shrink-0 max-w-full overflow-hidden 
                       rounded-md border border-[#262633] bg-black shadow-lg"
        >
            {/* Livello 1: Flusso Video o Messaggio di Errore */}
            {connected ? (
                <img src={videoUrl} alt="Live feed" className="h-full w-full object-cover" />
            ) : (
                <div className="flex h-full w-full items-center justify-center font-mono-data text-sm text-[#6B7280]">
                    SIGNAL LOST — reconnecting…
                </div>
            )}

            {/* Livello 2: Sovraimpressioni UI (HUD) */}
            <ReticleCorners />
            <StreamStatus connected={connected} camera={camera} />
            <TrackerBadge tracker={tracker} />
            <BottomMetrics fps={fps} activeVehicles={activeVehicles} />
            
        </motion.section>
    );
}