import { ArrowUp, CornerUpLeft, CornerUpRight } from "lucide-react";

// Colori utilizzati per le direzioni.
export const ACCENT = {
    N: "#60A5FA", // Blu per il Nord
    S: "#F87171", // Rosso per il Sud
    E: "#FBBF24", // Giallo per l'Est
    W: "#34D399", // Verde per l'Ovest
};

// Mappatura delle abbreviazioni cardinali nei loro nomi completi.
export const CARDINAL_NAME = {
    N: "NORTH",
    S: "SOUTH",
    E: "EAST",
    W: "WEST",
};

// Configurazione logica delle manovre dell'incrocio.
export const PANELS = {
    N: [
        ["E", "left"],
        ["S", "straight"],
        ["W", "right"],
    ],
    S: [
        ["W", "left"],
        ["N", "straight"],
        ["E", "right"],
    ],
    E: [
        ["S", "left"],
        ["W", "straight"],
        ["N", "right"],
    ],
    W: [
        ["N", "left"],
        ["E", "straight"],
        ["S", "right"],
    ],
};

// Mappatura tra il tipo di manovra e l'icona associata. Permette di renderizzare dinamicamente l'icona corretta nei contatori.
export const TURN_ICON = {
    left: CornerUpLeft,
    straight: ArrowUp,
    right: CornerUpRight,
};