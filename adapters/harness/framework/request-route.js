// Select a configured native provider through the official request waterfall.
export function requestRoute(proposal, route) {
  return route ? {...proposal, ...route} : proposal;
}
