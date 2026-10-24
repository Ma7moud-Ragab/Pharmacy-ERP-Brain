import { zodResolver } from '@hookform/resolvers/zod';
import { isAxiosError } from 'axios';
import { Building2, Lock, User } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { ApiClientError } from '../../../lib/api/client';
import { useAuthStore } from '../../../stores/authStore';
import { loginSchema, type LoginFormValues } from '../schemas/loginSchema';
import type { LoginRequest } from '../../../types/generated';

interface LoginFormProps {
  onSuccess: () => void;
}

const LOGIN_FIELDS: Record<keyof LoginFormValues, true> = {
  organization_code: true,
  username: true,
  password: true,
};

const isLoginField = (
  field: string | undefined
): field is keyof LoginFormValues =>
  typeof field === 'string' && Object.hasOwn(LOGIN_FIELDS, field);

export function LoginForm({ onSuccess }: LoginFormProps) {
  const login = useAuthStore((state) => state.login);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    mode: 'onTouched',
    defaultValues: {
      organization_code: '',
      username: '',
      password: '',
    },
  });

  const onSubmit = async (values: LoginFormValues) => {
    try {
      await login(values as LoginRequest);
      toast.success('Signed in successfully');
      onSuccess();
    } catch (error) {
      if (error instanceof ApiClientError) {
        let hasFieldError = false;

        for (const detail of error.details ?? []) {
          if (isLoginField(detail.field)) {
            setError(detail.field, {
              type: 'server',
              message: detail.issue,
            });
            hasFieldError = true;
          }
        }

        if (hasFieldError) return;

        if (error.status === 401) {
          toast.error('Invalid organization code or credentials.');
          return;
        }

        toast.error(
          error.trace_id
            ? `${error.message} (Ref: ${error.trace_id})`
            : error.message
        );
        return;
      }

      if (isAxiosError(error)) {
        toast.error(
          error.code === 'ECONNABORTED'
            ? 'The request timed out. Please try again.'
            : 'Cannot reach the server. Check your connection and try again.'
        );
        return;
      }

      toast.error('Unable to sign in. Please try again.');
    }
  };

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={handleSubmit(onSubmit)}
      noValidate
    >
      <Input
        label="Organization code"
        placeholder="PHARMAPLUS"
        autoComplete="organization"
        autoFocus
        leadingIcon={<Building2 className="h-4 w-4" aria-hidden="true" />}
        error={errors.organization_code?.message}
        {...register('organization_code')}
      />
      <Input
        label="Username"
        placeholder="fa.pharmacist"
        autoComplete="username"
        leadingIcon={<User className="h-4 w-4" aria-hidden="true" />}
        error={errors.username?.message}
        {...register('username')}
      />
      <Input
        label="Password"
        type="password"
        placeholder="Enter your password"
        autoComplete="current-password"
        leadingIcon={<Lock className="h-4 w-4" aria-hidden="true" />}
        error={errors.password?.message}
        {...register('password')}
      />
      <Button type="submit" fullWidth isLoading={isSubmitting}>
        {isSubmitting ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
}
