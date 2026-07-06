import { Activity } from "lucide-react";

// Mappatura stili grafici basata sul tipo di infrazione
const INFRACTION_STYLES = {
    "Speeding": "bg-amber-500/10 text-amber-400 border-red-500/20",
    "Wrong Lane": "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20",
    "Illegal Turn": "bg-sky-500/10 text-sky-400 border-sky-500/20",
    none: "bg-gray-500/10 text-gray-400 border-gray-500/20", // Default sicuro
};

// Colonne della tabella RILEVAMENTI
const COLS = [
    "Timestamp",
    "Origin",
    "Destination",
    "Vehicle ID",
    "Infraction",
    "Tracker",
    "Peak Speed",
];

// Helper per determinare il colore della velocità in base al limite
const getSpeedColor = (speed) => {
    if (!speed) return "text-[#6B7280]"; // Grigio neutro per velocità nulla
    if (speed >= 55) return "text-red-400"; // Grave
    if (speed >= 50) return "text-orange-400"; // Lieve
    return "text-[#34D399]"; // Sicura (Verde)
};

/**
 * Tabella riassuntiva di tutti i rilevamenti e le infrazioni.
 * Gli ultimi veicoli tracciati appaiono sempre in cima alla lista (reverse).
 */
export default function AppraisalsTable({ appraisals = [] }) {
    return (
        <section className="flex flex-1 min-h-[312px] min-w-[1392px] shrink-0 overflow-hidden pt-2 pb-6 mx-6">
            <div className="flex h-full w-full flex-col overflow-hidden rounded-md border border-[#262633] bg-[#18181F] shadow-lg">
                {/* Header Tabella */}
                <div className="flex items-center justify-between border-b border-[#262633] bg-[#1E1E26] px-5 py-3 shrink-0">
                    <div className="flex items-center gap-2">
                        <Activity size={16} className="text-[#60A5FA]" />
                        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-[#F3F4F6]">Rilevamenti</h2>
                    </div>
                    <span className="font-mono-data text-[11px] font-semibold text-[#9CA3AF] bg-[#262633] px-3 py-1rounded-full">
                        {appraisals.length} Valutazioni
                    </span>
                </div>

                {/* Corpo Tabella Scrollabile */}
                <div className="flex-1 overflow-y-auto bg-[#0D0D12]/30">
                    <table className="w-full border-collapse text-left">
                        <thead className="sticky top-0 z-10 bg-[#1E1E26]">
                            <tr>
                                {COLS.map((col) => (
                                    <th key={col} className="px-5 py-3 text-[10px] font-semibold uppercase tracking-wider text-[#6B7280]">
                                        {col}
                                    </th>
                                ))}
                            </tr>
                        </thead>

                        <tbody>
                            {appraisals.length === 0 ? (
                                <tr>
                                    <td colSpan={COLS.length} className="px-5 py-12 text-center text-sm font-medium text-[#6B7280]">
                                        Ancora nessun rilevamento — monitoraggio traffico attivo...
                                    </td>
                                </tr>
                            ) : (
                                // Mappa in ordine cronologico inverso (più recenti su)
                                [...appraisals].reverse().map((r) => {
                                    const rawInf = r.infraction?.toLowerCase() || "none";

                                    // Fallback badge per infrazioni non note
                                    const badgeStyle = INFRACTION_STYLES[r.infraction] || ( rawInf === "none"
                                            ? INFRACTION_STYLES.none
                                            : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                    );

                                    return (
                                        <tr key={r.id} className="border-b border-[#262633]/50 transition-colors hover:bg-[#1E1E26]/80">
                                            <td className="px-5 py-3 font-mono-data text-xs text-[#9CA3AF]">{r.timestamp}</td>
                                            <td className="px-5 py-3 font-mono-data text-xs font-medium text-[#F3F4F6]">
                                                {r.origin?.toUpperCase() || "—"}
                                            </td>
                                            <td className="px-5 py-3 font-mono-data text-xs font-medium text-[#F3F4F6]">
                                                {r.destination?.toUpperCase() || "—"}
                                            </td>
                                            <td className="px-5 py-3 font-mono-data text-xs font-bold text-[#F3F4F6]">#{r.id}</td>
                                            <td className="px-5 py-3">
                                                <span className={`inline-block rounded border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${badgeStyle}`}>
                                                    {r.infraction || "none"}
                                                </span>
                                            </td>
                                            <td className="px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">
                                                {r.tracker}
                                            </td>
                                            <td className={`px-5 py-3 font-mono-data text-sm font-bold ${getSpeedColor(r.speed)}`}>
                                                {r.speed ? `${r.speed} km/h` : "—"}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}