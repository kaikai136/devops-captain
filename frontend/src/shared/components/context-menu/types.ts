import type { IconName } from '../AppIcon.vue';

export interface ContextMenuEntry {
  id: string;
  label: string;
  icon: IconName;
  enabled: boolean;
  danger?: boolean;
  selected?: boolean;
  swatchColor?: string;
  separatorBefore?: boolean;
  shortcut?: string;
  children?: ContextMenuEntry[];
  action: () => void | Promise<void>;
}
