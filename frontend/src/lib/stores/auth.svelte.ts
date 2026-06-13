// Current-user store. The session lives in an httpOnly cookie; this just mirrors
// who is signed in so the layout can guard routes and show the account.

import { api, type CurrentUser } from '$lib/api';

export const auth = $state<{ user: CurrentUser | null; ready: boolean }>({
  user: null,
  ready: false
});

export async function loadUser(): Promise<CurrentUser | null> {
  auth.user = await api.me();
  auth.ready = true;
  return auth.user;
}

export async function signOut(): Promise<void> {
  await api.logout();
  auth.user = null;
}
