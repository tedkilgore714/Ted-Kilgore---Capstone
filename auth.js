// Shared customer-facing Supabase Auth client -- loaded by account.html,
// companies.html, and openings.html so a signed-in session is visible
// across all three.
//
// Default storageKey (sb-<project>-auth-token) is intentional -- admin.html
// already moved OFF that default key into 'aijobscout-admin-auth' so this
// slot would be free for the customer session, per the admin/anon-session-
// leak bug found and fixed earlier: logging into admin used to silently
// authenticate every other page as the admin user via shared localStorage,
// breaking anon-only actions like the public Contact form insert. Do not
// add a storageKey override here.
const authClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// Shared helper: redirect to account.html (preserving where to come back
// to) if there's no signed-in session. Call this at the top of any page
// that requires a signed-in customer. Returns the session if present.
async function requireSession() {
  const { data: { session } } = await authClient.auth.getSession();
  if (!session) {
    const here = window.location.pathname.replace(/^\//, '');
    window.location.href = `account.html?return=${encodeURIComponent(here)}`;
    return null;
  }
  return session;
}
