import { z } from 'zod';

export const loginSchema = z.object({
  organization_code: z
    .string()
    .trim()
    .min(1, 'Organization code is required')
    .max(30, 'Organization code must be 30 characters or fewer'),
  username: z
    .string()
    .trim()
    .min(1, 'Username is required')
    .max(80, 'Username must be 80 characters or fewer'),
  password: z
    .string()
    .min(1, 'Password is required')
    .max(128, 'Password must be 128 characters or fewer'),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
