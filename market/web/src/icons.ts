import bell from '@phosphor-icons/core/regular/bell.svg?raw';
import broadcast from '@phosphor-icons/core/regular/broadcast.svg?raw';
import chartLineUp from '@phosphor-icons/core/regular/chart-line-up.svg?raw';
import warning from '@phosphor-icons/core/regular/warning.svg?raw';
import x from '@phosphor-icons/core/regular/x.svg?raw';

const SOURCES = { bell, broadcast, chartLineUp, warning, x };

export type IconName = keyof typeof SOURCES;

const parser = new DOMParser();

// Parses bundled SVG files (never data from the network) into nodes.
export function icon(name: IconName): SVGElement {
  const svg = parser.parseFromString(SOURCES[name], 'image/svg+xml').documentElement as unknown as SVGElement;
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  return document.importNode(svg, true);
}
