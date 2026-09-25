export type CharacterKey = 'purple' | 'black' | 'orange' | 'yellow';
export interface Point { x: number; y: number }
export interface CharacterInteraction {
  pointer: Point | null;
  isTyping: boolean;
  maskedPassword: boolean;
  lookAway: boolean;
  glance: boolean;
  peek: boolean;
}

// Geometry and motion are adapted from careercompassai.vercel.app/login.
// The group is centred in a 550 × 500 stage with room for the tall character to stretch.
export const characters = [
  { key: 'purple', left: 120, width: 180, height: 400, faceX: 45, faceY: 40, eye: 18, pupil: 7, gap: 32, travel: 5 },
  { key: 'black', left: 290, width: 120, height: 310, faceX: 26, faceY: 32, eye: 16, pupil: 6, gap: 24, travel: 4 },
  { key: 'orange', left: 50, width: 240, height: 200, faceX: 82, faceY: 90, eye: 12, pupil: 12, gap: 32, travel: 5 },
  { key: 'yellow', left: 360, width: 140, height: 230, faceX: 52, faceY: 40, eye: 12, pupil: 12, gap: 24, travel: 5 },
] as const;

function clamp(value: number, limit: number) {
  return Math.max(-limit, Math.min(limit, value));
}

export function pupilOffset(pointer: Point | null, centre: Point, limit: number): Point {
  if (!pointer) return { x: 0, y: 0 };
  const x = pointer.x - centre.x;
  const y = pointer.y - centre.y;
  const distance = Math.hypot(x, y);
  const ratio = distance > limit ? limit / distance : 1;
  return { x: x * ratio, y: y * ratio };
}

export function characterPose(key: CharacterKey, state: CharacterInteraction) {
  const character = characters.find((item) => item.key === key)!;
  const leaning = state.isTyping || state.maskedPassword;
  const height = key === 'purple' && leaning ? 440 : character.height;
  const top = 460 - height;
  const dx = state.pointer ? state.pointer.x - (character.left + character.width / 2) : 0;
  const dy = state.pointer ? state.pointer.y - (top + height / 3) : 0;
  let skew = clamp(-dx / 120, 6);
  let translate = 0;
  let faceX: number = character.faceX + clamp(dx / 20, 15);
  let faceY: number = character.faceY + clamp(dy / 30, 10);
  let forcedLook: Point | null = null;

  if (state.lookAway) {
    skew = 0;
    faceX = { purple: 20, black: 10, orange: 50, yellow: 20 }[key];
    faceY = { purple: 35, black: 28, orange: 85, yellow: 35 }[key];
    forcedLook = { x: key === 'purple' && state.peek ? 4 : key === 'orange' || key === 'yellow' ? -5 : -4, y: key === 'purple' && state.peek ? 5 : -4 };
  } else if (key === 'purple') {
    if (leaning) { skew -= 12; translate = 40; }
    if (state.glance) { faceX = 55; faceY = 65; forcedLook = { x: 3, y: 4 }; }
  } else if (key === 'black') {
    if (state.glance) {
      skew = skew * 1.5 + 10;
      translate = 20;
      faceX = 32;
      faceY = 12;
      forcedLook = { x: 0, y: -4 };
    } else if (leaning) skew *= 1.5;
  }

  const pupils = [0, 1].map((index) => forcedLook ?? pupilOffset(state.pointer, {
    x: character.left + translate + faceX + character.eye / 2 + index * (character.eye + character.gap),
    y: top + faceY + character.eye / 2,
  }, character.travel));

  return { height, skew, translate, faceX, faceY, pupils,
    mouthX: state.lookAway ? 10 : 40 + clamp(dx / 20, 15),
    mouthY: state.lookAway ? 88 : 88 + clamp(dy / 30, 10) };
}
