import { call } from "@decky/api";

export interface ChargeState {
  bypass: boolean;
  protection: boolean;
  threshold: number;
  start_threshold: number;
  end_threshold: number;
  capacity: number | null;
  status: string | null;
  current_now: number | null;
  charging: boolean;
  usb_online: boolean;
  supported: boolean;
}

export const getState = () => call<[], ChargeState>("get_state");
export const setBypass = (enabled: boolean) => call<[boolean], ChargeState>("set_bypass", enabled);
export const setProtection = (enabled: boolean) => call<[boolean], ChargeState>("set_protection", enabled);
export const setThreshold = (value: number) => call<[number], ChargeState>("set_threshold", value);
