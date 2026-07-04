import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { ArrowUp, CornerUpLeft, CornerUpRight } from "lucide-react";

const BE = `http://localhost:8000`;
const API = `${BE}/api`;

const ACCENT = { N: "#60A5FA", S: "#F87171", E: "#FBBF24", W: "#34D399" };
const CARDINAL_NAME = { N: "NORTH", S: "SOUTH", E: "EAST", W: "WEST" };
const PANELS = {
    N: [["E", "left"], ["S", "straight"], ["W", "right"]],
    S: [["W", "left"], ["N", "straight"], ["E", "right"]],
    E: [["S", "left"], ["W", "straight"], ["N", "right"]],
    W: [["N", "left"], ["E", "straight"], ["S", "right"]],
};
const TURN_ICON = { left: CornerUpLeft, straight: ArrowUp, right: CornerUpRight };

export default function useTraffic(pollMs = 800) {
    const [metrics, setMetrics] = useState(null);
    const [appraisals, setAppraisals] = useState([]);
    const [connected, setConnected] = useState(false);
    const timer = useRef(null);

    const fetchAll = useCallback(async () => {
        try {
            const m = await axios.get(`${API}/metrics`);
            const raw = m.data;

            setMetrics({
                status: raw.status === "ANALYZING" ? "OK" : raw.status,
                fps: raw.fps,
                total: raw.appraisals ? raw.appraisals.length : 0,
                active_vehicles: raw.appraisals ? raw.appraisals.length : 0, 
                tracker: raw.tracker || "tracktrack",
                active_camera: raw.active_camera || "day1",
                counts: {
                    N_W: raw.count_N_W, N_S: raw.count_N_S, N_E: raw.count_N_E,
                    S_E: raw.count_S_E, S_N: raw.count_S_N, S_W: raw.count_S_W,
                    W_S: raw.count_W_S, W_E: raw.count_W_E, W_N: raw.count_W_N,
                    E_N: raw.count_E_N, E_W: raw.count_E_W, E_S: raw.count_E_S,
                },
                trend: [0, 5, 10, raw.total_crosses > 15 ? raw.total_crosses : 15] 
            });
            
            setAppraisals(raw.appraisals || []);
            setConnected(true);

        } catch (e) {
            console.error("Errore di connessione API:", e);
            setConnected(false);
        }
    }, []);

    useEffect(() => {
        fetchAll();
        timer.current = setInterval(fetchAll, pollMs);
        return () => clearInterval(timer.current);
    }, [fetchAll, pollMs]);

    const setTracker = useCallback(async (mode) => {
        try { await axios.post(`${API}/tracker/${mode}`); fetchAll(); } catch (e) {}
    }, [fetchAll]);

    const setCamera = useCallback(async (camId) => {
        try { await axios.post(`${API}/camera/${camId}`); fetchAll(); } catch (e) {}
    }, [fetchAll]);

    return { metrics, appraisals, connected, setTracker, setCamera, videoSrc: `${BE}/video_feed` };
}