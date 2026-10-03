import timeline from './data/september-timeline.json';
export const trajectoryResponse = (path) => {
  const payload = path === '/api/trajectory' ? { dates: timeline.days.map((day) => day.date) }
    : { places: timeline.places, days: timeline.days.filter((day) => day.date === path.split('/').at(-1)) };
  return Promise.resolve({ ok: true, status: 200, json: async () => payload });
};
