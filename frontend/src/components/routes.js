import { CornerUpLeft, ArrowUp, CornerUpRight } from "lucide-react";

export const ACCENT = {
    N: "#60A5FA",
    S: "#F87171",
    E: "#FBBF24",
    W: "#34D399",
};

export const CARDINAL_NAME = { N: "NORTH", S: "SOUTH", E: "EAST", W: "WEST" };

// origin -> ordered [left, straight, right] maneuvers with destination
export const PANELS = {
    N: [["E", "left"], ["S", "straight"], ["W", "right"]],
    S: [["W", "left"], ["N", "straight"], ["E", "right"]],
    E: [["S", "left"], ["W", "straight"], ["N", "right"]],
    W: [["N", "left"], ["E", "straight"], ["S", "right"]],
};

export const TURN_ICON = {
    left: CornerUpLeft,
    straight: ArrowUp,
    right: CornerUpRight,
};
