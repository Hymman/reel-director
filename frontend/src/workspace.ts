export const WORKSPACE_STORAGE_KEY = 'guest_workspace_id';
export const WORKSPACE_TEST_OVERRIDE_KEY = 'reel_director_workspace_test_override';
export const DEMO_WORKSPACE_ID = import.meta.env.VITE_DEMO_WORKSPACE_ID || 'reel_director_demo_user';

/**
 * The hackathon build intentionally behaves as one signed-in Demo User.
 * Every ordinary browser receives the same backend workspace so Campaigns,
 * Assets and Brand Kit remain visible across Edge, Chrome and the app browser.
 *
 * Development-only browser tests can opt into isolated workspaces with the
 * explicit override key. Production never accepts that client-side override.
 */
export const getWorkspaceId = (): string => {
  const testOverride = import.meta.env.DEV
    ? localStorage.getItem(WORKSPACE_TEST_OVERRIDE_KEY)?.trim()
    : undefined;
  const workspaceId = testOverride || DEMO_WORKSPACE_ID;

  if (localStorage.getItem(WORKSPACE_STORAGE_KEY) !== workspaceId) {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId);
  }

  return workspaceId;
};
