/** Labels shared by the run screens. */

export const SLOT_LABEL: Record<string, string> = {
  taste: "Based on your past picks", neutral: "Strong fit", bold: "Bold take", wildcard: "Wildcard",
};

export const CRITERIA: Record<string, string> = {
  B1: "Visual hierarchy", B2: "Layout & spacing", B3: "Typography", B4: "Color", B5: "Responsive",
  B6: "Consistency", B7: "Fit to the brief", B8: "Interaction states", B9: "Fidelity to the sketch",
};

export const STOP_REASON: Record<string, string> = {
  pass: "Passed the quality bar",
  plateau: "Stopped improving, so we kept the best version",
  max_iters: "Reached the round limit, so we kept the best version",
  budget: "Reached the cost budget, so we kept the best version",
};
