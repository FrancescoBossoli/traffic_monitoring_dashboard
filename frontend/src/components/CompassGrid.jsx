import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { ACCENT, CARDINAL_NAME, PANELS, TURN_ICON } from "./routes";

function CounterRow({ origin, dest, turn, value }) {
    const Icon = TURN_ICON[turn];
    const accent = ACCENT[origin];
    return (
        <div className="flex items-center justify-between rounded-sm border border-[#262633] bg-[#0D0D12] px-2 py-1.5 transition-colors hover:border-[#34343f]">
            <div className="flex items-center gap-1.5">
                <Icon size={13} style={{ color: accent }} />
                <span className="font-mono-data text-[11px] tracking-wide text-[#9CA3AF]">{origin}→{dest}</span>
            </div>
            <span className="font-mono-data text-sm font-medium text-[#F3F4F6] tabular-nums">{value ?? 0}</span>
        </div>
    );
}

function DirectionPanel({ origin, counts }) {
    const accent = ACCENT[origin];
    return (
        <div className="flex flex-col gap-1.5 rounded-md border border-[#262633] bg-[#18181F] p-2.5 shadow-sm">
            <div className="mb-0.5 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: accent }} />
                <span className="font-display text-[11px] font-bold tracking-[0.15em]" style={{ color: accent }}>{CARDINAL_NAME[origin]}</span>
                <span className="ml-auto text-[9px] uppercase tracking-wider text-[#6B7280]">origin</span>
            </div>
            {PANELS[origin].map(([dest, turn]) => (
                <CounterRow key={dest} origin={origin} dest={dest} turn={turn} value={counts?.[`${origin}_${dest}`]} />
            ))}
        </div>
    );
}

function Chip({ label, value, accent }) {
    return (
        <div className="flex flex-col items-center justify-center rounded-md border border-[#262633] bg-[#18181F] p-2 text-center shadow-sm">
            <span className="text-[9px] uppercase tracking-widest text-[#6B7280]">{label}</span>
            <span className="font-mono-data text-base font-medium" style={{ color: accent || "#F3F4F6" }}>{value}</span>
        </div>
    );
}

function CenterKPI({ total, trend }) {
    const data = (trend || []).map((v, i) => ({ i, v }));
    return (
        <div className="relative flex flex-col items-center justify-center overflow-hidden rounded-md border border-[#262633] bg-[#1E1E26] p-2 shadow-sm">
            <div className="absolute inset-0 opacity-50">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data} margin={{ top: 14, bottom: 0, left: 0, right: 0 }}>
                        <defs>
                            <linearGradient id="kpiArea" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#60A5FA" stopOpacity={0.5} />
                                <stop offset="100%" stopColor="#60A5FA" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <Area type="monotone" dataKey="v" stroke="#60A5FA" strokeWidth={1.5} fill="url(#kpiArea)" isAnimationActive={false} />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
            <span className="relative z-10 text-[9px] uppercase tracking-[0.2em] text-[#9CA3AF]">ATTRAVERSAMENTI</span>
            <span className="relative z-10 font-mono-data text-3xl font-light tracking-tighter text-[#F3F4F6] tabular-nums">{total ?? 0}</span>
            <span className="relative z-10 text-[9px] uppercase tracking-widest text-[#6B7280]">vehicles</span>
        </div>
    );
}

export default function CompassGrid({ metrics }) {
    const counts = metrics?.counts;
    return (
        <section className="h-[500px] w-full shrink-0 lg:w-[420px] xl:w-[480px]">
            <div className="grid h-full grid-cols-3 grid-rows-3 gap-2">
                <Chip label="Status" value={metrics?.status ?? "—"} accent={metrics?.status === "OK" ? "#10B981" : "#EF4444"} />
                <DirectionPanel origin="N" counts={counts} />
                <Chip label="FPS" value={metrics?.fps ?? "—"} accent="#34D399" />
                <DirectionPanel origin="W" counts={counts} />
                <CenterKPI total={metrics?.total} trend={metrics?.trend} />
                <DirectionPanel origin="E" counts={counts} />
                <Chip label="Active" value={metrics?.active_vehicles ?? 0} />
                <DirectionPanel origin="S" counts={counts} />
                <Chip label="Tracker" value={metrics?.tracker === "custom" ? "CuStOm" : "TrAcK"} accent="#FBBF24" />
            </div>
        </section>
    );
}
