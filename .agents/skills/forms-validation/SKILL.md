---
name: forms-validation
description: Use when building or changing forms, input validation, form submission, field-level error mapping from backend contracts, or dynamic line items with React Hook Form and Zod.
---

# Forms and Validation

This rule is STRICT. It applies to every form, input field, and validation schema across the app.
Stack: `react-hook-form` + `@hookform/resolvers/zod` + `zod`. See skill `tech-stack`.

## The 5 laws

1. **ALL forms use React Hook Form.** Never manage form state manually with multiple `useState` calls.
2. **ALL validation schemas use Zod.** Never write manual if/else validation logic inside submit handlers.
3. **Schemas define validation; contracts define API payloads.** Form values are inferred with `z.infer<typeof schema>`, but what is sent to the backend strictly matches the generated contract types (skill `contracts-types`).
4. **Backend errors MUST map to form fields.** When the API returns field-level validation errors (`error.details`), set them directly on the matching form fields using `setError`.
5. **Multi-row / line items use `useFieldArray`.** Tabular forms (POS items, purchase order line items) must use `useFieldArray` with unique keys.

## 1. Standard Form Setup

- Define the Zod schema outside the component, co-located or in a schemas file (per `STRUCTURE.md`).
- Infer the form values type using `z.infer`:
  ```ts
  export const supplierFormSchema = z.object({
    name: z.string().min(1, 'Supplier name is required'),
    email: z.string().email('Invalid email address'),
    phone: z.string().min(5, 'Phone number must be at least 5 digits'),
  });

  export type SupplierFormValues = z.infer<typeof supplierFormSchema>;
  ```
- Initialize the form with `useForm` using the Zod resolver and explicit default values:
  ```ts
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<SupplierFormValues>({
    resolver: zodResolver(supplierFormSchema),
    defaultValues: {
      name: '',
      email: '',
      phone: '',
    },
    mode: 'onTouched',
  });
  ```

## 2. Server Error Mapping (Mandatory)

The backend error response conforms to the standard shape: `{ code, message, details, trace_id }`.
In mutation `onError` callbacks (skill `api-server-state`):
- `error.details` is an ARRAY of `{ field?, issue }` objects (the contract's `ErrorDetail`), not a dictionary. Map every entry that has a `field` using `setError`:
  ```ts
  onError: (error) => {
    error.details?.forEach(({ field, issue }) => {
      if (field) {
        setError(field as keyof SupplierFormValues, {
          type: 'server',
          message: issue,
        });
      }
    });
  }
  ```
- Always display a top-level alert or toast for the generic `error.message` if field errors do not cover the failure.

## 3. Multi-Row Tabular Forms (`useFieldArray`)

Used for line items in Sales/POS and Purchase Orders (e.g., product lines, quantities, unit prices):
- Use `useFieldArray({ control, name: 'items' })`.
- ALWAYS use `field.id` as the React `key` prop on row containers (never use array index).
- Form calculations (e.g., row totals, subtotal) should be derived using `useWatch` or store selectors, not by manually modifying form inputs:
  ```ts
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'items',
  });
  ```
- Provide accessible buttons for `append` (Add Item) and `remove(index)` (Delete Item).
- Disable row removal if at least one row is required by business rules, unless the form provides an empty state.

## 4. Submission & State Discipline

- Disable the submit button when `isSubmitting` or when the mutation `isPending`.
- Never submit if the form is pristine (`!isDirty`) when editing existing entities, unless explicitly intended.
- Reset the form on successful mutation:
  ```ts
  onSuccess: () => {
    reset();
  }
  ```
- If a form lives in a modal or drawer, reset form errors and values when the modal closes.

## Forbidden (never do these)

- Managing form state with `useState` or putting form inputs in Zustand.
- Writing custom regex or manual validation loops instead of Zod rules.
- Swallowing backend `details` errors and showing only a generic "Submission failed" toast.
- Using array indexes as keys in dynamic field lists instead of `field.id`.
- Re-declaring contract types as duplicate Zod schemas instead of deriving from or mapping to generated types.
- Allowing double submissions by leaving submit buttons enabled during asynchronous requests.

## Before you finish

End your reply with a short "Forms check" section:
- Which schemas and forms were created or modified
- How server validation errors (`error.details`) are mapped to inputs
- Whether `useFieldArray` was used for multi-row data with `field.id` keys
- Confirm that submit buttons are guarded against double submission
