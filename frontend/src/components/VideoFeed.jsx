import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Maximize2, Minimize2, Radio } from "lucide-react";

export default function VideoFeed({ src, tracker, camera, fps, activeVehicles, connected }) {
    const [compact, setCompact] = useState(false);
    const [videoUrl, setVideoUrl] = useState(src);

    // Busta la cache del video quando cambiamo camera o ci riconnettiamo
    useEffect(() => {
        if (connected) setVideoUrl(`${src}?cam=${camera}&t=${Date.now()}`);
    }, [connected, src, camera]);

    return (
        <motion.section layout className="relative h-[500px] w-auto aspect-video shrink-0 overflow-hidden rounded-md border border-[#262633] bg-black max-w-full shadow-lg">
            {connected ? (
                <img src={videoUrl} alt="Live feed" className="h-full w-full object-cover" />
            ) : (
                <div className="flex h-full w-full items-center justify-center text-[#6B7280] text-sm font-mono-data">SIGNAL LOST — reconnecting…</div>
            )}
            <span className="pointer-events-none absolute left-2 top-2 h-5 w-5 border-l-2 border-t-2 border-white/30" />
            <span className="pointer-events-none absolute right-2 top-2 h-5 w-5 border-r-2 border-t-2 border-white/30" />
            <span className="pointer-events-none absolute bottom-2 left-2 h-5 w-5 border-b-2 border-l-2 border-white/30" />
            <span className="pointer-events-none absolute bottom-2 right-2 h-5 w-5 border-b-2 border-r-2 border-white/30" />

            <div className="absolute left-3 top-3 flex items-center gap-2 rounded bg-black/55 px-2.5 py-1 backdrop-blur-sm">
                <Radio size={13} className={connected ? "text-red-500 live-dot" : "text-[#6B7280]"} />
                <span className="font-mono-data text-[11px] uppercase tracking-widest text-white/80">
                    {connected ? "Live" : "Offline"} · CAM-{camera?.toUpperCase()}
                </span>
            </div>
            <div className="absolute right-3 top-3 rounded bg-black/55 px-2.5 py-1 font-mono-data text-[11px] uppercase tracking-widest text-white/70 backdrop-blur-sm">
                {tracker === "tracktrack" ? "Track-Track" : "Custom-SORT"}
            </div>
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-3 bg-gradient-to-t from-black/70 to-transparent px-3 pb-3 pt-8">
                <div className="flex gap-5 font-mono-data text-[11px] text-white/75">
                    <span><span className="text-[#6B7280]">FPS </span><span className="text-[#34D399]">{fps ?? "—"}</span></span>
                    <span><span className="text-[#6B7280]">TRACKING </span>{activeVehicles ?? 0}</span>
                </div>
            </div>
        </motion.section>
    );
}