import {
  ActionProvider,
  Renderer,
  StateProvider,
  VisibilityProvider,
} from "@json-render/react";

import { courtRegistry } from "../court/catalog";
import type { CourtSpec } from "../court/spec";

export function CourtRenderer({ spec }: { spec: CourtSpec }) {
  return (
    <StateProvider initialState={{}}>
      <ActionProvider handlers={{}}>
        <VisibilityProvider>
          <Renderer spec={spec} registry={courtRegistry} />
        </VisibilityProvider>
      </ActionProvider>
    </StateProvider>
  );
}
