const STAGE_COLORS = [
  { hex: '#415eee', rgb: [65, 94, 238] },
  { hex: '#b14c36', rgb: [177, 76, 54] },
  { hex: '#684ead', rgb: [104, 78, 173] },
  { hex: '#327253', rgb: [50, 114, 83] },
];

function stageColor(stageNumber) {
  return STAGE_COLORS[(stageNumber - 1) % STAGE_COLORS.length];
}

export { stageColor };
