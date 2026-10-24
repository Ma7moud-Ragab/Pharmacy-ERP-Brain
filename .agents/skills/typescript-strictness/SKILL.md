---
name: typescript-strictness
description: Use whenever writing or changing TypeScript or TSX: types, props, casts, null handling, suppression comments, and running the typecheck.
---

# TypeScript Strictness

This rule is STRICT. It applies to every `.ts` and `.tsx` file you write or change.
The goal: the compiler catches mistakes before the app runs. You never silence it, you fix the cause.

## The 6 laws

1. **NEVER use `any`.** Not in parameters, returns, variables, generics, or catch clauses.
2. **NEVER use `@ts-ignore`.** And never `eslint-disable` comments to hide a real problem.
3. **NEVER force a type** with unsafe casts (`as SomeType`, `as unknown as X`) or the non-null assertion `!`. Narrow the type instead.
4. **NEVER loosen the TypeScript configuration** (strict flags, `tsconfig`). That is a stack change (skill `tech-stack`) and needs the developer's approval.
5. **ALWAYS type component props and exported functions explicitly.**
6. **The typecheck must pass before you finish.** Never leave a type error that you introduced.

## Instead of `any`

| Situation | Do this |
| --- | --- |
| A value of unknown shape (caught error, parsed input) | Use `unknown`, then narrow it with a check before using it |
| A shape that comes from the API | Use the generated type (skill `contracts-types`) |
| A shape you control | Write a precise `type` or `interface` |
| A function that accepts several kinds of values | Use a union type or a generic with a constraint |
| A callback or event handler | Use the real type, for example `React.ChangeEvent<HTMLInputElement>` |
| A third-party value with missing types | STOP and ask the developer. Do not cast it to `any`. |

## Narrowing and null safety

- Handle `null` and `undefined` explicitly with checks, early returns, or defaults. Do not hide them with `!`.
- Optional chaining (`?.`) is for values that are genuinely optional. Do not use it to avoid understanding why something can be missing.
- Array and object index access may return `undefined`. Handle that case.
- Use type guards or discriminated unions to narrow, not casts.
- In a `catch` block, treat the error as `unknown` and narrow it before reading `message` or other fields.

## Allowed casts (the only ones)

- `as const` for literal values.
- A cast that comes right after a real check that TypeScript cannot follow, with a one-line comment explaining why it is safe. Tell the developer about it in your final check.
- Nothing else. If you feel you need another cast, the type design is wrong: fix the type.

## Good typing habits

- **Props:** every component has an explicit props type. No inferred-from-usage props.
- **Exported functions and hooks:** explicit parameter types. Add an explicit return type when it is not obvious from the code, and always for API functions.
- **Type-only imports:** use `import type` for imports used only as types.
- **Unions over enums:** use string literal unions or `as const` objects. For values that exist in the contracts, use the contract's types (skill `contracts-types`).
- **Exhaustive checks:** when you branch on a union (status, role, type), handle every case. In a `switch`, add a `default` that assigns the value to `never` so a new case becomes a compile error.
- **Readability:** keep types simple and readable. No deep conditional or mapped type tricks when a plain type works.
- **No loose built-in types:** do not use `Function`, `Object`, or `{}` as types.
- **Immutable by default:** prefer `readonly` for data that should not change.

## Suppression comments (rare)

- `@ts-ignore` is never allowed.
- `@ts-expect-error` is allowed only when there is no other way, with a comment that says exactly why, and only after telling the developer.
- Never silence a contract mismatch with either one (skill `contracts-types`).

## Checking your work

- After you change TypeScript code, run the typecheck: `npx tsc -b` (the `build` script runs `tsc -b && vite build`). If a dedicated `typecheck` script exists in `package.json`, use that instead. Do not create or change scripts yourself; if there is none, suggest adding one to the developer.
- Fix every error that your change caused.
- If the typecheck already had errors in files you did not touch, do NOT fix them silently. Report them to the developer.
- If you cannot run the typecheck, say so clearly. Do not claim that the code type-checks.

## Forbidden (never do these)

- `any`, explicit or implicit.
- `@ts-ignore`, or `@ts-expect-error` without telling the developer.
- `as unknown as X`, or any cast used to make an error disappear.
- The non-null assertion `!`.
- Weakening `tsconfig` or lint settings to make code compile.
- Empty `catch` blocks, or catching an error and treating it as `any`.
- Optional props added only because a value is sometimes undefined in your code. Fix the cause.
- Hand-writing a type that already exists in the contracts (skill `contracts-types`).
- Claiming the code is type-safe without running the typecheck.

## Before you finish

End your reply with a short "TypeScript check" section:
- Whether the typecheck was run, and the result
- Any cast, suppression comment, or `unknown` narrowing you needed, with the reason
- Any pre-existing type error you noticed outside your changes
