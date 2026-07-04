import { Activity } from "lucide-react";

const TYPE_STYLE = {
    "Red Light Running": "bg-red-500/10 text-red-400 border-red-500/20",
    "Speeding": "bg-amber-500/10 text-amber-400 border-amber-500/20",
    "Wrong Way": "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20",
    "Illegal Turn": "bg-sky-500/10 text-sky-400 border-sky-500/20",
    "Stop Line Violation": "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

export default function AppraisalsTable({ appraisals }) {
    const COLS = ["Timestamp", "Origin", "Destination", "Vehicle ID", "Infraction", "Tracker", "Peak Speed"];
    return (
        <section className="flex flex-1 min-h-[312px] min-w-[1392px] shrink-0 overflow-hidden pt-2 pb-6 mx-6">
            <div className="flex h-full w-full flex-col overflow-hidden rounded-md border border-[#262633] bg-[#18181F] shadow-lg">
                <div className="flex items-center justify-between border-b border-[#262633] bg-[#1E1E26] px-5 py-3 shrink-0">
                    <div className="flex items-center gap-2">
                        <Activity size={16} className="text-[#60A5FA]" />
                        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-[#F3F4F6]">Rilevamenti</h2>
                    </div>
                    <span className="font-mono-data text-[11px] font-semibold text-[#9CA3AF] bg-[#262633] px-3 py-1 rounded-full">
                        {appraisals.length} Valutazioni
                    </span>
                </div>
                
                <div className="flex-1 overflow-y-auto bg-[#0D0D12]/30">
                    <table className="w-full border-collapse text-left">
                        <thead className="sticky top-0 z-10 bg-[#1E1E26]">
                            <tr>
                                {COLS.map(c => <th key={c} className="px-5 py-3 text-[10px] font-semibold uppercase tracking-wider text-[#6B7280]">{c}</th>)}
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
                                [...appraisals].reverse().map((r) => (
                                    <tr
                                        key={r.id} 
                                        className="border-b border-[#262633]/50 transition-colors hover:bg-[#1E1E26]/80"
                                    >
                                        <td className="px-5 py-3 font-mono-data text-xs text-[#9CA3AF]">{r.timestamp}</td>
                                        <td className="px-5 py-3 font-mono-data text-xs font-medium text-[#F3F4F6]">{r.origin?.toUpperCase() || "—"}</td>
                                        <td className="px-5 py-3 font-mono-data text-xs font-medium text-[#F3F4F6]">{r.destination?.toUpperCase() || "—"}</td>
                                        <td className="px-5 py-3 font-mono-data text-xs font-bold text-[#F3F4F6]">#{r.id}</td>
                                        <td className="px-5 py-3">
                                            <span className={`inline-block rounded border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${TYPE_STYLE[r.infraction] || "bg-amber-500/10 text-amber-400 border-amber-500/20"}`}>
                                                {r.infraction}
                                            </span>
                                        </td>
                                        <td className="px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">{r.tracker}</td>
                                        <td className={`px-5 py-3 font-mono-data text-sm font-bold ${r.speed >= 55 ? "text-red-400" : r.speed >= 50 ? "text-orange-400" : "text-[#34D399]"}`}>
                                            {r.speed ? `${r.speed} km/h` : "—"}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}
