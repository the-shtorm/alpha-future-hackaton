export type Page = 'catalog' | 'form' | 'results' | 'saved' | 'applications';
export type View = {
  page: Page;
  profileId: string | null;
  runId: string | null;
  applicationId: string | null;
};
const pages: Page[] = ['catalog', 'form', 'results', 'saved', 'applications'];
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function readView(search: string): View {
  const params = new URLSearchParams(search);
  const id = (key: string) => (uuid.test(params.get(key) ?? '') ? params.get(key) : null);
  const page = params.get('page') as Page;
  return {
    page: pages.includes(page) ? page : 'catalog',
    profileId: id('profile'),
    runId: id('run'),
    applicationId: id('application'),
  };
}
export function viewSearch(view: View): string {
  const params = new URLSearchParams();
  if (view.page !== 'catalog') params.set('page', view.page);
  if (['form', 'results'].includes(view.page) && view.profileId)
    params.set('profile', view.profileId);
  if (view.page === 'results' && view.runId) params.set('run', view.runId);
  if (view.page === 'applications' && view.applicationId)
    params.set('application', view.applicationId);
  return params.size ? `?${params}` : '';
}
