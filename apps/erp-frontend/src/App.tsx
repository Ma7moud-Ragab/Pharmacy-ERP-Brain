import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { ToastHost } from './components/ui/ToastHost';
import { router } from './routes';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return (
    <>
      <RouterProvider router={router} />
      <ToastHost />
    </>
  );
}
