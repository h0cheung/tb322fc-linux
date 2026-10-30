// SPDX-License-Identifier: BSD-3-Clause
const WRAPPER = '/usr/bin/kettle-fg';
export function framegenOptions(options: string, enabled: boolean): string {
  // Only our exact trailing wrapper; retain the rest byte for byte, including quoted paths.
  if (!enabled && !/(?:^|\s)\/usr\/bin\/kettle-fg\s*%command%/.test(options)) return options;
  const at = options.indexOf('%command%');
  const prefix = at < 0 ? '' : options.slice(0, at);
  const rest = at < 0 ? (options ? ' ' + options : '') : options.slice(at + 9);
  const clean = prefix.replace(/(?:^|\s)\/usr\/bin\/kettle-fg\s*$/, '').trimEnd();
  if (enabled) return (clean ? clean + ' ' : '') + WRAPPER + ' %command%' + rest;
  return clean || rest.trim() ? (clean ? clean + ' ' : '') + '%command%' + rest : '';
}
