import { ShieldCheck } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LoginForm } from '../components/LoginForm';
import { resolveRedirectPath } from '../../../routes/paths';

export function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleSuccess = () => {
    navigate(resolveRedirectPath(location.state), { replace: true });
  };

  return (
    <main className="bg-background flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="border-border bg-surface rounded-lg border p-6 shadow-md sm:p-8">
          <div className="mb-6 flex flex-col items-center gap-3 text-center">
            <span className="bg-primary-soft text-primary flex h-11 w-11 items-center justify-center rounded-md">
              <ShieldCheck className="h-6 w-6" aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-display text-text">Sign in</h1>
              <p className="text-body text-text-secondary mt-1">
                Access your pharmacy workspace.
              </p>
            </div>
          </div>
          <LoginForm onSuccess={handleSuccess} />
        </div>
        <p className="text-caption text-text-muted mt-4 text-center">
          ForgeERP · Secure session access
        </p>
      </div>
    </main>
  );
}

export default LoginPage;
