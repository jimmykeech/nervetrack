// Current-user store. The session lives in an httpOnly cookie; this just mirrors
// who is signed in so the layout can guard routes and show the account.

import { api, type CurrentUser } from '$lib/api';

export const auth = $state<{ user: CurrentUser | null; ready: boolean; error: boolean }>({
  user: null,
  ready: false,
  error: false
});

export async function loadUser(): Promise<CurrentUser | null> {
  try {
    // api.me() resolves to null on a clean 401 (simply not signed in) and
    // throws on anything else (e.g. the backend is unreachable).
    auth.user = await api.me();
    auth.error = false;
  } catch {
    // Never leave the app hanging on a blank shell: record the failure so the
    // layout can show an error instead of an empty page or a misleading bounce
    // to /login (the login button hits the same dead backend).
    auth.user = null;
    auth.error = true;
  } finally {
    auth.ready = true;
  }
  return auth.user;
}

export async function signOut(): Promise<void> {
  await api.logout();
  auth.user = null;
}
