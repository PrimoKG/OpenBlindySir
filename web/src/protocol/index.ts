// Stable entry point of the protocol types: re-exports the generated file and adds guards.
import type { HostMcView, HostPlayerModeView, PlayerView } from "./generated";

export * from "./generated";

export type AnyView = PlayerView | HostPlayerModeView | HostMcView;
export type HostView = HostPlayerModeView | HostMcView;

export function isPlayerView(view: AnyView): view is PlayerView {
  return view.kind === "player";
}

export function isHostView(view: AnyView): view is HostView {
  return view.kind === "host_player" || view.kind === "host_mc";
}

export function isMcView(view: AnyView): view is HostMcView {
  return view.kind === "host_mc";
}
