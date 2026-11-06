// A stable color per group or person, for banners and accents (same hash as the avatars).
import { avatarCells } from "./avatar";

/** A steady color for a name. */
export function hueColor(seed: string): string {
  return avatarCells(seed).color;
}
