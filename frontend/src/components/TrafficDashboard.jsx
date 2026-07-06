import { Activity, CloudRain, Moon, Sun, Wind } from "lucide-react";
import useTraffic from "../hooks/useTraffic";
import VideoFeed from "./VideoFeed";
import CompassGrid from "./CompassGrid";
import AppraisalsTable from "./AppraisalsTable";

// Componente per la selezione del video feed. Genera dinamicamente i bottoni partendo da un array di configurazione.

export function CameraSwitch({ camera, onChange }) {
    const opts = [
        { id: "day1", icon: Sun, label: "Day 1" },
        { id: "day2", icon: Sun, label: "Day 2" },
        { id: "night", icon: Moon, label: "Night" },
        { id: "rain", icon: CloudRain, label: "Rain" },
        { id: "wind", icon: Wind, label: "Wind" },
    ];

    return (
        <div className="inline-flex flex-wrap rounded-md border border-[#262633] bg-[#18181F] p-1">
            {opts.map((o) => {
                const active = camera === o.id;
                const Icon = o.icon;
                
                // Estrazione delle classi Tailwind per mantenere il JSX pulito
                const baseClass = "flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all";
                const activeClass = active ? "bg-[#60A5FA] text-[#0D0D12]" : "text-[#6B7280] hover:text-[#9CA3AF]";

                return (
                    <button key={o.id} onClick={() => onChange(o.id)} title={o.label} className={`${baseClass} ${activeClass}`}>
                        <Icon size={14} />
                        <span className="hidden lg:inline">{o.label}</span>
                    </button>
                );
            })}
        </div>
    );
}

// Componente per lo switch in tempo reale tra i due algoritmi di tracking del backend.
export function TrackerSwitch({ tracker, onChange }) {
    const opts = [
        { id: "tracktrack", label: "TrAcK-TrAcK" },
        { id: "custom", label: "CuStOm-SoRt" },
    ];

    return (
        <div className="inline-flex rounded-md border border-[#262633] bg-[#18181F] p-1">
            {opts.map((o) => {
                const active = tracker === o.id;                
                const baseClass = "rounded px-4 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all";
                const activeClass = active ? "bg-[#60A5FA] text-[#0D0D12]" : "text-[#6B7280] hover:text-[#9CA3AF]";

                return (
                    <button key={o.id} onClick={() => onChange(o.id)} className={`${baseClass} ${activeClass}`}>{o.label}</button>
                );
            })}
        </div>
    );
}

// Dashboard Principale: orchestra lo stato globale e il layout dell'intera applicazione.
export default function TrafficDashboard() {
    
    // Inizializzazione dello stato tramite l'hook custom di gestione API
    const { metrics, appraisals, connected, setTracker, setCamera, videoSrc } = useTraffic();
    
    // Fallback di sicurezza in caso di ritardi nel rendering o risposta API lenta
    const tracker = metrics?.tracker || "tracktrack";
    const camera = metrics?.active_camera || "day1";

    return (
        <div className="App grid-bg flex h-screen flex-col overflow-hidden bg-[#0D0D12] p-4 text-[#F3F4F6] md:p-6 lg:p-8">
            
            {/* ================= HEADER APPLICAZIONE ================= */}
            <header className="mx-auto flex w-full max-w-[1392px] mt-1 shrink-0 flex-col gap-6 pb-6 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md border border-[#262633] bg-[#18181F]">
                        <Activity size={18} className="text-[#60A5FA]" />
                    </div>
                    <div>
                        <h1 className="font-display text-xl font-bold tracking-tight md:text-2xl">
                            Traffic <span className="text-[#60A5FA]">Monitoring</span> Dashboard
                        </h1>
                        <p className="font-mono-data text-[11px] uppercase tracking-[0.2em] text-[#6B7280]">
                            Origin · Destination Analytics
                        </p>
                    </div>
                </div>
                
                {/* Controlli di Stato, Telecamera e Tracker */}
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${connected ? "bg-[#10B981] live-dot" : "bg-[#EF4444]"}`} />
                        <span className="font-mono-data text-[11px] uppercase tracking-wider text-[#9CA3AF]">
                            {connected ? "Connected" : "Disconnected"}
                        </span>
                    </div>
                    <CameraSwitch camera={camera} onChange={setCamera} />
                    <TrackerSwitch tracker={tracker} onChange={setTracker} />
                </div>
            </header>

            {/* ================= CORPO PRINCIPALE ================= */}
            <main className="mx-auto flex w-full max-w-[1392px] flex-1 flex-col items-center justify-start gap-6 min-h-0">
                
                {/* Riquadro Superiore: Streaming Video (sinistra) e Griglia KPI/Bussola (destra) */}
                <div className="flex w-full shrink-0 flex-col items-center justify-between gap-6 lg:flex-row lg:items-start">
                    <VideoFeed 
                        src={videoSrc} 
                        tracker={tracker} 
                        camera={camera} 
                        fps={metrics?.fps} 
                        activeVehicles={metrics?.active_vehicles} 
                        connected={connected} 
                    />
                    <CompassGrid metrics={metrics} />
                </div>
                
                {/* Riquadro Inferiore: Tabella Valutazioni Cronologiche (Appraisals) */}
                <AppraisalsTable appraisals={appraisals} />
                
            </main>
            
        </div>
    );
}