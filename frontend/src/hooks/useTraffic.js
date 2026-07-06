import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { ArrowUp, CornerUpLeft, CornerUpRight } from "lucide-react";

const BE = `http://localhost:8000`;
const API = `${BE}/api`;

// Configurazioni grafiche e costanti di mappatura dell'incrocio
const ACCENT = { N: "#60A5FA", S: "#F87171", E: "#FBBF24", W: "#34D399" };
const CARDINAL_NAME = { N: "NORTH", S: "SOUTH", E: "EAST", W: "WEST" };
const PANELS = {
    N: [["E", "left"], ["S", "straight"], ["W", "right"]],
    S: [["W", "left"], ["N", "straight"], ["E", "right"]],
    E: [["S", "left"], ["W", "straight"], ["N", "right"]],
    W: [["N", "left"], ["E", "straight"], ["S", "right"]],
};
const TURN_ICON = { left: CornerUpLeft, straight: ArrowUp, right: CornerUpRight };

/**
 * Hook custom per la gestione dello stato e del polling del traffico.
 * @param {number} pollMs - Intervallo di aggiornamento in millisecondi.
 */
export default function useTraffic(pollMs = 800) {
    const [metrics, setMetrics] = useState(null);
    const [appraisals, setAppraisals] = useState([]);
    const [connected, setConnected] = useState(false);
    const timer = useRef(null);

    // Funzione interna per mappare ed normalizzare la risposta dell'API
    const formatMetrics = useCallback((raw) => {
        const appCount = raw.appraisals ? raw.appraisals.length : 0;
        const trendVal = raw.total_crosses > 15 ? raw.total_crosses : 15;

        return {
            status: raw.status === "ANALYZING" ? "OK" : raw.status,
            fps: raw.fps,
            total: appCount,
            active_vehicles: appCount,
            tracker: raw.tracker || "tracktrack",
            active_camera: raw.active_camera || "day1",
            counts: {
                N_W: raw.count_N_W,
                N_S: raw.count_N_S,
                N_E: raw.count_N_E,
                S_E: raw.count_S_E,
                S_N: raw.count_S_N,
                S_W: raw.count_S_W,
                W_S: raw.count_W_S,
                W_E: raw.count_W_E,
                W_N: raw.count_W_N,
                E_N: raw.count_E_N,
                E_W: raw.count_E_W,
                E_S: raw.count_E_S,
            },
            trend: [0, 5, 10, trendVal],
        };
    }, []);

    // Richiesta HTTP principale per recuperare i dati correnti
    const fetchAll = useCallback(async () => {
        try {
            const response = await axios.get(`${API}/metrics`);
            const raw = response.data;

            setMetrics(formatMetrics(raw));
            setAppraisals(raw.appraisals || []);
            setConnected(true);
        } catch (error) {
            console.error("Errore di connessione API:", error);
            setConnected(false);
        }
    }, [formatMetrics]);

    // Ciclo di polling per aggiornare i dati in tempo reale
    useEffect(() => {
        fetchAll();
        timer.current = setInterval(fetchAll, pollMs);
        return () => clearInterval(timer.current);
    }, [fetchAll, pollMs]);

    // Endpoint per mutare lo stato del tracker a runtime
    const setTracker = useCallback(
        async (mode) => {
            try {
                await axios.post(`${API}/tracker/${mode}`);
                fetchAll();
            } catch (error) {
                console.error("Errore switch tracker:", error);
            }
        },
        [fetchAll]
    );

    // Endpoint per cambiare la sorgente video/condizione meteo
    const setCamera = useCallback(
        async (camId) => {
            try {
                await axios.post(`${API}/camera/${camId}`);
                fetchAll();
            } catch (error) {
                console.error("Errore switch camera:", error);
            }
        },
        [fetchAll]
    );

    return {
        metrics,
        appraisals,
        connected,
        setTracker,
        setCamera,
        videoSrc: `${BE}/video_feed`,
    };
}