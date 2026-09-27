import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { registerSW } from 'virtual:pwa-register';
import { connectAuth } from '@/api/client';
import { App } from '@/app/App';
import { checkForUpdatesWhenVisible, pwaUpdate } from '@/app/pwaUpdate';
import { createAuthSession } from '@/features/auth/session';
import '@/i18n';
import '@/styles/index.css';

// A new service worker waits until the user chooses to reload (UpdatePrompt).
const updateServiceWorker = registerSW({
  onNeedRefresh: () => pwaUpdate.announce(() => updateServiceWorker(true)),
  onRegisteredSW: (_url, registration) => {
    if (registration) checkForUpdatesWhenVisible(registration);
  },
});

// One session for the app's lifetime, connected to the API client before anything renders.
const authSession = createAuthSession();
connectAuth(authSession);

const root = document.getElementById('root');
if (!root) throw new Error('The #root element is missing from index.html');

createRoot(root).render(
  <StrictMode>
    <App authSession={authSession} />
  </StrictMode>,
);
