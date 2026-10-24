# Contract Questions — Frontend → Backend

| | |
|---|---|
| **From** | erp-frontend team |
| **To** | erp-backend team |
| **Subject** | `contracts/openapi.erp.yaml` v1.0.0 — two gaps found during a full contract review (56 paths / 79 operations) |
| **Date** | 2026-10-18 |
| **Status** | Open — awaiting backend decisions |
| **Blocks** | Issue 1 blocks the FE auth/retry client behavior. Issue 2 blocks Stage-3 (Purchasing) FE screens. |

> الشرح بالعربي لتوضيح الصورة والسيناريوهات، والأسئلة بالإنجليزي مرقّمة وجاهزة للإجابة سطراً بسطر.
> أي تعديل متفق عليه يُنفَّذ في `openapi.erp.yaml` / `FRONTEND.md` ثم نعيد توليد التايبس عند الفرونت.

---

## Issue 1 — Idempotency-Key ناقص في 5 mutations

### الشرح

القاعدة العامة في العقد (سطر 14) تقول بصيغة binding:

> "All mutations require header: Idempotency-Key"

بمراجعة الملف كله: **46 mutation، منها 41 ملتزمة بالهيدر، و5 لأ**:

| # | Operation | Location | الوظيفة |
|---|---|---|---|
| 1 | `authLogin` | `POST /auth/login` (line 72) | تسجيل الدخول |
| 2 | `authRefresh` | `POST /auth/refresh` (line 102) | تدوير التوكن |
| 3 | `authLogout` | `POST /auth/logout` (line 130) | إبطال الجلسة |
| 4 | `createOrganization` | `POST /organizations` (line 193) | إنشاء مستأجر كامل (PlatformProvisioner — deployment فقط) |
| 5 | `redeemBranchEnrollment` | `POST /branch-enrollment` (line 344) | صرف توكن تسجيل الفرع (single-use) |

الخمسة كلها عندها — منطقياً — آلية حماية طبيعية بديلة: إعادة تسجيل الدخول تُنشئ جلسة جديدة، وتكرار logout آمن، والـ refresh محمي بالـ rotation، وتوكن الـ enrollment single-use، وإنشاء المنظمة عملية deployment تحدث مرة واحدة. لذلك نرجّح أن **الاستثناء مقصود لكنه غير موثّق** — والقاعدة المكتوبة تناقض الواقع.

### السيناريو الخطر: انقطاع الشبكة أثناء الـ refresh

```
1. التوكن انتهى → الفرونت يرسل POST /auth/refresh ومعه RT1
2. السيرفر: يستهلك RT1، يُصدر (AT2, RT2)، ويرسل رد 200
3. الرد يُفقد في الشبكة        ← الفرونت لم يستلم RT2 أبداً
4. الفرونت لا يملك غير RT1 → يعيد المحاولة به
5. السيرفر: "RT1 مستُهلك سابقاً" → حسب العقد يحُرق عائلة
   التوكن كاملة → المستخدم يُطرد لشاشة الدخول — دون أن يخطئ
```

هذا ليس سيناريو نظرياً عندنا: النظام POS لفروع صيدليات، والشبكات الضعيفة هي السبب الأساسي لوجود وضع BranchLocal أصلاً.

### Questions (EN)

- **Q1 — Intent & carve-out.** The convention on line 14 ("All mutations require header: Idempotency-Key") is not honored by 5 of 46 mutations: `authLogin`, `authRefresh`, `authLogout`, `createOrganization`, `redeemBranchEnrollment`. Is the exception intentional? If yes, please state an explicit carve-out in the contract so the FE knows exactly when to send the header.
- **Q2 — Refresh with a lost response (critical).** If the 200 response to `POST /auth/refresh` is lost after the server consumed RT1 and issued (AT2, RT2), the FE retries with RT1 (it never received RT2). Per the contract, that retry is a "reused token" → the whole family is revoked and the user is force-logged-out. Please define the expected behavior:
  (a) add `Idempotency-Key` support to `/auth/refresh` so the retry replays the stored token pair;
  (b) a short server-side replay window for the just-consumed refresh token, returning the same pair;
  (c) explicitly require the FE to force re-login on any lost refresh response.
- **Q3 — Header tolerance.** If the FE sends an `Idempotency-Key` on login/refresh/logout anyway (following the global convention), does the server accept, ignore, or reject it?
- **Q4 — Enrollment recovery.** `POST /branch-enrollment` redeems a single-use token (410 when already used). If its 200 response is lost, the retry returns 410 and the branch never receives its credentials/cursor. What is the documented recovery flow (re-issue a token from Cloud?) and can the FE distinguish "consumed by my own lost request" from "expired / used by someone else"?
- **Q5 — createOrganization duplication.** No 409 is defined for this operation and no duplicate protection is stated. What happens if it is executed twice (retry after a lost response)? Please document the guarantee (e.g. uniqueness on `organization_code` → 409).

### المقترح من ناحيتنا

1. توثيق carve-out صريح للخمسة في العقد (قائمة + سبب الاستثناء).
2. للـ refresh تحديداً: الحل (a) أو (b) هو الأفضل للـ UX في الفروع؛ الحل (c) مقبول لكنه يطرد الكاشير عند أي هزة شبكة.
3. إضافة جدول صغير في العقد: لكل عملية من الخمسة — "السلوك المتوقع عند إعادة المحاولة".

### التأثير على شغل الفرونت

سلوك الـ HTTP client في الـ auth/retry **معلّق** حتى يتحدد القرار، ووثائق الاتفاقيات الداخلية عندنا (تقول حالياً "كل mutation تحمل مفتاح") ستُضبط على القرار النهائي.

---

## Issue 2 — BranchLocal لا يملك قراءات الـ Purchasing

### الشرح

وضع التشغيل BranchLocal (سيرفر الفرع، offline-capable) هو المسؤول عن **استلام** المشتريات وإنشاء **مرتجعات الموردين** — لكنه في العقد لا يملك أي endpoint لقراءة نفس البيانات التي يكتب عليها:

| Endpoint | x-runtime | ملاحظة |
|---|---|---|
| `GET/POST /suppliers` + `GET/PATCH /suppliers/{id}` | Cloud | القراءة والكتابة |
| `POST /purchase-orders` (create) | Cloud | |
| `GET /purchase-orders` (list) | **Cloud** | ❌ الفرع يحتاجها في شاشة الاستلام |
| `GET /purchase-orders/{id}` (detail) | **Cloud** | ❌ الفرع يحتاجها قبل تسجيل الاستلام |
| `POST /purchase-orders/{id}/approve` / `order` | Cloud | |
| `POST /purchase-orders/{id}/receive` | **BranchLocal** | ✅ الفرع يكتب |
| `POST /purchase-orders/{id}/cancel-remaining` | **BranchLocal** | ✅ الفرع يكتب |
| `GET /vendor-returns` (list) | **Cloud** | ❌ الفرع ينشئ مرتجعات ولا يقرؤها |
| `GET /vendor-returns/{id}` (detail) | **Cloud** | ❌ |
| `POST /vendor-returns` + `/cancel` + `/post` | **BranchLocal** | ✅ الفرع يكتب |
| Supplier payments (كلها) | Cloud | مقبول (بما أن الفرع لا يشارك في الدفع) |

والعقد نفسه ينص (line 2121): أن نداء route من نوع Cloud من داخل الفرع يرد **404/405** — أي أن شاشة الاستلام في الفرع لا تستطيع حتى عرض قائمة الـ POs المتوقعة أو تفاصيلها، مع أن التسجيل نفسه مسموح.

### المثال الفعلي (يوم استلام في الفرع)

بضاعة وصلت لفرع "وسط البلد"، والصيدلية تفتح POS الفرع لتسجيل الاستلام:

1. `GET /purchase-orders?status=ORDERED` → **404/405** → لا قائمة بالـ POs المتوقعة ❌
2. `GET /purchase-orders/{id}` → **404/405** → لا بنود ولا كميات مستلمة سابقاً ❌
3. `POST /purchase-orders/{id}/receive` → ✅ تعمل — لكن لا يمكن الوصول إليها بلا خطوات 1 و2

وبالمثل: إنشاء مرتجع مورد يعمل، لكن القائمة/التفاصيل له لا تعمل في الفرع.

### Questions (EN)

- **Q6 — Receiving screen on BranchLocal.** Which endpoints is the receiving screen supposed to call to list expected POs and read a PO's lines (ordered / previously received / remaining)? Should `GET /purchase-orders` and `GET /purchase-orders/{id}` be `x-runtime: Both` (the branch serving them from its synced local projection)? If not, what is the intended read surface?
- **Q7 — Vendor returns reads.** Same for `GET /vendor-returns` and `GET /vendor-returns/{id}`: the branch creates/cancels/posts returns but cannot list or view them. Should these reads be `Both`?
- **Q8 — Supplier data in the branch.** Does the branch-side PO DTO include supplier display data (name/code snapshot), or does the FE need `GET /suppliers` to work on BranchLocal too?
- **Q9 — PO states on the branch.** Which PO states exist in the branch projection (ORDERED and later only, since DRAFT/APPROVED are Cloud-owned)? What is the expected FE behavior for a PO that was just ordered and has not synced to the branch yet?
- **Q10 — Freshness after receive.** After the branch posts a receipt, does `GET /purchase-orders/{id}` on BranchLocal immediately reflect the updated received/rejected quantities? And where does the PO's payments summary (Cloud-owned data) come from in the branch's PO detail?
- **Q11 — Sync confirmation.** We understand `sync/*` endpoints are internal plumbing and NOT an FE surface (per FRONTEND.md). Confirm that any branch read requirement will be represented as a normal REST read in the contract, never via sync endpoints.

### المقترح من ناحيتنا

- تحويل الـ GETs الأربعة المذكورة إلى `x-runtime: Both` (الفرع يخدمها من نسخته المحلية المتزامنة)، أو إضافة الـ endpoints البديلة صراحة إن كان هناك تصميم آخر.
- تحديد مصدر بيانات المورد والـ payments summary في نسخة الفرع (snapshot داخل PO DTO أم قراءات إضافية).

### التأثير على شغل الفرونت

تصميم شاشات Stage 3 (الاستلام + مرتجعات الموردين) **لا يمكن البدء فيه** بشكل صحيح قبل حسم هذه النقطة، لأن سلوك 404/405 الحالي يجعل الشاشات غير قابلة للعمل في وضع الفرع.

---

## خلاصة سريعة

| # | الموضوع | الحالة | المطلوب | الموعد |
|---|---|---|---|---|
| 1 | Idempotency-Key في 5 mutations | مفتوح | تحديد مقصود/غير مقصود + توثيق + قرار سلوك refresh | قبل تنفيذ مرحلة الـ auth عند الفرونت |
| 2 | قراءات Purchasing في BranchLocal | مفتوح | تحديد الـ read surface للفرع (+ تعديل x-runtime) | **قبل بدء Stage 3** |

بعد أي قرار: يُحدَّث العقد، ونراجع الـ diff سوياً، ثم نعيد توليد التايبس عند الفرونت.
