import {
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { getState, setBypass, setProtection, setThreshold } from "./backend";
import type { ChargeState } from "./backend";

const THRESHOLD_MIN = 55;
const THRESHOLD_MAX = 100;
const POLL_MS = 3000;
const SAVE_DEBOUNCE_MS = 400;

export function Content() {
  const [state, setState] = useState<ChargeState | null>(null);
  const [error, setError] = useState("");
  // True while a slider edit is in flight so the poll loop cannot overwrite it.
  const editing = useRef(false);
  const saveTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await getState());
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      if (!editing.current) void refresh();
    }, POLL_MS);
    return () => {
      window.clearInterval(id);
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    };
  }, [refresh]);

  const run = useCallback(async (promise: Promise<ChargeState>) => {
    try {
      setState(await promise);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const onThresholdChange = useCallback(
    (value: number) => {
      editing.current = true;
      setState((current) => (current ? { ...current, threshold: value } : current));
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        saveTimer.current = null;
        void run(setThreshold(value)).finally(() => {
          editing.current = false;
        });
      }, SAVE_DEBOUNCE_MS);
    },
    [run],
  );

  const status = state
    ? `${state.capacity ?? "?"}%${state.status ? ` · ${state.status}` : ""}${
        state.charging ? " · charging" : ""
      }`
    : "Loading…";

  return (
    <PanelSection title="Y700 Charge">
      <PanelSectionRow>
        <Field label="Battery" description={status} />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label="Bypass charging"
          description="Run off the adapter and leave the pack idle (best for plugged-in gaming)"
          checked={state?.bypass ?? false}
          disabled={!state}
          onChange={(value) => void run(setBypass(value))}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ToggleField
          label="Charge protection"
          description="Stop charging at the limit below to slow battery ageing"
          checked={state?.protection ?? false}
          disabled={!state}
          onChange={(value) => void run(setProtection(value))}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <SliderField
          label="Charge limit"
          value={state?.threshold ?? 80}
          min={THRESHOLD_MIN}
          max={THRESHOLD_MAX}
          step={5}
          showValue
          disabled={!state || !state.protection}
          onChange={onThresholdChange}
        />
      </PanelSectionRow>

      {state?.protection ? (
        <PanelSectionRow>
          <div className={staticClasses.Label}>
            Charging resumes below {state.start_threshold}%
          </div>
        </PanelSectionRow>
      ) : null}

      {state && !state.supported ? (
        <PanelSectionRow>
          <Field label="Warning" description="qcom-battmgr battery not found" />
        </PanelSectionRow>
      ) : null}

      {error ? (
        <PanelSectionRow>
          <Field label="Error" description={error} />
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}
